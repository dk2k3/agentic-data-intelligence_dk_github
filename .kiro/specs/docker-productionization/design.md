# Design Document: Docker Productionization

## Overview

This document covers the full technical design for productionizing the Agentic AI Data Intelligence Platform via Docker. The goal is a single `docker compose up` command that starts all services (PostgreSQL → Ollama with model auto-pull → FastAPI backend → Streamlit dashboard) in the correct order with health checks, persistent volumes, non-root users, and no localhost references inside containers. This is a pure infrastructure change — all existing application logic is preserved.

The platform comprises four containerized services: `postgres` (data persistence), `ollama` (local LLM serving), `api` (FastAPI backend), and `dashboard` (Streamlit frontend). Inter-service communication uses Docker service names as hostnames. Persistent data (Postgres rows, Ollama model weights, uploaded CSV files) survives container restarts via named volumes.

---

## Architecture

### Service Topology

```mermaid
graph TD
    subgraph "Docker Network (bridge)"
        PG[postgres:5432<br/>postgres:15]
        OL[ollama:11434<br/>custom ollama image<br/>auto-pulls llama3.1]
        API[api:8000<br/>FastAPI + Uvicorn<br/>non-root appuser]
        DASH[dashboard:8501<br/>Streamlit<br/>non-root appuser]
    end

    subgraph "Named Volumes"
        V1[(postgres_data)]
        V2[(ollama_data)]
        V3[(uploaded_datasets)]
    end

    subgraph "Host Ports"
        H1[localhost:5432]
        H2[localhost:11434]
        H3[localhost:8000]
        H4[localhost:8501]
    end

    PG --> V1
    OL --> V2
    API --> V3

    H1 --> PG
    H2 --> OL
    H3 --> API
    H4 --> DASH

    API -->|psycopg2 / SQLAlchemy| PG
    API -->|HTTP REST| OL
    DASH -->|HTTP REST via API_BASE_URL| API

    PG -.->|service_healthy| API
    OL -.->|service_healthy| API
    API -.->|service_healthy| DASH
```

### Startup Sequence

```mermaid
sequenceDiagram
    participant DC as docker compose
    participant PG as postgres
    participant OL as ollama
    participant API as api
    participant DASH as dashboard

    DC->>PG: start
    PG-->>DC: healthy (pg_isready passes)

    DC->>OL: start (custom image)
    Note over OL: start_ollama.sh runs:<br/>1. ollama serve &<br/>2. wait for :11434<br/>3. pull llama3.1 if absent
    OL-->>DC: healthy (curl /api/tags passes)

    DC->>API: start (depends_on: postgres healthy, ollama healthy)
    Note over API: start_api.sh runs:<br/>retry loop up to 30s<br/>waits for postgres TCP
    API-->>DC: healthy (GET /health returns 200)

    DC->>DASH: start (depends_on: api healthy)
    DASH-->>DC: healthy (GET /_stcore/health)
```

---

## Components and Interfaces

### Component 1: `postgres` Service

**Purpose**: Persistent relational storage for datasets, summaries, insights, and query history.

**Image**: `postgres:15` (official, no custom build needed)

**Interface**:
- Port: `5432` (host-mapped for external tooling)
- Credentials via env vars: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- Health check: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`
- Volume: `postgres_data:/var/lib/postgresql/data`

**Env vars consumed**:
```
POSTGRES_USER=agentic
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=agenticdb
```

---

### Component 2: `ollama` Service (Custom Image)

**Purpose**: Serves the `llama3.1` LLM locally. Auto-pulls the model on first boot so users don't need any manual steps.

**Image**: Built from `docker/Dockerfile.ollama` (extends `ollama/ollama:latest`)

**Interface**:
- Port: `11434` (host-mapped for direct use)
- Health check: `curl -f http://localhost:11434/api/tags`
- Volume: `ollama_data:/root/.ollama` (model weights persist across restarts)
- Entrypoint: `docker/start_ollama.sh`

