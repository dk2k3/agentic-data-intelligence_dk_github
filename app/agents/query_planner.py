from typing import Dict, Optional, List

from app.agents.metric_resolver import MetricResolver
from app.agents.time_resolver import TimeResolver
from app.agents.query_plan import QueryPlan
from app.schemas.final_reasoning_schema import IntentType


# -------------------------------
# Helper utilities
# -------------------------------

def is_id_column(col: str) -> bool:
    col_l = col.lower()
    return (
        col_l.endswith("id")
        or col_l == "id"
        or "uuid" in col_l
        or "hash" in col_l
    )


def is_categorical(dtype: str) -> bool:
    return dtype == "object"


def semantic_match(col: str, keywords: List[str]) -> bool:
    col_l = col.lower()
    return any(k in col_l for k in keywords)


# -------------------------------
# Main planner
# -------------------------------

def build_query_plan(question: str, schema: Dict) -> QueryPlan:
    q = question.lower()

    # --------------------------------------------------
    # DEFAULTS
    # --------------------------------------------------
    intent = IntentType.SCALAR
    metric: Optional[str] = None
    aggregation: Optional[str] = None
    entity: Optional[str] = None
    group_by: List[str] = []
    filters = {}
    chart_type = None
    limit = None

    # --------------------------------------------------
    # INTENT DETECTION
    # --------------------------------------------------
    if any(k in q for k in ["top", "most", "highest", "lowest", "best"]):
        intent = IntentType.RANKING
        limit = 5

    elif any(k in q for k in ["trend", "over time", "per year", "per month"]):
        intent = IntentType.TIME_SERIES

    # --------------------------------------------------
    # AGGREGATION DETECTION
    # --------------------------------------------------
    if any(k in q for k in ["average", "mean"]):
        aggregation = "mean"

    elif any(k in q for k in ["total", "sum", "revenue", "sales", "streams"]):
        aggregation = "sum"

    elif any(k in q for k in ["count", "how many", "number of"]):
        aggregation = "count"

    # --------------------------------------------------
    # METRIC RESOLUTION
    # --------------------------------------------------
    metric = MetricResolver(schema).resolve_metric_from_question(q)

    # --------------------------------------------------
    #  SEMANTIC ENTITY RESOLUTION 
    # --------------------------------------------------
    if intent in {IntentType.RANKING, IntentType.TABULAR}:

        ENTITY_KEYWORDS = {
            "artist": ["artist"],
            "genre": ["genre"],
            "track": ["track", "song", "title", "name"],
            "product": ["product", "item"],
            "category": ["category"],
            "seller": ["seller", "vendor"],
            "brand": ["brand"],
            "customer": ["customer", "client"],
        }

        #  Try question → schema semantic mapping
        for entity_name, keywords in ENTITY_KEYWORDS.items():
            if any(k in q for k in keywords):
                for col, dtype in schema.items():
                    if (
                        is_categorical(dtype)
                        and not is_id_column(col)
                        and semantic_match(col, keywords)
                    ):
                        group_by = [col]
                        entity = entity_name
                        break
            if group_by:
                break

        #  Safe fallback (best categorical, non-ID)
        if not group_by:
            for col, dtype in schema.items():
                if is_categorical(dtype) and not is_id_column(col):
                    group_by = [col]
                    break

    # --------------------------------------------------
    # TIME RESOLUTION
    # --------------------------------------------------
    time_plan = TimeResolver(schema).resolve(question)

    # --------------------------------------------------
    #  RANKING SAFETY GUARANTEES
    # --------------------------------------------------
    if intent == IntentType.RANKING:
        if not metric:
            for col, dtype in schema.items():
                if dtype in {"int64", "float64"}:
                    metric = col
                    break

        if not aggregation:
            aggregation = "sum"

        chart_type = "bar"

    # --------------------------------------------------
    # TIME SERIES DEFAULTS
    # --------------------------------------------------
    if intent == IntentType.TIME_SERIES:
        if not aggregation:
            aggregation = "sum"
        chart_type = "line"

    # --------------------------------------------------
    # SCALAR CLEANUP
    # --------------------------------------------------
    if intent == IntentType.SCALAR:
        group_by = []
        chart_type = None

    return QueryPlan(
        intent=intent,
        metric=metric,
        aggregation=aggregation,
        entity=entity,
        time=time_plan,
        group_by=group_by,
        filters=filters,
        chart_type=chart_type,
        limit=limit,
    )
