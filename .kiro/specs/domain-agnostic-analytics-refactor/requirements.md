# Requirements Document

## Introduction

Refactor the existing AI Data Intelligence Platform backend into a domain-agnostic, production-grade analytics system. The current system suffers from hardcoded keyword-based logic, a limited intent vocabulary, and a fragile metric resolution strategy that causes complex multi-metric queries (e.g., procurement optimization) to silently fall through to meaningless scalar sums. The refactored system must correctly understand and analyze any structured CSV dataset without relying on domain-specific column names, hardcoded business rules, or brittle keyword matching.

The refactor preserves the existing Streamlit UI, FastAPI API contracts, Docker setup, and SQLite database while replacing the backend agent pipeline with modular, schema-driven, LLM-assisted components that share a single canonical execution plan.

---

## Glossary

- **Analytics_System**: The full FastAPI backend including all agents and services.
- **Intent_Classifier**: The agent responsible for classifying the semantic type of a user's natural-language query.
- **Schema_Agent**: The agent responsible for inferring semantic meaning from a dataset's column names and data types without hardcoded rules.
- **Metric_Extractor**: The agent that extracts requested metrics, entities, filters, and groupings from the user's question and validates them against the live dataset schema.
- **Execution_Planner**: The agent that produces a structured, validated execution plan from classified intent and extracted metrics.
- **Query_Verifier**: The agent that validates an execution plan for correctness before execution.
- **Execution_Plan**: A structured Pydantic model containing intent, metrics, aggregations, groupings, filters, time context, and chart type — consumed by all executors.
- **Pandas_Executor**: The service that executes an Execution_Plan against a pandas DataFrame.
- **SQL_Executor**: The service that generates SQL from an Execution_Plan.
- **Visualization_Generator**: The service that generates a Plotly chart specification from an Execution_Plan and its result.
- **Confidence_Engine**: The agent that computes a confidence score using schema coverage, query ambiguity, validation results, and execution success.
- **Reasoning_Agent**: The agent that generates domain-contextual insights and recommendations from analysis results without hardcoded business rules.
- **Evaluation_Suite**: The automated testing framework that runs natural-language stress questions against the pipeline and measures correctness.
- **LLM**: The local language model (currently llama3.1 via Ollama) used by agents that require semantic understanding.
- **Pipeline**: The ordered sequence of agents and services that transforms a natural-language question into a structured result.
- **Dataset**: A user-uploaded CSV file stored in the `uploaded_datasets/` directory and tracked in the SQLite database.

---

## Requirements

### Requirement 1: Expanded Intent Classification

**User Story:** As a data analyst, I want the system to correctly identify complex query types beyond simple aggregation, so that multi-step analytical questions like "recommend an optimal procurement strategy" are routed to the correct executor instead of silently falling back to a scalar sum.

#### Acceptance Criteria

1. THE Intent_Classifier SHALL classify user queries into one of the following intent types: `aggregation`, `comparison`, `ranking`, `filtering`, `trend`, `correlation`, `anomaly_detection`, `statistics`, `recommendation`, `optimization`, `summarization`, `forecasting`, `root_cause_analysis`, and `visualization`.
2. WHEN the user submits a query, THE Intent_Classifier SHALL return the classified intent type, a confidence score between 0.0 and 1.0, and a list of detected sub-intents if the query spans multiple analytical dimensions.
3. IF the Intent_Classifier cannot determine intent with a confidence score above 0.4, THEN THE Intent_Classifier SHALL return intent type `unknown` rather than defaulting to `aggregation`.
4. THE Intent_Classifier SHALL use the dataset schema as additional context when classifying intent, so that column availability informs the classification.
5. WHEN the intent is `optimization` or `recommendation`, THE Intent_Classifier SHALL identify all relevant metric dimensions mentioned in the question and include them in the classification output.
6. THE Intent_Classifier SHALL be implemented using an LLM prompt with a structured JSON output schema, replacing the current keyword-matching approach in `intent_classifier_agent.py` and `query_planner.py`.

---

### Requirement 2: Schema Understanding Agent

**User Story:** As a data analyst, I want the system to automatically understand what each column in my dataset represents, so that questions using domain terms (e.g., "lead time", "defect rate", "stock level") are correctly mapped to actual columns without hardcoded lookup tables.

#### Acceptance Criteria

