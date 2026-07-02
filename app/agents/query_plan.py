from typing import Optional, List, Dict, Any
from app.schemas.final_reasoning_schema import IntentType, TimePlan


class QueryPlan:
    """
    Canonical query plan object passed across agents.
    """

    def __init__(
        self,
        intent: IntentType,
        metric: Optional[str] = None,
        aggregation: Optional[str] = None,
        entity: Optional[str] = None,
        time: Optional[TimePlan] = None,
        group_by: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        chart_type: Optional[str] = None,
        limit: Optional[int] = None,  # ✅ ADD THIS
    ):
        self.intent = intent
        self.metric = metric
        self.aggregation = aggregation
        self.entity = entity
        self.time = time
        self.group_by = group_by or []
        self.filters = filters or {}
        self.chart_type = chart_type
        self.limit = limit  # ✅ STORE IT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "metric": self.metric,
            "aggregation": self.aggregation,
            "entity": self.entity,
            "time": self.time.to_dict() if self.time else None,
            "group_by": self.group_by,
            "filters": self.filters,
            "chart_type": self.chart_type,
            "limit": self.limit,  # ✅ SERIALIZE IT
        }
