"""
Unified Execution Plan — the single contract consumed by ALL executors.
Every agent reads from and writes to this model. No agent uses raw dicts.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class QueryIntent(str, Enum):
    AGGREGATION     = "aggregation"
    COMPARISON      = "comparison"
    RANKING         = "ranking"
    FILTERING       = "filtering"
    TREND           = "trend"
    CORRELATION     = "correlation"
    ANOMALY         = "anomaly"
    STATISTICS      = "statistics"
    RECOMMENDATION  = "recommendation"
    OPTIMIZATION    = "optimization"
    SUMMARIZATION   = "summarization"
    FORECASTING     = "forecasting"
    ROOT_CAUSE      = "root_cause"
    VISUALIZATION   = "visualization"
    UNKNOWN         = "unknown"


class AggregationFunc(str, Enum):
    SUM     = "sum"
    MEAN    = "mean"
    MEDIAN  = "median"
    COUNT   = "count"
    MIN     = "min"
    MAX     = "max"
    STD     = "std"
    VAR     = "var"


class SortOrder(str, Enum):
    ASC  = "asc"
    DESC = "desc"


class ChartType(str, Enum):
    BAR       = "bar"
    LINE      = "line"
    PIE       = "pie"
    SCATTER   = "scatter"
    HISTOGRAM = "histogram"
    HEATMAP   = "heatmap"
    AUTO      = "auto"
    NONE      = "none"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ColumnSemantics(str, Enum):
    IDENTIFIER  = "identifier"
    CATEGORICAL = "categorical"
    NUMERIC     = "numeric"
    DATE        = "date"
    TEXT        = "text"
    BOOLEAN     = "boolean"
    TARGET      = "target"
    UNKNOWN     = "unknown"


class SchemaColumn(BaseModel):
    name: str
    dtype: str
    semantics: ColumnSemantics
    n_unique: int = 0
    n_missing: int = 0
    sample_values: List[Any] = Field(default_factory=list)


class DatasetSchema(BaseModel):
    columns: List[SchemaColumn] = Field(default_factory=list)
    row_count: int = 0
    date_columns: List[str] = Field(default_factory=list)
    numeric_columns: List[str] = Field(default_factory=list)
    categorical_columns: List[str] = Field(default_factory=list)
    identifier_columns: List[str] = Field(default_factory=list)
    potential_targets: List[str] = Field(default_factory=list)

    def col(self, name: str) -> Optional[SchemaColumn]:
        for c in self.columns:
            if c.name == name:
                return c
        return None

    def has_column(self, name: str) -> bool:
        return any(c.name == name for c in self.columns)


class FilterCondition(BaseModel):
    column: str
    operator: str          # eq, ne, gt, gte, lt, lte, in, contains
    value: Any


class TimeBand(BaseModel):
    column: str
    start: Optional[str] = None
    end: Optional[str] = None
    granularity: str = "year"  # day / month / quarter / year


class ValidationIssue(BaseModel):
    severity: str           # error / warning / info
    message: str
    field: Optional[str] = None


# ---------------------------------------------------------------------------
# The Unified Execution Plan
# ---------------------------------------------------------------------------

class ExecutionPlan(BaseModel):
    # ---- intent ----
    intent: QueryIntent = QueryIntent.UNKNOWN
    original_question: str = ""

    # ---- what to measure ----
    metrics: List[str] = Field(default_factory=list)          # validated column names
    aggregation: Optional[AggregationFunc] = None

    # ---- how to slice ----
    group_by: List[str] = Field(default_factory=list)
    filters: List[FilterCondition] = Field(default_factory=list)
    time_band: Optional[TimeBand] = None
    limit: Optional[int] = None
    sort_order: SortOrder = SortOrder.DESC

    # ---- visualization ----
    chart_type: ChartType = ChartType.AUTO

    # ---- metadata ----
    dataset_schema: Optional[DatasetSchema] = None
    validation_issues: List[ValidationIssue] = Field(default_factory=list)
    is_executable: bool = True
    unsupported_reason: Optional[str] = None

    # ---- confidence inputs (filled by ConfidenceEngine) ----
    schema_coverage: float = 1.0      # fraction of requested columns found
    ambiguity_score: float = 0.0      # 0=clear, 1=very ambiguous
    complexity_score: float = 0.0     # 0=simple, 1=very complex

    def has_errors(self) -> bool:
        return any(v.severity == "error" for v in self.validation_issues)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude={"dataset_schema"})
