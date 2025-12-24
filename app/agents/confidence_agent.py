from typing import Any

from app.schemas.final_reasoning_schema import IntentType


def calculate_confidence(plan, result_data: Any) -> float:
    """
    Calculate a confidence score (0.0 – 1.0) based on:
    - Plan completeness
    - Intent-result compatibility
    - Output quality
    """

    score = 1.0

    # --------------------------------------------------
    # PLAN COMPLETENESS
    # --------------------------------------------------
    if plan.intent in {IntentType.SCALAR, IntentType.RANKING, IntentType.TIME_SERIES}:
        if not plan.metric and plan.intent != IntentType.SCALAR:
            score -= 0.15

    if plan.intent == IntentType.RANKING and not plan.group_by:
        score -= 0.2

    if plan.intent == IntentType.TIME_SERIES and not plan.time:
        score -= 0.2

    # --------------------------------------------------
    # RESULT QUALITY
    # --------------------------------------------------
    # Scalar
    if isinstance(result_data, (int, float, bool)):
        pass

    # Tabular / ranking / time-series
    elif isinstance(result_data, list):
        if len(result_data) == 0:
            score -= 0.3

    # Unknown or unsafe
    else:
        score -= 0.25

    # --------------------------------------------------
    # CLAMP
    # --------------------------------------------------
    score = max(0.0, min(1.0, score))
    return round(score, 2)