**Key behaviour of `start_ollama.sh`**:
1. Start `ollama serve` in background
2. Poll `http://localhost:11434` until ready (max 60s)
3. Check if `llama3.1` already in `/root/.ollama/models` to skip redundant pulls
4. Pull `llama3.1` if absent
5. Keep container alive (`wait`)

---

### Component 3: `api` Service

**Purpose**: FastAPI backend — the core analytics engine. Connects to Postgres for persistence and Ollama for LLM features.

**Image**: Built from `docker/Dockerfile.api`

**Interface**:
- Port: `8000`
- Health check: `GET /health` → `{"status": "ok"}`
- Volume: `uploaded_datasets:/app/uploaded_datasets`
- Depends on: `postgres` (healthy), `ollama` (healthy)
- Entrypoint: `docker/start_api.sh` (adds TCP-level Postgres retry before uvicorn)

**Env vars consumed**:
```
DATABASE_URL=postgresql://agentic:${POSTGRES_PASSWORD}@postgres:5432/agenticdb
OLLAMA_HOST=http://ollama:11434
```

**New endpoint added to `app/main.py`**:
```
GET /health → {"status": "ok", "version": "2.0.0"}
```

---

### Component 4: `dashboard` Service

**Purpose**: Streamlit frontend. Communicates with the API exclusively via `API_BASE_URL` (Docker service name, not localhost).

**Image**: Built from `docker/Dockerfile.streamlit`

**Interface**:
- Port: `8501`
- Health check: `curl -f http://localhost:8501/_stcore/health`
- Depends on: `api` (healthy)

**Env vars consumed**:
```
API_BASE_URL=http://api:8000
```

**Existing code already correct**: `dashboard/api_client.py` already reads `os.getenv("API_BASE_URL", "http://127.0.0.1:8000")` — no code change needed, only docker-compose must pass `API_BASE_URL` (not `API_URL` as the current broken compose does).

---

## Data Models

### Environment Configuration (`.env.example`)

```
# PostgreSQL
POSTGRES_USER=agentic
POSTGRES_PASSWORD=changeme
POSTGRES_DB=agenticdb

# Ollama
OLLAMA_HOST=http://ollama:11434

# API → Postgres
DATABASE_URL=postgresql://agentic:changeme@postgres:5432/agenticdb

# Dashboard → API
API_BASE_URL=http://api:8000
```

Variables `POSTGRES_PASSWORD` is the only secret that should be changed. All other values work out-of-the-box with Docker service names.

### Volume Mapping

| Volume Name | Container Path | Service | Purpose |
|---|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | postgres | DB rows |
| `ollama_data` | `/root/.ollama` | ollama | Model weights |
| `uploaded_datasets` | `/app/uploaded_datasets` | api | CSV files |

---

## Error Handling

### Scenario 1: Postgres Not Ready When API Starts

**Condition**: `depends_on: service_healthy` passes the Docker healthcheck, but TCP connection still takes a moment.
**Response**: `start_api.sh` implements a retry loop (30 attempts × 1s sleep) testing `pg_isready` before launching uvicorn.
**Recovery**: uvicorn starts only after Postgres accepts connections. If it never becomes ready in 30s, the container exits with code 1 so Docker can restart it.

### Scenario 2: Ollama Model Not Yet Pulled

**Condition**: First run on a machine with no `ollama_data` volume.
**Response**: `start_ollama.sh` detects absence of `llama3.1` in `/root/.ollama/models/manifests` and runs `ollama pull llama3.1`. The API's `depends_on: ollama: condition: service_healthy` ensures the API doesn't start until the health check passes, but the health check only verifies the Ollama API is running (not that the model is pulled). LLM agents already have graceful `try/except` fallback — they skip silently if Ollama is busy pulling. Model pull completes in background; no crash.
**Recovery**: Transparent to the user. Pull is idempotent — on subsequent starts, the manifest check skips the pull entirely.

### Scenario 3: Dashboard Starts Before API Ready

**Condition**: Race condition on startup.
**Response**: `depends_on: api: condition: service_healthy` prevents dashboard from starting until `GET /health` returns 200.
**Recovery**: Streamlit shows a connection error in the UI if API goes down mid-session; user refreshes to reconnect.

