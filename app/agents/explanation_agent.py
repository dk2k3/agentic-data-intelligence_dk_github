from app.schemas.final_reasoning_schema import IntentType


def generate_explanation(plan) -> str:
    """
    Generate a human-readable explanation
    aligned with the canonical QueryPlan.
    """

    parts = []

    # --------------------------------------------------
    # INTENT
    # --------------------------------------------------
    if plan.intent == IntentType.SCALAR:
        parts.append("The system interpreted your question as a **scalar** query.")
    elif plan.intent == IntentType.RANKING:
        parts.append("The system interpreted your question as a **ranking** query.")
    elif plan.intent == IntentType.TIME_SERIES:
        parts.append("The system interpreted your question as a **time-series** query.")
    elif plan.intent == IntentType.TABULAR:
        parts.append("The system interpreted your question as a **tabular** query.")
    else:
        parts.append("The system interpreted your question as an analytical query.")

    # --------------------------------------------------
    # METRIC + AGGREGATION
    # --------------------------------------------------
    if plan.metric and plan.aggregation:
        parts.append(
            f"It computed the **{plan.aggregation}** of **{plan.metric}**."
        )
    elif plan.metric:
        parts.append(f"It analyzed the values of **{plan.metric}**.")

    # --------------------------------------------------
    # GROUPING
    # --------------------------------------------------
    if plan.group_by:
        groups = ", ".join(plan.group_by)
        parts.append(f"The results are grouped by **{groups}**.")

    # --------------------------------------------------
    # TIME FILTER
    # --------------------------------------------------
    if plan.time:
        if plan.time.start and plan.time.end:
            parts.append(
                f"The data was filtered from **{plan.time.start}** to **{plan.time.end}**."
            )

    # --------------------------------------------------
    # CHART
    # --------------------------------------------------
    if plan.chart_type:
        parts.append(f"A **{plan.chart_type} chart** was selected for visualization.")

    return " ".join(parts)