1. THE Schema_Agent SHALL analyze every column in the uploaded dataset and produce a semantic profile that includes: inferred semantic role (identifier, categorical, numerical measure, date/time, target variable), human-readable description, and cardinality class (low/medium/high).
2. THE Schema_Agent SHALL identify column relationships, including potential foreign-key-like links between string columns and grouping columns, and potential target variable candidates for numerical columns.
3. THE Schema_Agent SHALL never rely on hardcoded column name lists; all semantic inference MUST be driven by statistical properties of the data and LLM understanding of column names.
4. WHEN a dataset is uploaded, THE Schema_Agent SHALL persist its schema analysis alongside the existing `DatasetSummary` record so that downstream agents can retrieve it without re-analysis on every query.
5. THE Schema_Agent SHALL produce output conforming to a Pydantic `SchemaProfile` model containing a list of `ColumnProfile` objects, each with fields: `name`, `dtype`, `semantic_role`, `description`, `is_identifier`, `is_categorical`, `is_numeric`, `is_date`, `cardinality_class`, and `sample_values`.
6. WHEN a user query references a concept not present as a column name (e.g., "procurement efficiency"), THE Schema_Agent SHALL identify the closest semantically related columns and report them with a similarity rationale, rather than returning an empty match.

---

### Requirement 3: Metric and Entity Extractor

**User Story:** As a data analyst, I want the system to correctly extract all metrics, entities, and filters from my question and validate them against the actual dataset columns, so that the system never substitutes an unrelated column when the requested metric is absent.

#### Acceptance Criteria

1. THE Metric_Extractor SHALL extract all requested metrics, entities, filter conditions, and grouping dimensions from the user's natural-language question.
2. WHEN extracting metrics, THE Metric_Extractor SHALL validate each extracted metric against the dataset's `SchemaProfile` to confirm a matching column exists.
3. IF a requested metric cannot be matched to any column in the dataset, THEN THE Metric_Extractor SHALL flag it as `unresolvable` and SHALL NOT substitute it with a semantically unrelated column.
4. WHEN multiple metrics are requested in a single query (e.g., "considering stock levels, lead times, and defect rates"), THE Metric_Extractor SHALL extract all of them as a list and pass all to the Execution_Planner, rather than selecting only the first match.
5. THE Metric_Extractor SHALL extract filter conditions expressed in natural language (e.g., "where category is Electronics", "in Q3 2023") and convert them into structured filter objects with column name, operator, and value.
6. THE Metric_Extractor SHALL extract grouping dimensions (e.g., "by supplier", "per product category") and validate that the corresponding columns exist in the schema.
7. WHEN the user query is ambiguous about which column to use (e.g., "sales" could match `sales_qty` or `sales_amount`), THE Metric_Extractor SHALL report the ambiguity rather than silently selecting one option.

---

### Requirement 4: Execution Planner

**User Story:** As a developer, I want all query execution to be driven by a validated, structured execution plan, so that Pandas, SQL, and visualization generators all produce consistent results from the same source of truth.

#### Acceptance Criteria

1. THE Execution_Planner SHALL accept the classified intent, extracted metrics, and schema profile as inputs and produce a single `ExecutionPlan` Pydantic model as output.
2. THE `ExecutionPlan` model SHALL contain: `intent` (string), `metrics` (list of column references), `aggregations` (dict mapping metric to aggregation function), `group_by` (list of column names), `filters` (list of structured filter objects), `time_context` (optional time range and granularity), `chart_type` (string), `limit` (optional integer), `multi_metric` (boolean), `execution_strategy` (one of: `aggregation`, `ranking`, `statistics`, `correlation`, `optimization`, `recommendation`, `visualization`, `summary`), and `unsupported_reason` (optional string explaining why the query cannot be executed).
3. THE Execution_Planner SHALL route queries to the appropriate `execution_strategy` based on the classified intent: `optimization` and `recommendation` intents SHALL map to the `optimization` strategy, `correlation` and `statistics` SHALL map to their respective strategies, and `ranking`/`aggregation`/`trend` SHALL map to their existing strategies.
4. WHEN the classified intent is `forecasting` and no date column is present in the schema, THE Execution_Planner SHALL set `execution_strategy` to `unsupported` and populate `unsupported_reason` with a human-readable explanation instead of proceeding to execution.
5. THE Pandas_Executor, SQL_Executor, and Visualization_Generator SHALL each accept only an `ExecutionPlan` and a DataFrame (or table name) as inputs, enforcing the single-plan contract.
6. THE Execution_Planner SHALL support multi-metric plans where `metrics` contains more than one element, and SHALL pass all metrics to the selected executor rather than truncating to one.

---

### Requirement 5: Query Verifier

