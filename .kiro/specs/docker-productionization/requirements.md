# Requirements Document

## Introduction

This document defines the requirements for productionizing the Agentic AI Data Intelligence Platform via Docker. The goal is a zero-manual-steps deployment experience: a developer with Docker Desktop installed clones the repository and runs `docker compose up` to get a fully operational platform. All four services (PostgreSQL, Ollama, FastAPI backend, Streamlit dashboard) must start in the correct order, persist data across restarts, communicate using Docker service names, and run application processes as non-root users. All existing application functionality is preserved — this is a pure infrastructure change.

## Glossary

- **Compose_Stack**: The set of four services (`postgres`, `ollama`, `api`, `dashboard`) managed by `docker compose up`.
- **Docker_Compose**: The `docker compose` CLI tool (Compose v2, no `version:` field required).
- **Postgres_Service**: The `postgres` container running PostgreSQL 15.
- **Ollama_Service**: The `ollama` container serving the `llama3.1` model via HTTP.
- **API_Service**: The `api` container running the FastAPI backend on port 8000.
- **Dashboard_Service**: The `dashboard` container running the Streamlit frontend on port 8501.
- **Health_Check**: A Docker health check that probes a container to determine its `healthy` state.
- **Named_Volume**: A Docker-managed persistent volume that survives `docker compose down` (without `-v`).
- **Service_Name_Hostname**: The Docker Compose service name (e.g., `postgres`, `ollama`, `api`) used as a hostname for inter-container TCP/HTTP communication.
- **Non_Root_User**: A Linux user with UID 1000 (`appuser`), distinct from root (UID 0).
- **Model_Manifest**: The directory at `/root/.ollama/models/manifests/registry.ollama.ai/library/llama3.1` whose existence indicates the `llama3.1` model is cached locally.
- **Health_Endpoint**: The `GET /health` route on the API_Service that returns `{"status": "ok", "version": "2.0.0"}`.
- **Env_Template**: The `.env.example` file containing all environment variable definitions with safe defaults.
- **API_Base_URL**: The environment variable `API_BASE_URL` consumed by the Dashboard_Service to locate the API_Service.

---

## Requirements

### Requirement 1: One-Command Startup

**User Story:** As a developer, I want to start the entire platform with a single command, so that I can get a working environment immediately after cloning without any manual setup steps.

#### Acceptance Criteria

1. WHEN a developer runs `docker compose up` in the repository root on a machine with Docker Desktop installed, THE Compose_Stack SHALL start all four services without requiring any additional terminal commands.
2. THE Docker_Compose configuration SHALL contain no deprecated `version:` top-level field.
3. WHEN `docker compose up --build` completes successfully, THE API_Service SHALL be reachable at `http://localhost:8000` and THE Dashboard_Service SHALL be reachable at `http://localhost:8501`.
4. THE Compose_Stack SHALL require no manual execution of `pip install`, `ollama pull`, database migrations, or any other setup command by the developer.

---

### Requirement 2: Service Dependency Ordering with Health Checks

**User Story:** As a platform operator, I want services to start in dependency order with health checks, so that no service attempts to connect to a dependency that is not yet ready.

#### Acceptance Criteria

1. WHEN the Compose_Stack starts, THE Docker_Compose SHALL start Postgres_Service before starting API_Service, enforced by `depends_on` with `condition: service_healthy`.
2. WHEN the Compose_Stack starts, THE Docker_Compose SHALL start Ollama_Service before starting API_Service, enforced by `depends_on` with `condition: service_healthy`.
3. WHEN the Compose_Stack starts, THE Docker_Compose SHALL require API_Service to be in `healthy` state before Dashboard_Service starts, enforced by `depends_on` with `condition: service_healthy` on the Dashboard_Service side.
4. THE Postgres_Service health check SHALL use `pg_isready -U ${POSTGRES_USER:-agentic} -d ${POSTGRES_DB:-agenticdb}` with an interval of 10s, timeout of 5s, 5 retries, and a start_period of 10s.
5. THE Ollama_Service health check SHALL use `curl -f http://localhost:11434/api/tags` with an interval of 30s, timeout of 10s, 10 retries, and a start_period of 120s.
6. THE API_Service health check SHALL use `curl -f http://localhost:8000/health` with an interval of 15s, timeout of 5s, 5 retries, and a start_period of 30s.
7. THE Dashboard_Service health check SHALL use `curl -f http://localhost:8501/_stcore/health` with an interval of 15s, timeout of 5s, 5 retries, and a start_period of 30s.
8. IF the Postgres_Service does not reach `healthy` within the configured retry budget, THEN THE API_Service SHALL not start and Docker SHALL apply the `restart: unless-stopped` policy.

