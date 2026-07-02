from typing import Any, Dict
import pandas as pd

from app.schemas.final_reasoning_schema import IntentType
from app.agents.query_plan import QueryPlan

MAX_CORRECTIONS = 2


def needs_correction(result: Any, intent: IntentType, plan=None) -> bool:
    """
    Decide whether execution output violates intent semantics.
    This function must be conservative.
    """

    if result is None:
        return True

    if intent == IntentType.SCALAR:
        if isinstance(result, (pd.DataFrame, pd.Series)) and len(result) > 1:
            return True

    if intent == IntentType.RANKING:
        if isinstance(result, pd.DataFrame) and len(result) == 0:
            return True

    if intent == IntentType.TIME_SERIES:
        if isinstance(result, pd.DataFrame) and len(result) == 0:
            return True

    return False


def apply_self_correction(plan: QueryPlan, schema: Dict) -> QueryPlan:
    """
    Deterministically repair an incomplete QueryPlan.
    This function MUST NOT raise.
    """

    # --------------------------------------------------
    # SCALAR FIXES
    # --------------------------------------------------
    if plan.intent == IntentType.SCALAR:
        plan.group_by = []
        if not plan.aggregation:
            plan.aggregation = "count" if plan.metric is None else "sum"
        return plan

    # --------------------------------------------------
    # RANKING FIXES 
    # --------------------------------------------------
    if plan.intent == IntentType.RANKING:

        # group_by → first categorical column
        if not plan.group_by:
            for col, dtype in schema.items():
                if dtype == "object":
                    plan.group_by = [col]
                    break

        # metric → first numeric column
        if not plan.metric:
            for col, dtype in schema.items():
                if dtype in {"int64", "float64"}:
                    plan.metric = col
                    break

        # aggregation → sum
        if not plan.aggregation:
            plan.aggregation = "sum"

        # limit → safe default
        if not plan.limit:
            plan.limit = 5

        return plan

    # --------------------------------------------------
    # TABULAR FIXES
    # --------------------------------------------------
    if plan.intent == IntentType.TABULAR:
        if not plan.group_by:
            plan.group_by = []
        return plan

    # --------------------------------------------------
    # TIME SERIES FIXES
    # --------------------------------------------------
    if plan.intent == IntentType.TIME_SERIES:
        # If time column is missing, try to find one from the schema
        if not plan.time or not plan.time.column:
            from app.schemas.final_reasoning_schema import TimePlan
            date_col = None
            for col, dtype in schema.items():
                if "date" in col.lower() or "time" in col.lower() or "datetime" in dtype.lower():
                    date_col = col
                    break
            if date_col:
                plan.time = TimePlan(column=date_col, granularity="year")
            else:
                # No date column at all — downgrade to TABULAR so we don't crash
                plan.intent = IntentType.TABULAR
        if not plan.metric:
            for col, dtype in schema.items():
                if dtype in {"int64", "float64"}:
                    plan.metric = col
                    break
        if not plan.aggregation:
            plan.aggregation = "sum"
        return plan

    return plan
