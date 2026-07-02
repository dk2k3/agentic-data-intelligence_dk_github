from enum import Enum
from typing import Optional, List
from pydantic import BaseModel


# --------------------------------------------------
# INTENT ENUM
# --------------------------------------------------
class IntentType(str, Enum):
    SCALAR = "scalar"
    TABULAR = "tabular"
    RANKING = "ranking"
    TIME_SERIES = "time_series"
    BOOLEAN = "boolean"


# --------------------------------------------------
# TIME PLAN
# --------------------------------------------------
class TimePlan(BaseModel):
    column: Optional[str] = None
    granularity: Optional[str] = None  # day, month, year
    start: Optional[str] = None
    end: Optional[str] = None

    def to_dict(self):
        return {
            "column": self.column,
            "granularity": self.granularity,
            "start": self.start,
            "end": self.end,
        }


# --------------------------------------------------
# FINAL REASONING SCHEMA (FOR LLM OUTPUTS)
# --------------------------------------------------
class FinalReasoningSchema(BaseModel):
    intent: IntentType
    metric: Optional[str] = None
    aggregation: Optional[str] = None
    entity: Optional[str] = None
    group_by: Optional[List[str]] = None
    time: Optional[TimePlan] = None
    filters: Optional[dict] = None
    chart_type: Optional[str] = None