**User Story:** As a developer, I want the system to validate execution plans before running them, so that invalid aggregations, missing columns, and incompatible operations are caught early and reported clearly instead of causing runtime 500 errors.

#### Acceptance Criteria

1. THE Query_Verifier SHALL validate every `ExecutionPlan` before it is passed to any executor.
2. WHEN validating an `ExecutionPlan`, THE Query_Verifier SHALL check: all columns in `metrics`, `group_by`, and `filters` exist in the dataset schema; all aggregation functions are valid for their target column's data type (e.g., `sum` is invalid on a string column); no conflicting operations are present (e.g., applying a time filter when no date column is specified).
3. IF validation fails, THEN THE Query_Verifier SHALL return a structured `ValidationResult` containing a list of `ValidationError` objects, each with a `field`, `error_code`, and `message`, rather than raising an unhandled exception.
4. THE Query_Verifier SHALL distinguish between `fatal` errors (execution must not proceed) and `warning` errors (execution may proceed with degraded confidence).
5. WHEN the `ExecutionPlan` contains an `optimization` or `multi_metric` strategy with more than 5 metrics, THE Query_Verifier SHALL issue a `warning` that result interpretation may be complex.
6. THE Analytics_System SHALL return a structured error response to the API caller when a fatal `ValidationResult` is produced, including the list of validation errors, rather than returning a 500 HTTP error.

---

### Requirement 6: Unified Execution Contract

**User Story:** As a developer, I want all executors to share the same execution plan interface, so that switching between Pandas and SQL execution never produces different results for the same query.

#### Acceptance Criteria

1. THE Pandas_Executor SHALL be refactored to accept an `ExecutionPlan` directly and generate execution logic from the plan's fields, replacing the current code-generation approach in `strict_pandas_generator.py`.
2. THE SQL_Executor SHALL be refactored to generate SQL from an `ExecutionPlan` directly, using the same field mappings as the Pandas_Executor.
3. THE Visualization_Generator SHALL be refactored to generate chart specifications from an `ExecutionPlan` and its result data, replacing the current `chart_agent.py` implementation.
4. WHEN an `ExecutionPlan` specifies `multi_metric = True`, BOTH the Pandas_Executor AND the SQL_Executor SHALL include all listed metrics in their output rather than selecting only the first.
5. THE Analytics_System SHALL include a consistency check in the test suite that runs a representative query against both the Pandas_Executor and SQL_Executor and asserts the results are numerically equivalent (within floating-point tolerance).

---

### Requirement 7: Domain-Contextual Reasoning Agent

**User Story:** As a data analyst, I want the system to generate recommendations and insights that are grounded in the actual dataset content, so that I receive actionable analysis of my procurement data rather than generic template responses.

#### Acceptance Criteria

1. THE Reasoning_Agent SHALL generate recommendations and insights by combining the `ExecutionPlan`, the execution result, and the dataset's `SchemaProfile` — without using any hardcoded domain-specific rules or templates.
2. WHEN the intent is `recommendation` or `optimization`, THE Reasoning_Agent SHALL identify the top and bottom performers across all relevant metrics in the `ExecutionPlan` and include them in the recommendation output.
3. THE Reasoning_Agent SHALL frame all insights relative to the dataset's actual value ranges and distributions, using statistics from the `SchemaProfile` rather than absolute thresholds.
4. THE Reasoning_Agent SHALL produce output in a structured format containing: `summary` (1-2 sentence overview), `key_findings` (list of finding strings), `recommendations` (list of recommendation strings), and `caveats` (list of data quality or coverage warnings).
5. WHEN the execution result is empty or the confidence score is below 0.5, THE Reasoning_Agent SHALL include a caveat explaining the low confidence or missing data rather than generating recommendations from insufficient data.

---

### Requirement 8: Confidence Engine

**User Story:** As a data analyst, I want to see an accurate confidence score for each answer, so that I can tell the difference between a high-quality result and a best-effort approximation.

#### Acceptance Criteria

1. THE Confidence_Engine SHALL compute a composite confidence score as a weighted combination of: schema coverage score (fraction of requested metrics found in schema), ambiguity score (inverse of number of unresolved ambiguities), validation score (1.0 if no fatal errors, 0.5 if warnings only, 0.0 if fatal errors), and execution success score (1.0 if result is non-empty and matches expected shape, 0.0 otherwise).
2. THE Confidence_Engine SHALL return a score in the range [0.0, 1.0] with a breakdown object showing each component score and its weight.
3. WHEN schema coverage is below 0.5 (fewer than half the requested metrics were resolved), THE Confidence_Engine SHALL cap the maximum composite score at 0.6.
4. WHEN a multi-metric query with `optimization` or `recommendation` strategy produces a result with more than 3 unresolved metrics, THE Confidence_Engine SHALL reduce the composite score by 0.2.
5. THE Confidence_Engine SHALL replace both the existing `confidence_agent.py` and `confidence_scoring_agent.py`, consolidating all confidence logic into a single component.