### Scenario 4: Non-Root User Permission on Volumes

**Condition**: Named volume mounted as root; non-root `appuser` (UID 1000) can't write.
**Response**: Dockerfiles `chown` the working directory to `appuser` before the USER switch. For `uploaded_datasets`, the volume is owned by root by default, so the api Dockerfile explicitly creates the directory with correct ownership before switching user.
**Recovery**: `RUN mkdir -p /app/uploaded_datasets && chown -R appuser:appuser /app/uploaded_datasets` in Dockerfile.api.

---

## Testing Strategy

### Unit Testing Approach

No new business logic is introduced. Existing test suite in `tests/` continues to work via `python -m pytest tests/test_pipeline.py -v` against a running stack.

### Property-Based Testing Approach

Not applicable for infrastructure-only changes.

### Integration Testing Approach

**Smoke test after `docker compose up --build`**:
1. `curl http://localhost:8000/health` → `{"status": "ok"}`
2. `curl http://localhost:8000/` → `{"status": "running", ...}`
3. `curl http://localhost:11434/api/tags` → JSON with model list
4. Browser `http://localhost:8501` → Streamlit UI loads
5. Upload a CSV via Streamlit → `dataset_id` returned
6. Ask a question → result returned

**Volume persistence test**:
1. Upload a CSV, note `dataset_id`
2. `docker compose down` (NOT `--volumes`)
3. `docker compose up`
4. `GET /dataset-summary/{dataset_id}` → still returns data

---

## Performance Considerations

- `pool_pre_ping=True` is already set in `app/db.py` — SQLAlchemy will auto-reconnect if Postgres restarts.
- Ollama model weights are in a named volume; subsequent starts skip the pull (typically 4–5 GB for llama3.1) — startup is fast after first run.
- `uploaded_datasets` volume prevents re-upload on container restart.
- `pip install --no-cache-dir` keeps image layers lean.
- Multi-stage builds are not needed here since there's no compiled artifact; the slim base image is sufficient.

---

## Security Considerations

- Non-root `appuser` (UID 1000) in both `api` and `dashboard` containers reduces attack surface.
- `POSTGRES_PASSWORD` is sourced from `.env` (git-ignored) — never hardcoded.
- `.dockerignore` excludes `.env`, `*.db`, `__pycache__`, `.git`, and `venv`.
- Postgres port `5432` is exposed to host only for development convenience; in a production cloud deployment, remove the `ports:` entry from the postgres service.
- Ollama port `11434` is similarly host-exposed for development; restrict in production.

---

## Dependencies

| Dependency | Version | Purpose |
|---|---|---|
| `postgres` | 15 | Relational DB |
| `ollama/ollama` | latest | Local LLM serving |
| `python` | 3.13-slim | Base image for api and dashboard |
| `psycopg2-binary` | (in requirements.txt) | PostgreSQL Python driver |
| `curl` | system | Health checks in api/dashboard containers |

---

## Low-Level Design: Exact File Contents

### 1. `docker/start_ollama.sh` (CREATE)

**Purpose**: Custom entrypoint for the Ollama container. Starts the server, waits for it to be ready, pulls `llama3.1` only if not already cached, then keeps the container running.

```bash
#!/bin/sh
set -e

echo "[ollama] Starting ollama serve..."
ollama serve &
OLLAMA_PID=$!

echo "[ollama] Waiting for ollama to be ready..."
RETRIES=60
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ "$RETRIES" -le 0 ]; then
        echo "[ollama] ERROR: ollama did not start in time"
        exit 1
    fi
    sleep 1
done
echo "[ollama] ollama is ready."

MODEL="llama3.1"
MODEL_MANIFEST_DIR="/root/.ollama/models/manifests/registry.ollama.ai/library/llama3.1"

if [ -d "$MODEL_MANIFEST_DIR" ]; then
    echo "[ollama] Model '$MODEL' already present. Skipping pull."
else
    echo "[ollama] Pulling model '$MODEL'..."
    ollama pull "$MODEL"
    echo "[ollama] Model '$MODEL' pulled successfully."
fi

echo "[ollama] Ready. Keeping container alive."
wait "$OLLAMA_PID"
```