---

### Requirement 3: Automatic Ollama Model Pull

**User Story:** As a developer, I want the `llama3.1` model to be pulled automatically on first run, so that I do not need to run any manual `ollama pull` commands.

#### Acceptance Criteria

1. WHEN the Ollama_Service container starts for the first time with an empty `ollama_data` volume, THE Ollama_Service SHALL automatically pull the `llama3.1` model without any user intervention.
2. WHEN the Ollama_Service container starts and the Model_Manifest directory already exists, THE Ollama_Service SHALL skip the `ollama pull` command and start without downloading the model again.
3. THE Ollama_Service entrypoint script SHALL start `ollama serve` as a background process, wait until `http://localhost:11434/api/tags` responds successfully (up to 60 retries with 1s sleep), then check for the Model_Manifest before conditionally pulling.
4. IF the Ollama_Service server does not become ready within 60 seconds, THEN THE entrypoint script SHALL exit with a non-zero status code.
5. WHEN the `llama3.1` model pull is in progress, THE API_Service agents that invoke the LLM SHALL handle unavailability gracefully by skipping LLM calls and returning a degraded response, and THE API_Service SHALL not crash or exit due to LLM unavailability.

---

### Requirement 4: PostgreSQL Data Persistence

**User Story:** As a platform user, I want my uploaded datasets and query history to persist across container restarts, so that I do not lose my work when the stack is restarted.

#### Acceptance Criteria

1. THE Postgres_Service SHALL mount the Named_Volume `postgres_data` at `/var/lib/postgresql/data` inside the container.
2. WHEN `docker compose down` is run without the `-v` flag and then `docker compose up` is run again, THE Postgres_Service SHALL retain all previously stored datasets, summaries, insights, and query history.
3. THE `docker-compose.yml` SHALL declare `postgres_data` as a top-level named volume.
4. THE Postgres_Service SHALL use environment variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` sourced from the `.env` file with defaults `agentic`, `changeme`, and `agenticdb` respectively.

---

### Requirement 5: Uploaded Dataset Persistence

**User Story:** As a platform user, I want uploaded CSV files to persist across container restarts, so that I can continue querying previously uploaded datasets after restarting the stack.

#### Acceptance Criteria

1. THE API_Service SHALL mount the Named_Volume `uploaded_datasets` at `/app/uploaded_datasets` inside the container.
2. WHEN `docker compose down` is run without the `-v` flag and then `docker compose up` is run again, THE API_Service SHALL retain all previously uploaded CSV files in the `uploaded_datasets` volume.
3. THE `docker-compose.yml` SHALL declare `uploaded_datasets` as a top-level named volume.
4. THE Ollama_Service SHALL mount the Named_Volume `ollama_data` at `/root/.ollama` inside the container so that pulled model weights persist across restarts.

---

### Requirement 6: Non-Root Container Execution

**User Story:** As a security-conscious operator, I want API and Dashboard containers to run as non-root users, so that a container breakout does not grant root-level host access.

#### Acceptance Criteria

1. THE `docker/Dockerfile.api` SHALL create a user named `appuser` with UID 1000 using `useradd -m -u 1000 appuser`.
2. THE `docker/Dockerfile.api` SHALL switch to `appuser` before the `ENTRYPOINT` instruction using the `USER appuser` directive.
3. THE `docker/Dockerfile.streamlit` SHALL create a user named `appuser` with UID 1000 using `useradd -m -u 1000 appuser`.
4. THE `docker/Dockerfile.streamlit` SHALL switch to `appuser` before the `CMD` instruction using the `USER appuser` directive.
5. THE `docker/Dockerfile.api` SHALL run `chown -R appuser:appuser /app` after copying application files and before the `USER appuser` directive, so that `appuser` has write access to `/app/uploaded_datasets`.
6. THE `docker/Dockerfile.streamlit` SHALL run `chown -R appuser:appuser /app` after copying application files and before the `USER appuser` directive.

---

### Requirement 7: Docker Service Name Hostnames for Inter-Container Communication

**User Story:** As a platform operator, I want all inter-container connections to use Docker service names as hostnames, so that service-to-service communication works correctly inside the Docker network.

#### Acceptance Criteria

1. THE `DATABASE_URL` environment variable passed to the API_Service SHALL use `postgres` as the hostname (e.g., `postgresql://agentic:changeme@postgres:5432/agenticdb`), not `localhost` or `127.0.0.1`.
2. THE `OLLAMA_HOST` environment variable passed to the API_Service SHALL use `ollama` as the hostname (e.g., `http://ollama:11434`), not `localhost` or `127.0.0.1`.
3. THE `API_BASE_URL` environment variable passed to the Dashboard_Service SHALL use `api` as the hostname (e.g., `http://api:8000`), not `localhost` or `127.0.0.1`.
4. THE `docker-compose.yml` SHALL pass `API_BASE_URL` (not `API_URL`) to the Dashboard_Service environment so that `dashboard/api_client.py` reads the correct variable name.

