# Agentic AI Data Intelligence Platform

A **domain-agnostic, production-grade AI analytics copilot** that transforms natural-language questions into safe, explainable, and evidence-based data insights — for **any** structured dataset.

Built on a modular multi-agent pipeline with FastAPI, Streamlit, Pandas, and Ollama-hosted LLMs. Fully containerized — runs with a single command.

---

## Quick Start (Docker — Recommended)

**The only prerequisite is [Docker Desktop](https://www.docker.com/products/docker-desktop/).**  
No Python, no Ollama, no pip, no database setup required.

```bash
git clone <repo-url>
cd agentic-data-intelligence_dk_V2
docker compose up --build
```

That's it. Docker will automatically:
- Pull and start PostgreSQL
- Pull and start Ollama, then download the `llama3.1` model (~4.7 GB on first run)
- Build and start the FastAPI backend
- Build and start the Streamlit dashboard

| Service | URL |
|---|---|
| **Streamlit Dashboard** | http://localhost:8501 |
| **FastAPI Backend** | http://localhost:8000 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **Ollama API** | http://localhost:11434 |

> **First run note:** The `llama3.1` model is ~4.7 GB. It downloads automatically in the background. Subsequent starts skip the download and are fast.

### Stop the stack

```bash
docker compose down          # stops containers, keeps all data
docker compose down -v       # stops containers AND deletes all volumes (full reset)
```

### Rebuild after code changes

```bash
docker compose up --build
```

---

## Docker Architecture

```
┌─────────────────────────────────────────────────┐
│              Docker Bridge Network               │
│                                                 │
│  ┌──────────┐    ┌──────────┐                   │
│  │ postgres │    │  ollama  │                   │
│  │  :5432   │    │  :11434  │                   │
│  └────┬─────┘    └────┬─────┘                   │
│       │ service_       │ service_                │
│       │ healthy        │ started                 │
│       └──────┬─────────┘                         │
│              ▼                                   │
│          ┌───────┐                               │
│          │  api  │  FastAPI + Uvicorn            │
│          │ :8000 │  SQLAlchemy → postgres        │
│          └───┬───┘  LangChain → ollama           │
│              │ depends_on                        │
│              ▼                                   │
│        ┌──────────┐                              │
│        │dashboard │  Streamlit                   │
│        │  :8501   │  → api:8000                  │
│        └──────────┘                              │
└─────────────────────────────────────────────────┘

Named Volumes:
  postgres_data      → /var/lib/postgresql/data
  ollama_data        → /root/.ollama
  uploaded_datasets  → /app/uploaded_datasets (bind mount)
```

### Services

| Service | Image | Port | Role |
|---|---|---|---|
| `postgres` | `postgres:15` | 5432 | Persistent relational storage |
| `ollama` | `ollama/ollama:latest` | 11434 | Local LLM serving (llama3.1) |
| `api` | Built from `docker/Dockerfile.api` | 8000 | FastAPI analytics backend |
| `dashboard` | Built from `docker/Dockerfile.streamlit` | 8501 | Streamlit frontend |

### Key environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://agentic:password@postgres:5432/agenticdb` | PostgreSQL connection (uses service name) |
| `OLLAMA_HOST` | `http://ollama:11434` | Ollama server URL (uses service name) |
| `API_BASE_URL` | `http://api:8000` | Backend URL used by Streamlit (uses service name) |

### Data persistence

All data survives `docker compose down` (without `-v`):
- **PostgreSQL** — datasets, summaries, insights, query history
- **Ollama models** — downloaded model weights (no re-download on restart)
- **Uploaded CSVs** — files uploaded via the dashboard

---

## What It Does

Upload any CSV dataset, ask questions in plain English, and get back:

- Computed analytics results (aggregations, rankings, trends, correlations, statistics)
- **Ranked recommendation cards** with composite scoring, signal breakdown, and evidence rows
- A decision brief with actionable guidance
- Confidence scores with explanation
- Auto-generated Pandas code and equivalent SQL (for full transparency)
- Interactive Plotly charts (bar, line, pie, scatter, histogram, heatmap)
- LLM-generated dataset understanding and business insights
- Follow-up question suggestions

The system works on **any dataset** — e-commerce, HR, supply chain, health, finance, or anything else — with zero hardcoded column names or business rules.

---

## Architecture

### Pipeline overview

```
Upload  →  Schema Understanding Agent  →  (cached per dataset)
        →  EDA Agent                   →  statistical profiling
        →  Dataset Understanding Agent →  LLM dataset type + columns (Ollama)
        →  Insight Agent               →  LLM business insights (Ollama)

Ask     →  Intent Classifier Agent      (14 query types)
        →  Metric & Entity Extractor    (fuzzy column matching)
        →  Execution Planner            (builds ExecutionPlan)
        →  Query Verifier               (validates before execution)
        →  Execution Router
              ├─ RecommendationExecutor  (RECOMMENDATION / OPTIMIZATION)
              └─ PandasExecutorAgent     (all other intents)
        →  SQL Generator Agent          (transparency only)
        →  Chart Agent                  (driven by ExecutionPlan)
        →  Confidence Engine            (composite scoring)
        →  Domain Reasoning Agent       (explanation + insights)
        →  Follow-up Question Agent     (LLM, graceful skip)
        →  Response
```

### The Unified ExecutionPlan

Every agent reads from and writes to a single `ExecutionPlan` Pydantic model. No agent passes raw dicts. This guarantees Pandas and SQL produce consistent results.

```python
ExecutionPlan(
    intent      = QueryIntent.RECOMMENDATION,
    metrics     = ["revenue", "returns"],
    group_by    = ["product"],
    aggregation = AggregationFunc.MEAN,
    filters     = [...],
    time_band   = TimeBand(column="order_date", granularity="month"),
    chart_type  = ChartType.BAR,
    ...
)
```

---

## Agents

### Core pipeline (always active, no LLM required)

| Agent | File | Role |
|---|---|---|
| **Schema Understanding Agent** | `schema_understanding_agent.py` | Infers column semantics from data statistics. Zero hardcoded column names. |
| **Intent Classifier Agent** | `intent_classifier_agent.py` | Detects 14 query intents. |
| **Metric & Entity Extractor** | `metric_entity_extractor.py` | Fuzzy-matches metrics, group-by columns, filters, and time bands. |
| **Execution Planner** | `execution_planner.py` | Assembles a validated `ExecutionPlan`. |
| **Query Verifier** | `query_verifier.py` | Validates the plan before execution. |
| **Pandas Executor Agent** | `pandas_executor_agent.py` | Generates and executes safe Pandas code from the `ExecutionPlan`. |
| **Recommendation Executor** | `recommendation_executor.py` | Full decision-support engine for RECOMMENDATION / OPTIMIZATION intents. |
| **SQL Generator Agent** | `sql_generator_agent.py` | Generates SQL from the same `ExecutionPlan` for transparency. |
| **Chart Agent** | `chart_agent.py` | Builds Plotly figure specs from the `ExecutionPlan`. |
| **Confidence Engine** | `confidence_engine.py` | Computes a composite 0–1 confidence score. |
| **Domain Reasoning Agent** | `domain_reasoning_agent.py` | Generates explanations, insights, and recommendations. |

### LLM-enhanced agents (Ollama via `OLLAMA_HOST`, gracefully skipped if unavailable)

| Agent | File | Role |
|---|---|---|
| **Dataset Understanding Agent** | `dataset_understanding_agent.py` | LLM analysis of schema + EDA → dataset type, columns, suggested questions. |
| **Insight Agent** | `insight_agent.py` | LLM-generated business insights from EDA results. |
| **Follow-up Question Agent** | `followup_question_agent.py` | Suggests 3–5 follow-up questions based on the current result. |
| **Visualization Intent Agent** | `visualization_intent_agent.py` | LLM detection of explicit chart type requests. |

> All LLM agents connect to Ollama via the `OLLAMA_HOST` environment variable. In Docker this is `http://ollama:11434`. Locally it defaults to `http://localhost:11434`.

---

## Supported Query Intents

| Intent | Example questions |
|---|---|
| **Aggregation** | "Total revenue", "Average salary by department" |
| **Ranking** | "Top 10 products by sales", "Worst performing regions" |
| **Trend** | "Revenue trend over time", "Monthly units sold" |
| **Statistics** | "Distribution of salaries", "Standard deviation of BMI" |
| **Correlation** | "Correlation between cost and defect rate" |
| **Comparison** | "Compare Electronics vs Clothing revenue" |
| **Filtering** | "Show orders where revenue > 1000" |
| **Recommendation** | "Which supplier should we prioritize?" |
| **Optimization** | "Minimize cost and defect rate" |
| **Anomaly** | "Are there revenue outliers?" |
| **Root cause** | "Why is performance low in some departments?" |
| **Summarization** | "Summarize this dataset" |
| **Visualization** | "Show a pie chart of revenue by category" |
| **Forecasting** | Detected and gracefully rejected if no date column exists |

---

## Project Structure

```
agentic-data-intelligence_dk_V2/
│
├── app/
│   ├── agents/                         # All pipeline agents
│   ├── schemas/                        # Pydantic models (ExecutionPlan)
│   ├── services/                       # Data loading, execution, normalisation
│   ├── core/                           # Logger
│   ├── main.py                         # FastAPI app + all endpoints
│   ├── models.py                       # SQLAlchemy ORM models
│   ├── db.py                           # Database connection (env-driven)
│   └── __init__.py
│
├── dashboard/
│   ├── streamlit_app.py                # Streamlit UI
│   └── api_client.py                   # HTTP client (reads API_BASE_URL)
│
├── docker/
│   ├── Dockerfile.api                  # FastAPI image
│   └── Dockerfile.streamlit            # Streamlit image
│
├── tests/
│   ├── test_pipeline.py                # 150+ NL stress questions
│   ├── smoke_test.py                   # Quick end-to-end smoke test
│   └── smoke_recommendation.py        # Recommendation executor tests
│
├── docker-compose.yml                  # Production Docker Compose
├── requirements.txt
├── run.py                              # Local dev launcher (no Docker)
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Platform status |
| `GET` | `/health` | Health check (used by Docker) |
| `POST` | `/upload-dataset` | Upload CSV, returns `dataset_id` |
| `GET` | `/dataset-summary/{id}` | Dataset understanding (async, LLM) |
| `GET` | `/dataset-insights/{id}` | LLM-generated insights (async) |
| `POST` | `/ask` | Answer a natural-language question |

### `/ask` request

```json
{
  "dataset_id": 1,
  "question": "Recommend the best suppliers based on cost, defect rate, and lead time",
  "chart_override": "bar"
}
```

### `/ask` response (key fields)

```json
{
  "execution_plan":          { ... },
  "generated_pandas":        "...",
  "generated_sql":           "...",
  "result":                  { "cards": [...], "decision_brief": "..." },
  "confidence":              0.97,
  "confidence_explanation":  "...",
  "explanation":             "...",
  "insights":                "...",
  "recommendations":         [...],
  "chart":                   { "data": [...], "layout": {...} },
  "followup_questions":      [...],
  "validation_issues":       [...],
  "is_executable":           true
}
```

---

## Run Locally (Without Docker)

**Prerequisites:** Python 3.10+, [Ollama](https://ollama.com/) installed and running.

```bash
# Pull the LLM model
ollama pull llama3.1

# Install dependencies
pip install -r requirements.txt

# Start both services together
python run.py

# Or start separately:
uvicorn app.main:app --reload           # FastAPI → http://localhost:8000
streamlit run dashboard/streamlit_app.py  # Streamlit → http://localhost:8501
```

---

## Running the Test Suite

```bash
# Quick smoke test (no pytest needed)
python -m tests.smoke_test

# Recommendation executor tests (9 scenarios, 3 domains)
python -m tests.smoke_recommendation

# Full 150+ question stress test
python -m pytest tests/test_pipeline.py -v
```

The test suite covers 4 domains: **e-commerce, HR, health, supply chain**.

---

## Troubleshooting

**Dashboard says "Backend is not reachable"**
- Make sure `docker compose up --build` was used after the last code change
- Check that `API_BASE_URL=http://api:8000` is in the dashboard service env (not `API_URL`)
- Run `docker compose logs api` to check for startup errors

**Dataset type shows "Unknown" / Insights stuck on "generating"**
- Ollama may still be downloading the model (~4.7 GB). Wait a few minutes and refresh.
- Run `docker compose logs ollama` to check the download progress
- The API connects to Ollama via `OLLAMA_HOST=http://ollama:11434`. If you see `localhost:11434` errors in the API logs, run `docker compose down && docker compose up --build`

**PostgreSQL healthcheck fails**
- The healthcheck uses `-d agenticdb`. If you see `database "agentic" does not exist`, run `docker compose down -v && docker compose up` to reset the volume with the correct database name

**Port already in use**
- Stop any local instances of PostgreSQL (5432), Ollama (11434), or other services on ports 8000/8501
- Or change the host port mappings in `docker-compose.yml` (e.g., `"8001:8000"`)

**Rebuild after code changes**
```bash
docker compose down
docker compose up --build
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Frontend | Streamlit |
| Analytics | Pandas, NumPy, scikit-learn |
| Visualization | Plotly |
| LLMs | Ollama (llama3.1) via LangChain |
| Database | PostgreSQL 15 (Docker) / SQLite (local dev) |
| Containerisation | Docker, Docker Compose |
| Validation | Pydantic v2 |
| Logging | Python logging (structured) |

---

## Design Principles

- **Zero hardcoded column names** — all logic is derived from schema analysis and the question
- **Never substitute missing metrics** — if a requested metric isn't in the dataset, the system says so
- **Graceful LLM degradation** — every LLM agent has `try/except`; the core analytics pipeline runs entirely without Ollama
- **Unsupported query handling** — queries that require data not present return a clear explanation, not a hallucinated result
- **Unified execution contract** — Pandas, SQL, and chart generation all consume the same `ExecutionPlan`
- **Evidence-based decisions** — recommendation output includes raw data rows, composite signal scores, and a grade for every candidate
- **Docker-native** — all inter-service URLs use Docker service names; `localhost` is never used inside containers