---

### 2. `docker/Dockerfile.ollama` (CREATE)

**Purpose**: Extends the official Ollama image with the auto-pull entrypoint script.

```dockerfile
FROM ollama/ollama:latest

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY docker/start_ollama.sh /start_ollama.sh
RUN chmod +x /start_ollama.sh

ENTRYPOINT ["/start_ollama.sh"]
```

> **Build context note**: The `docker-compose.yml` builds this with `context: .` so `docker/start_ollama.sh` is available at build time.

---

### 3. `docker/start_api.sh` (CREATE)

**Purpose**: Waits for PostgreSQL to accept TCP connections before launching uvicorn. Provides a retry loop on top of Docker's `service_healthy` depends_on.

```bash
#!/bin/sh
set -e

HOST="${POSTGRES_HOST:-postgres}"
PORT="${POSTGRES_PORT:-5432}"
MAX_RETRIES=30

echo "[api] Waiting for PostgreSQL at $HOST:$PORT..."
RETRIES=0
until pg_isready -h "$HOST" -p "$PORT" -U "${POSTGRES_USER:-agentic}" > /dev/null 2>&1; do
    RETRIES=$((RETRIES + 1))
    if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
        echo "[api] ERROR: PostgreSQL not ready after ${MAX_RETRIES}s. Exiting."
        exit 1
    fi
    echo "[api] PostgreSQL not ready yet ($RETRIES/$MAX_RETRIES). Retrying..."
    sleep 1
done
echo "[api] PostgreSQL is ready. Starting uvicorn..."

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

### 4. `.env.example` (CREATE)

**Purpose**: Template showing all variables required for Docker Compose. Users copy this to `.env` and set their own password.

```dotenv
# ============================================================
# Agentic AI Data Intelligence Platform — Docker Environment
# ============================================================
# Copy this file to .env and adjust values before running:
#   cp .env.example .env
# ============================================================

# ------------------------------------------------------------
# PostgreSQL
# ------------------------------------------------------------
POSTGRES_USER=agentic
POSTGRES_PASSWORD=changeme
POSTGRES_DB=agenticdb

# ------------------------------------------------------------
# API → PostgreSQL connection string
# Uses Docker service name 'postgres' as host
# ------------------------------------------------------------
DATABASE_URL=postgresql://agentic:changeme@postgres:5432/agenticdb

# ------------------------------------------------------------
# Ollama LLM Server
# Uses Docker service name 'ollama' as host
# ------------------------------------------------------------
OLLAMA_HOST=http://ollama:11434

