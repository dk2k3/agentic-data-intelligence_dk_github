# Implementation Plan: Docker Productionization

## Overview

Pure infrastructure changes to make the platform start reliably with `docker compose up`. All tasks write, modify, or create files. No business logic changes — existing application code is preserved throughout. The work falls into four logical groups: new entrypoint scripts, Dockerfile updates, Compose/config file fixes, and a minimal API endpoint addition.

---

## Tasks

- [ ] 1. Create Ollama entrypoint script and custom image
  - [ ] 1.1 Create `docker/start_ollama.sh`
    - Write a POSIX shell script that starts `ollama serve` in the background, polls `http://localhost:11434/api/tags` with up to 60 retries (1s sleep each), checks for the Model_Manifest directory at `/root/.ollama/models/manifests/registry.ollama.ai/library/llama3.1`, pulls `llama3.1` only if absent, then blocks on `wait $OLLAMA_PID`
    - The script must `set -e` and exit with code 1 if the server never becomes ready within 60s
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 1.2 Create `docker/Dockerfile.ollama`
    - Extend `FROM ollama/ollama:latest`
    - Install `curl` via `apt-get` with `--no-install-recommends` and clean the apt cache
    - `COPY docker/start_ollama.sh /start_ollama.sh` and `RUN chmod +x /start_ollama.sh`
    - Set `ENTRYPOINT ["/start_ollama.sh"]`
    - Build context is the repo root (`.`) so the `docker/` path is reachable during build
    - _Requirements: 3.1, 3.3, 2.5_

- [ ] 2. Create API entrypoint script
  - [ ] 2.1 Create `docker/start_api.sh`
    - Write a POSIX shell script that reads `POSTGRES_HOST` (default `postgres`), `POSTGRES_PORT` (default `5432`), `POSTGRES_USER` (default `agentic`) from environment
    - Implements a retry loop: calls `pg_isready -h $HOST -p $PORT -U $USER` up to 30 times with 1s sleep between attempts; if all 30 fail, print an error and `exit 1`
    - On success, runs `exec uvicorn app.main:app --host 0.0.0.0 --port 8000` (using `exec` to replace the shell process)
    - The script must `set -e` at the top
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 3. Add `/health` endpoint to FastAPI app
  - [ ] 3.1 Modify `app/main.py` — add `GET /health` route
    - Insert the following 4-line route immediately after the existing `@app.get("/")` `health_check` function (around line 178):
      ```python
      @app.get("/health")
      def health():
          """Dedicated health endpoint for Docker health checks and load balancers."""
          return {"status": "ok", "version": "2.0.0"}
      ```
    - Do NOT change any other code — no imports, no existing routes, no logic
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 4. Update `docker/Dockerfile.api`
  - [ ] 4.1 Modify `docker/Dockerfile.api` — add system deps, non-root user, and new entrypoint
    - In the `apt-get install` block, add `postgresql-client` and `curl` alongside the existing `gcc g++ build-essential`; use `--no-install-recommends` flag
    - Merge the two separate `RUN pip install` lines into one chained command (`&&`) for a cleaner layer
    - After `COPY . .`, add:
      ```dockerfile
      RUN useradd -m -u 1000 appuser && \
          mkdir -p /app/uploaded_datasets && \
          chown -R appuser:appuser /app
      RUN chmod +x /app/docker/start_api.sh
      USER appuser
      ```
    - Replace the final `CMD ["uvicorn", ...]` with `ENTRYPOINT ["/app/docker/start_api.sh"]`
    - _Requirements: 6.1, 6.2, 6.5, 10.5, 10.6_

- [ ] 5. Update `docker/Dockerfile.streamlit`
  - [ ] 5.1 Modify `docker/Dockerfile.streamlit` — add curl, non-root user, headless flag
    - In the `apt-get install` block, add `curl` alongside existing `gcc g++ build-essential`; use `--no-install-recommends` flag
    - Merge the two separate `RUN pip install` lines into one chained command (`&&`)
    - After `COPY . .`, add:
      ```dockerfile
      RUN useradd -m -u 1000 appuser && \
          chown -R appuser:appuser /app
      USER appuser
      ```
    - Update the `CMD` to add `--server.headless=true` and explicitly set `--server.port=8501`:
      ```dockerfile
      CMD ["streamlit", "run", "dashboard/streamlit_app.py", \
           "--server.address=0.0.0.0", \
           "--server.port=8501", \
           "--server.headless=true"]
      ```
    - _Requirements: 6.3, 6.4, 6.6, 2.7_

