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
    # TIME FILTER (SCALAR only — time-series manages its own filtering)
    # --------------------------------------------------
    if plan.time and plan.intent not in (IntentType.TIME_SERIES,):
        col = plan.time.column
        start = plan.time.start
        end = plan.time.end
        if col and start and end:
            lines.append(
                f"df = df[pd.to_datetime(df['{col}'], errors='coerce').between('{start}', '{end}')]"
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
    # RANKING 
    # --------------------------------------------------
    if plan.intent == IntentType.RANKING:

        # Safe fallbacks — self_correction_agent should have filled these,
        # but guard here too so we never raise a 500.
        if not plan.group_by or not plan.metric:
            lines.append("result = df.head(10)")
            return "\n".join(lines)

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

        if not plan.metric:
            # No metric — fall back to row count over time
            fallback_code = (
                "_date_cols = [c for c in df.columns "
                "if 'date' in c.lower() or 'time' in c.lower() or 'year' in c.lower()]\n"
                "if not _date_cols:\n"
                "    result = pd.DataFrame()\n"
                "else:\n"
                "    _col = _date_cols[0]\n"
                "    df['_time'] = pd.to_datetime(df[_col], errors='coerce').dt.to_period('Y')\n"
                "    result = df.groupby('_time').size().reset_index(name='count')\n"
            )
            lines.append(fallback_code)
            return "\n".join(lines)

        aggregation = plan.aggregation or "sum"

        # Resolve time column and granularity from plan or fall back to
        # the first date-like column in the dataframe (detected at runtime).
        if plan.time and plan.time.column:
            col = plan.time.column
            granularity = plan.time.granularity or "year"
        else:
            # No time config — detect date column at runtime inside the
            # generated code so we don't raise at generation time.
            fallback_code = (
                f"_date_cols = [c for c in df.columns "
                f"if 'date' in c.lower() or 'time' in c.lower() or 'year' in c.lower()]\n"
                f"if not _date_cols:\n"
                f"    result = pd.DataFrame()\n"
                f"else:\n"
                f"    _col = _date_cols[0]\n"
                f"    df['_time'] = pd.to_datetime(df[_col], errors='coerce').dt.to_period('Y')\n"
                f"    result = df.groupby('_time')['{plan.metric}'].{aggregation}().reset_index()\n"
            )
            lines.append(fallback_code)
            return "\n".join(lines)

        freq_map = {
            "year": "Y",
            "month": "M",
            "day": "D"
        }
        freq = freq_map.get(granularity, "Y")

        # Apply time filter only when explicit start/end were given
        if plan.time and plan.time.start and plan.time.end:
            lines.append(
                f"df = df[pd.to_datetime(df['{col}'], errors='coerce')"
                f".between('{plan.time.start}', '{plan.time.end}')]"
            )

        lines.append(
            f"df['_time'] = pd.to_datetime(df['{col}'], errors='coerce').dt.to_period('{freq}')"
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