# ------------------------------------------------------------
# Dashboard → API
# Uses Docker service name 'api' as host
# ------------------------------------------------------------
API_BASE_URL=http://api:8000
```

---

### 5. `docker-compose.yml` (MODIFY — full rewrite)

**Key fixes from current version**:
- Remove deprecated `version:` field
- Remove all `container_name:` entries
- Fix `API_URL` → `API_BASE_URL` in dashboard env
- Add `ollama` health check
- Change dashboard `depends_on` to `condition: service_healthy` on `api`
- Add `api` health check (via new `/health` endpoint)
- Build `ollama` from custom `Dockerfile.ollama`
- Add `uploaded_datasets` volume for persistence
- Add `postgresql-client` to api image so `pg_isready` is available in `start_api.sh`
- Source secrets from `.env` file

```yaml
services:

  postgres:
    image: postgres:15
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-agentic}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
      POSTGRES_DB: ${POSTGRES_DB:-agenticdb}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-agentic} -d ${POSTGRES_DB:-agenticdb}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  ollama:
    build:
      context: .
      dockerfile: docker/Dockerfile.ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 120s

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    restart: unless-stopped
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      ollama:
        condition: service_healthy
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgresql://agentic:changeme@postgres:5432/agenticdb}
      OLLAMA_HOST: ${OLLAMA_HOST:-http://ollama:11434}
      POSTGRES_USER: ${POSTGRES_USER:-agentic}
    volumes:
      - uploaded_datasets:/app/uploaded_datasets
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s

  dashboard:
    build:
      context: .
      dockerfile: docker/Dockerfile.streamlit
    restart: unless-stopped
    ports:
      - "8501:8501"
    depends_on:
      api:
        condition: service_healthy
    environment:
      API_BASE_URL: ${API_BASE_URL:-http://api:8000}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s

volumes:
  postgres_data:
  ollama_data:
  uploaded_datasets:
```

---

### 6. `docker/Dockerfile.api` (MODIFY)

**Changes from current**:
- Install `postgresql-client` so `pg_isready` is available for `start_api.sh`
- Install `curl` so the healthcheck `CMD curl -f` works
- Add non-root `appuser` (UID 1000)
- Copy and use `start_api.sh` as entrypoint
- Create `uploaded_datasets` with correct ownership before switching user

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Build tools + postgresql-client (for pg_isready) + curl (for health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Create non-root user and fix directory ownership
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/uploaded_datasets && \
    chown -R appuser:appuser /app

# Copy and make entrypoint executable
RUN chmod +x /app/docker/start_api.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker/start_api.sh"]
```

---

### 7. `docker/Dockerfile.streamlit` (MODIFY)

**Changes from current**:
- Install `curl` for health check
- Add non-root `appuser` (UID 1000)

```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "dashboard/streamlit_app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
```

---

### 8. `app/main.py` (MODIFY — add `/health` endpoint only)

**Change**: Add a dedicated `/health` endpoint after the existing `@app.get("/")` health check. All other code is untouched.

**Existing route (unchanged)**:
```python
@app.get("/")
def health_check():
    return {"status": "running", "message": "Agentic AI Data Intelligence Platform v2 is live"}
```

**New route to add immediately after**:
```python
@app.get("/health")
def health():
    """Dedicated health endpoint for Docker health checks and load balancers."""
    return {"status": "ok", "version": "2.0.0"}
```

No imports change. No existing routes change. This is a 4-line addition.

---

### 9. `.dockerignore` (MODIFY — minor improvements)

**Changes from current**:
- Add `agentic.db` explicitly (currently excluded by `*.db` glob — keep)
- Add `docker/*.sh` exclusion note: Actually, shell scripts ARE needed in the build context — do not exclude them
- Add `.kiro/` to exclusions (spec files not needed in image)
- Add `tests/` to exclusions (test files not needed in production image)
- Add `requirements-lock.txt` exclusion if unused in Docker build
- Add `run.py` exclusion (local dev runner, not needed in container)
- Keep `uploaded_datasets/.gitkeep` inclusion pattern

```dockerignore
# Python
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.egg-info

# Virtual environments
venv
.venv
env

# Version control
.git
.gitignore
.gitattributes

# IDE / editors
.idea
.vscode
*.swp
*.swo

# Environment files (secrets)
.env

# Database files
*.db
*.sqlite
*.sqlite3

# Jupyter
.ipynb_checkpoints
*.ipynb

# Uploaded data (use named volume instead)
uploaded_datasets/*
!uploaded_datasets/.gitkeep

# Logs and temp
logs
tmp
cache
*.log

# Node (if any tooling is added later)
node_modules

# Build artifacts
dist
build

# Kiro spec files (not needed in image)
.kiro

# Tests (not needed in production image)
tests

# Local dev runner (not needed in container)
run.py

# Lock files not used by Docker build
requirements-lock.txt
```

---

### 10. `README.md` (MODIFY — Docker-first section)

**Change**: Replace the existing "Getting started" section with Docker-first instructions. The local dev section moves to a secondary position. All other content is preserved.

The "Getting started" section becomes:

```markdown
## Getting started

### Quick start with Docker (recommended)

**Prerequisites**: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker + Docker Compose v2) installed. That's it.

```bash
# 1. Clone the repository
git clone <repo-url>
cd agentic-data-intelligence_dk_V2

# 2. Configure environment (optional — defaults work out of the box)
cp .env.example .env
# Edit .env to set POSTGRES_PASSWORD and any other overrides

# 3. Start everything
docker compose up --build
```

First run downloads the `llama3.1` model (~4.7 GB) automatically. Subsequent starts are fast.

| Service | URL |
|---|---|
| Streamlit Dashboard | http://localhost:8501 |
| FastAPI Backend | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Ollama API | http://localhost:11434 |

**Stop the stack:**
```bash
docker compose down          # stops containers, keeps volumes
docker compose down -v       # stops containers AND deletes all data
```

**Rebuild after code changes:**
```bash
docker compose up --build
```

### Run locally (without Docker)

**Prerequisites**: Python 3.10+, [Ollama](https://ollama.com/) installed and running.

```bash
# Pull the LLM model
ollama pull llama3.1

# Install dependencies
pip install -r requirements.txt

# Start both services together
python run.py

# Or separately:
uvicorn app.main:app --reload          # http://localhost:8000
streamlit run dashboard/streamlit_app.py  # http://localhost:8501
```
```

---

### 11. `dashboard/api_client.py` (VERIFY — no change needed)

The file already uses `os.getenv("API_BASE_URL", "http://127.0.0.1:8000")` on line 6. This is correct. The docker-compose fix (changing `API_URL` to `API_BASE_URL` in the dashboard environment) is the only required change — no code modification needed.

**Verification**: The env var name `API_BASE_URL` in `api_client.py` matches the variable name in `.env.example` and `docker-compose.yml`. No mismatch.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Service Startup Order Guarantee

For all Compose_Stack startups, `postgres` and `ollama` must both reach the `healthy` state before the `api` container starts, and `api` must reach `healthy` before `dashboard` starts. This ordering is enforced by `depends_on` with `condition: service_healthy` in `docker-compose.yml`.

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: Non-Root Process Execution

For all running container instances of `api` and `dashboard`, no application process runs as root (UID 0). Both Dockerfiles create `appuser` with UID 1000 and switch to that user before the CMD/ENTRYPOINT, ensuring the process UID is always 1000.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 3: No Localhost Cross-Service References

For all inter-service environment variables in `docker-compose.yml` (`DATABASE_URL`, `OLLAMA_HOST`, `API_BASE_URL`), no value contains `localhost` or `127.0.0.1`. All service-to-service URLs use Docker Compose service names (`postgres`, `ollama`, `api`) as hostnames.

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 4: Volume Data Persistence

For any data written to `postgres_data`, `ollama_data`, or `uploaded_datasets` Named_Volumes during a running session, that data persists and is accessible after `docker compose down && docker compose up` when the `-v` flag is not used.

**Validates: Requirements 4.2, 5.2**

### Property 5: Ollama Model Pull Idempotency

For all Ollama container starts where the Model_Manifest directory already exists at `/root/.ollama/models/manifests/registry.ollama.ai/library/llama3.1`, the `ollama pull` command is NOT executed. The entrypoint script must skip the pull, keeping subsequent starts fast.

**Validates: Requirement 3.2**

### Property 6: API Health Endpoint Invariant

For all states in which the FastAPI application is running and accepting connections — regardless of database connectivity, Ollama availability, or concurrent request load — `GET /health` returns HTTP 200 with body `{"status": "ok", "version": "2.0.0"}`.

**Validates: Requirements 8.2, 8.3, 8.4**

### Property 7: Dashboard API URL Resolution

For all environment configurations passed to the `dashboard` container, the variable key used for API communication is `API_BASE_URL` (not `API_URL`), and its value uses `api` as the hostname rather than `127.0.0.1` or `localhost`.

**Validates: Requirements 7.3, 7.4**

### Property 8: API Startup Retry Correctness

For any number of initial `pg_isready` failures N where N < 30, the `start_api.sh` entrypoint eventually launches uvicorn after N+1 attempts. For any N >= 30 consecutive failures, the script exits with a non-zero status code without launching uvicorn.

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

### Property 9: LLM Unavailability Resilience

For any valid incoming API request when the Ollama service is unreachable or the model is still being pulled, the API_Service returns a valid JSON response (with degraded or empty LLM fields) rather than an unhandled exception or HTTP 500 crash.

**Validates: Requirement 3.5**