- [ ] 6. Rewrite `docker-compose.yml`
  - [ ] 6.1 Rewrite `docker-compose.yml` with all production fixes
    - Remove the top-level `version: "3.9"` field (deprecated in Compose v2)
    - Remove all `container_name:` entries from every service
    - `postgres` service: add `start_period: 10s` to existing healthcheck; use `${POSTGRES_USER:-agentic}` and `${POSTGRES_DB:-agenticdb}` in the healthcheck test command; source credentials from env with `:-` defaults
    - `ollama` service: change `image: ollama/ollama:latest` to a `build:` block pointing to `docker/Dockerfile.ollama` with `context: .`; add healthcheck using `["CMD", "curl", "-f", "http://localhost:11434/api/tags"]` with interval 30s, timeout 10s, retries 10, start_period 120s
    - `api` service: change `ollama: condition: service_started` to `condition: service_healthy`; add `POSTGRES_USER: ${POSTGRES_USER:-agentic}` to environment; change `- ./uploaded_datasets:/app/uploaded_datasets` to named volume `uploaded_datasets:/app/uploaded_datasets`; add healthcheck using `["CMD", "curl", "-f", "http://localhost:8000/health"]` with interval 15s, timeout 5s, retries 5, start_period 30s; source `DATABASE_URL` and `OLLAMA_HOST` from env with `:-` defaults
    - `dashboard` service: rename env var `API_URL` → `API_BASE_URL`; change `depends_on: - api` to `depends_on: api: condition: service_healthy`; add healthcheck using `["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]` with interval 15s, timeout 5s, retries 5, start_period 30s; source `API_BASE_URL` from env with `:-` default
    - Add `uploaded_datasets:` to the top-level `volumes:` block alongside existing `postgres_data:` and `ollama_data:`
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 4.1, 4.3, 5.1, 5.3, 5.4, 7.1, 7.2, 7.3, 7.4, 9.4_

- [ ] 7. Create `.env.example`
  - [ ] 7.1 Create `.env.example` in repository root
    - Include variables: `POSTGRES_USER=agentic`, `POSTGRES_PASSWORD=changeme`, `POSTGRES_DB=agenticdb`, `DATABASE_URL=postgresql://agentic:changeme@postgres:5432/agenticdb`, `OLLAMA_HOST=http://ollama:11434`, `API_BASE_URL=http://api:8000`
    - Add explanatory comments above each section (PostgreSQL, API→Postgres, Ollama, Dashboard→API)
    - Include a header comment explaining: copy to `.env`, only `POSTGRES_PASSWORD` needs changing for production
    - All hostnames must use Docker service names (`postgres`, `ollama`, `api`), not `localhost`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6_

- [ ] 8. Update `.dockerignore`
  - [ ] 8.1 Modify `.dockerignore` — add missing exclusions
    - Add `.kiro` to exclude spec files from the Docker build context
    - Add `tests` to exclude test files from the production image
    - Add `run.py` to exclude the local dev launcher
    - Add `requirements-lock.txt` to exclude the lock file unused by the Docker build
    - Preserve the existing `uploaded_datasets/*` / `!uploaded_datasets/.gitkeep` pattern
    - Do NOT exclude `docker/*.sh` — shell scripts are required in the build context
    - _Requirements: 9.5_

- [ ] 9. Create `uploaded_datasets/.gitkeep` and finalize repo hygiene
  - [ ] 9.1 Create `uploaded_datasets/.gitkeep`
    - Create an empty file at `uploaded_datasets/.gitkeep` so the `uploaded_datasets/` directory is tracked by git (required for `.dockerignore`'s `!uploaded_datasets/.gitkeep` allowlist rule to work)
    - _Requirements: 5.1, 5.2_

- [ ] 10. Update `README.md`
  - [ ] 10.1 Modify the "Getting started" section in `README.md`
    - Replace the current "Getting started" section (which lists local Python prerequisites) with a Docker-first section as the primary path
    - Docker section must include: prerequisites (Docker Desktop only), the three-command flow (`git clone`, `cp .env.example .env`, `docker compose up --build`), a first-run note about the ~4.7 GB llama3.1 download, a service URL table (Streamlit 8501, FastAPI 8000, Swagger /docs, Ollama 11434), and `docker compose down` / `docker compose down -v` teardown commands
    - Move the existing local Python dev instructions to a secondary subsection titled "Run locally (without Docker)"
    - All other README sections (Architecture, Agents, API endpoints, etc.) must be preserved verbatim
    - _Requirements: 1.1, 1.3, 1.4_

- [ ] 11. Final checkpoint — verify all files are consistent
  - Ensure all tests pass, ask the user if questions arise.
  - Confirm `docker/start_api.sh` references `pg_isready` and that `Dockerfile.api` installs `postgresql-client`
  - Confirm `API_BASE_URL` is used consistently in `docker-compose.yml`, `.env.example`, and `dashboard/api_client.py`
  - Confirm `uploaded_datasets` appears as a named volume in `docker-compose.yml` volumes block and in the `api` service mount
  - Confirm `app/main.py` has `GET /health` and the original `GET /` is untouched

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP (none in this plan — all tasks are required infrastructure)
- This is a pure infrastructure change; no business logic in `app/agents/`, `app/services/`, or `dashboard/` is modified
- Task 3.1 is a 4-line addition to `app/main.py` — the rest of the file is untouched
- The `.env.example` uses `changeme` as the default password; users should replace it before production deployment
- `docker/start_ollama.sh` and `docker/start_api.sh` must have Unix line endings (LF) and be executable; on Windows, ensure your editor saves them with LF or add a `.gitattributes` rule
- Tasks 1–3 (new files) have no inter-dependencies and can proceed in parallel; Task 6.1 (docker-compose rewrite) depends on Tasks 1.2, 4.1, 5.1, and 3.1 being complete for the healthchecks and build targets to be valid

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "7.1", "8.1", "9.1"] },
    { "id": 1, "tasks": ["1.2", "4.1", "5.1"] },
    { "id": 2, "tasks": ["6.1"] },
    { "id": 3, "tasks": ["10.1"] }
  ]
}
```