---

### Requirement 8: FastAPI Health Endpoint

**User Story:** As a platform operator, I want a dedicated `/health` endpoint on the API service, so that Docker health checks and load balancers can reliably determine API readiness.

#### Acceptance Criteria

1. THE API_Service SHALL expose a `GET /health` HTTP route at path `/health`.
2. WHEN the API_Service is running and accepting connections, THE Health_Endpoint SHALL return HTTP status 200.
3. WHEN the Health_Endpoint is called, THE API_Service SHALL return a JSON response body of `{"status": "ok", "version": "2.0.0"}`.
4. THE Health_Endpoint SHALL be independent of database connectivity — it SHALL return 200 even if PostgreSQL is temporarily unreachable.
5. THE existing `GET /` route SHALL remain unchanged and continue to return `{"status": "running", "message": "Agentic AI Data Intelligence Platform v2 is live"}`.

---

### Requirement 9: Environment Variable Configuration

**User Story:** As a developer, I want a pre-configured environment variable template, so that I can configure the platform for my environment without needing to know the internal service names or connection strings.

#### Acceptance Criteria

1. THE Compose_Stack SHALL provide a file named `.env.example` in the repository root containing all environment variables needed to run the platform.
2. THE `.env.example` file SHALL include variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, `OLLAMA_HOST`, and `API_BASE_URL` with working default values that use Docker service name hostnames.
3. WHEN a developer copies `.env.example` to `.env` and runs `docker compose up` without any other changes, THE Compose_Stack SHALL start successfully with default credentials.
4. THE `docker-compose.yml` SHALL use variable interpolation (e.g., `${POSTGRES_PASSWORD:-changeme}`) to source all credentials and connection strings from the `.env` file.
5. THE `.env` file SHALL be listed in `.gitignore` or `.dockerignore` to prevent secrets from being committed to version control or baked into images.
6. THE `POSTGRES_PASSWORD` variable SHALL be the only secret that requires user modification for a secure production deployment.

---

### Requirement 10: API Service Startup Reliability

**User Story:** As a platform operator, I want the API service to handle transient database connection delays at startup, so that the service starts reliably even if PostgreSQL takes a moment to accept connections after its health check passes.

#### Acceptance Criteria

1. THE API_Service entrypoint script (`docker/start_api.sh`) SHALL implement a retry loop that calls `pg_isready -h postgres -p 5432` before launching `uvicorn`.
2. THE retry loop SHALL attempt connection up to 30 times with a 1-second sleep between attempts.
3. IF the retry loop exhausts all 30 attempts without a successful `pg_isready` response, THEN THE entrypoint script SHALL exit with a non-zero status code so Docker applies the restart policy.
4. WHEN `pg_isready` succeeds within the retry budget, THE entrypoint script SHALL launch `uvicorn app.main:app --host 0.0.0.0 --port 8000` using `exec` to replace the shell process.
5. THE `docker/Dockerfile.api` SHALL install `postgresql-client` so that `pg_isready` is available inside the container.
6. THE `docker/Dockerfile.api` SHALL install `curl` so that the Docker health check command (`curl -f http://localhost:8000/health`) is available inside the container.