---

### Requirement 9: Unsupported Query Handling

**User Story:** As a data analyst, I want the system to clearly explain why it cannot answer a question rather than crashing or hallucinating an answer, so that I understand what data is missing and how to fix it.

#### Acceptance Criteria

1. WHEN the Execution_Planner sets `execution_strategy` to `unsupported`, THE Analytics_System SHALL return an HTTP 200 response with a structured explanation in the `result` field and SHALL NOT return an HTTP 500 error.
2. THE unsupported response SHALL include: `unsupported_reason` (human-readable explanation of why the query cannot be executed), `missing_data` (list of data types or columns that would be needed), and `suggestions` (list of alternative questions the user could ask based on the available schema).
3. WHEN a `forecasting` query is received for a dataset with no date columns, THE Analytics_System SHALL respond with an unsupported explanation that names the missing column type and suggests trend or distribution queries as alternatives.
4. WHEN a query requests a metric that does not exist and cannot be approximated, THE Analytics_System SHALL return an unsupported explanation naming the missing metric rather than substituting an unrelated column.
5. THE Query_Verifier SHALL detect and handle all unsupported cases before any executor is invoked, ensuring zero 500 errors from unsupported query types.

---

### Requirement 10: Automated Evaluation Suite

**User Story:** As a developer, I want an automated evaluation suite with diverse natural-language questions, so that I can measure and track the correctness of the pipeline across multiple domains and query types.

#### Acceptance Criteria

1. THE Evaluation_Suite SHALL contain at least 150 natural-language test questions covering all 14 classified intent types and at least 5 different dataset domains (e.g., supply chain, e-commerce, music, finance, healthcare).
2. WHEN the Evaluation_Suite runs a test question, THE Evaluation_Suite SHALL assert: the classified intent matches the expected intent; the result shape matches the expected output type (scalar, tabular, ranking, time-series); the result is non-empty (or the query is correctly identified as unsupported); and no 500 errors are returned.
3. THE Evaluation_Suite SHALL compute and report a per-intent accuracy score and an overall pipeline accuracy score at the end of each run.
4. THE Evaluation_Suite SHALL include at least 20 adversarial questions designed to trigger the known bug where complex optimization queries fall through to a scalar sum, and SHALL assert that these questions are classified as `optimization` or `recommendation`, not `aggregation`.
5. THE Evaluation_Suite SHALL be executable as a standalone Python script (`tests/evaluation_suite.py`) that produces a summary report and exits with a non-zero code if overall accuracy falls below 80%.
6. THE Evaluation_Suite SHALL test round-trip consistency: for any question that produces a Pandas result, the equivalent SQL execution SHALL produce an equivalent result (within floating-point tolerance).

---

### Requirement 11: Modular Agent Architecture

**User Story:** As a developer, I want all agents to have clean, well-defined Pydantic interfaces and structured logging, so that the pipeline is maintainable, testable, and ready for future LLM upgrades.

#### Acceptance Criteria

1. EACH agent in the pipeline (Intent_Classifier, Schema_Agent, Metric_Extractor, Execution_Planner, Query_Verifier, Confidence_Engine, Reasoning_Agent) SHALL expose a single public method with typed inputs and outputs defined as Pydantic models.
2. EACH agent SHALL emit structured log entries at entry and exit using the existing `app/core/logger.py`, including: agent name, input summary, output summary, and elapsed time in milliseconds.
3. THE Analytics_System SHALL maintain backward-compatible FastAPI API contracts — the `/ask` and `/upload-dataset` endpoints SHALL preserve their existing request and response field names.
4. WHERE an agent depends on an LLM call, THE agent SHALL implement a graceful fallback that returns a degraded but valid result when Ollama is unavailable, rather than raising an unhandled exception.
5. THE refactored pipeline SHALL be runnable with the existing `run.py` entry point and Docker Compose configuration without requiring changes to the Streamlit UI or `dashboard/` directory.
6. EACH new agent module SHALL include a module-level docstring describing its responsibility, inputs, outputs, and any known limitations.
