import pandas as pd
from app.schemas.final_reasoning_schema import IntentType
from app.agents.query_planner import QueryPlan


def generate_pandas_from_plan(plan: QueryPlan) -> str:
    """
    Generate SAFE, EXECUTABLE Pandas code from a QueryPlan.
    The generated code MUST assign output to variable `result`.
    """

    lines: list[str] = []

    # --------------------------------------------------
    # TIME FILTER
    # --------------------------------------------------
    if plan.time:
        col = plan.time.column
        start = plan.time.start
        end = plan.time.end
        lines.append(
            f"df = df[pd.to_datetime(df['{col}']).between('{start}', '{end}')]"
        )

    # --------------------------------------------------
    # SCALAR
    # --------------------------------------------------
    if plan.intent == IntentType.SCALAR:
        if plan.metric and plan.aggregation:
            lines.append(
                f"result = df['{plan.metric}'].{plan.aggregation}()"
            )
        elif plan.metric:
            lines.append(
                f"result = df['{plan.metric}']"
            )
        else:
            lines.append("result = len(df)")
        return "\n".join(lines)

    # --------------------------------------------------
    # TABULAR
    # --------------------------------------------------
    if plan.intent == IntentType.TABULAR:
        if plan.group_by and plan.metric and plan.aggregation:
            gb = plan.group_by[0]
            lines.append(
                "result = ("
                f"df.groupby('{gb}')"
                f"['{plan.metric}']"
                f".{plan.aggregation}()"
                ".reset_index()"
                ")"
            )
        else:
            lines.append("result = df.head(20)")
        return "\n".join(lines)

    # --------------------------------------------------
    # RANKING (FIXED + SAFE)
    # --------------------------------------------------
    if plan.intent == IntentType.RANKING:

        if not plan.group_by:
            raise ValueError("Ranking requires group_by")

        if not plan.metric:
            raise ValueError("Ranking requires metric")

        aggregation = plan.aggregation or "sum"
        limit = plan.limit or 5

        gb = plan.group_by[0]
        metric = plan.metric

        lines.append(
            "result = ("
            f"df.groupby('{gb}')"
            f"['{metric}']"
            f".{aggregation}()"
            ".reset_index()"
            f".sort_values('{metric}', ascending=False)"
            f".head({limit})"
            ")"
        )
        return "\n".join(lines)

    # --------------------------------------------------
    # TIME SERIES
    # --------------------------------------------------
    if plan.intent == IntentType.TIME_SERIES:

        if not plan.time:
            raise ValueError("Time-series requires time configuration")

        if not plan.metric:
            raise ValueError("Time-series requires metric")

        col = plan.time.column
        granularity = plan.time.granularity or "year"
        aggregation = plan.aggregation or "sum"

        freq_map = {
            "year": "Y",
            "month": "M",
            "day": "D"
        }
        freq = freq_map.get(granularity, "Y")

        lines.append(
            f"df['_time'] = pd.to_datetime(df['{col}']).dt.to_period('{freq}')"
        )
        lines.append(
            "result = ("
            "df.groupby('_time')"
            f"['{plan.metric}']"
            f".{aggregation}()"
            ".reset_index()"
            ")"
        )
        return "\n".join(lines)

    raise ValueError(f"Unsupported intent: {plan.intent}")
