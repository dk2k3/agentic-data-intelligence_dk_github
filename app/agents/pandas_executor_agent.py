"""
Pandas Executor Agent
---------------------
Consumes an ExecutionPlan and produces a safe pandas code string + executes it.
All routing logic is driven entirely by the ExecutionPlan — no hardcoded columns.
"""
from __future__ import annotations

from typing import Any, Tuple

import pandas as pd

from app.schemas.execution_plan import (
    AggregationFunc,
    ExecutionPlan,
    FilterCondition,
    QueryIntent,
)
from app.core.logger import logger


# ---------------------------------------------------------------------------
# Safe execution harness
# ---------------------------------------------------------------------------

def _safe_exec(df: pd.DataFrame, code: str) -> Any:
    env = {"df": df.copy(), "pd": pd, "result": None}
    exec(code, {"__builtins__": {"len": len, "range": range, "list": list,
                                  "str": str, "int": int, "float": float,
                                  "bool": bool, "None": None}}, env)
    return env.get("result")


# ---------------------------------------------------------------------------
# Code generators per executor type
# ---------------------------------------------------------------------------

def _filter_code(filters: list[FilterCondition]) -> list[str]:
    lines = []
    op_map = {"eq": "==", "ne": "!=", "gt": ">", "gte": ">=",
              "lt": "<", "lte": "<=", "contains": ".str.contains"}
    for f in filters:
        op = op_map.get(f.operator, "==")
        val = f"'{f.value}'" if isinstance(f.value, str) else f.value
        if f.operator == "contains":
            lines.append(f"df = df[df['{f.column}'].astype(str).str.contains({val}, na=False)]")
        else:
            lines.append(f"df = df[df['{f.column}'] {op} {val}]")
    return lines


def _time_filter_code(plan: ExecutionPlan) -> list[str]:
    if not plan.time_band:
        return []
    tb = plan.time_band
    col = tb.column
    lines = [f"df['{col}'] = pd.to_datetime(df['{col}'], errors='coerce')"]
    if tb.start and tb.end:
        lines.append(f"df = df[df['{col}'].between('{tb.start}', '{tb.end}')]")
    return lines


def _agg_str(agg: AggregationFunc | None) -> str:
    return agg.value if agg else "sum"


class PandasExecutorAgent:

    def generate_code(self, plan: ExecutionPlan) -> str:
        lines: list[str] = []

        # Apply filters first
        lines += _filter_code(plan.filters)
        lines += _time_filter_code(plan)

        intent = plan.intent

        # ---- Aggregation / Scalar ----------------------------------------
        if intent == QueryIntent.AGGREGATION:
            lines += self._aggregation_code(plan)

        # ---- Ranking --------------------------------------------------------
        elif intent == QueryIntent.RANKING:
            lines += self._ranking_code(plan)

        # ---- Trend / Time-series --------------------------------------------
        elif intent == QueryIntent.TREND:
            lines += self._trend_code(plan)

        # ---- Statistics -----------------------------------------------------
        elif intent == QueryIntent.STATISTICS:
            lines += self._statistics_code(plan)

        # ---- Correlation ----------------------------------------------------
        elif intent == QueryIntent.CORRELATION:
            lines += self._correlation_code(plan)

        # ---- Comparison -----------------------------------------------------
        elif intent == QueryIntent.COMPARISON:
            lines += self._comparison_code(plan)

        # ---- Filtering ------------------------------------------------------
        elif intent == QueryIntent.FILTERING:
            lines += self._filtering_code(plan)

        # ---- Summarization / Root-cause / Visualization --------------------
        elif intent in (QueryIntent.SUMMARIZATION, QueryIntent.ANOMALY,
                        QueryIntent.ROOT_CAUSE, QueryIntent.VISUALIZATION):
            lines += self._tabular_code(plan)

        # ---- Recommendation / Optimization — delegated separately ----------
        # These intents are handled by RecommendationExecutor.
        # Return a sentinel so the caller knows to route differently.
        elif intent in (QueryIntent.RECOMMENDATION, QueryIntent.OPTIMIZATION):
            lines += self._recommendation_preview_code(plan)

        # ---- Forecasting (should be caught by verifier) --------------------
        else:
            lines.append("result = df.head(20)")

        return "\n".join(lines) if lines else "result = df.head(20)"

    def execute(self, df: pd.DataFrame, plan: ExecutionPlan) -> Tuple[Any, str]:
        """Returns (result, code_string)."""
        code = self.generate_code(plan)
        logger.debug(f"Generated pandas code:\n{code}")
        try:
            result = _safe_exec(df, code)
            return result, code
        except Exception as e:
            logger.error(f"Pandas execution failed: {e}\nCode:\n{code}")
            # Graceful fallback
            return df.head(20), code

    # ------------------------------------------------------------------
    # Executor helpers
    # ------------------------------------------------------------------

    def _aggregation_code(self, plan: ExecutionPlan) -> list[str]:
        lines = []
        agg = _agg_str(plan.aggregation)
        metric = plan.metrics[0] if plan.metrics else None

        if plan.group_by and metric:
            gb = plan.group_by[0]
            order = "False" if plan.sort_order.value == "desc" else "True"
            lim = plan.limit or 20
            lines.append(
                f"result = (df.groupby('{gb}')['{metric}'].{agg}()"
                f".reset_index().sort_values('{metric}', ascending={order}).head({lim}))"
            )
        elif metric:
            if agg == "count":
                lines.append(f"result = df['{metric}'].count()")
            else:
                lines.append(f"result = df['{metric}'].{agg}()")
        else:
            lines.append("result = len(df)")
        return lines

    def _ranking_code(self, plan: ExecutionPlan) -> list[str]:
        lines = []
        metric = plan.metrics[0] if plan.metrics else None
        gb = plan.group_by[0] if plan.group_by else None
        agg = _agg_str(plan.aggregation)
        lim = plan.limit or 10
        order = "False" if plan.sort_order.value == "desc" else "True"

        if gb and metric:
            lines.append(
                f"result = (df.groupby('{gb}')['{metric}'].{agg}()"
                f".reset_index().sort_values('{metric}', ascending={order}).head({lim}))"
            )
        else:
            lines.append(f"result = df.head({lim})")
        return lines

    def _trend_code(self, plan: ExecutionPlan) -> list[str]:
        lines = []
        metric = plan.metrics[0] if plan.metrics else None
        agg = _agg_str(plan.aggregation)

        if plan.time_band and plan.time_band.column:
            col = plan.time_band.column
            gran_map = {"year": "Y", "month": "M", "quarter": "Q", "day": "D"}
            freq = gran_map.get(plan.time_band.granularity or "year", "Y")
            lines.append(f"df['_period'] = df['{col}'].dt.to_period('{freq}')")
            if metric:
                lines.append(
                    f"result = df.groupby('_period')['{metric}'].{agg}().reset_index()"
                )
            else:
                lines.append("result = df.groupby('_period').size().reset_index(name='count')")
        else:
            # No date column — return tabular
            lines.append("result = df.head(20)")
        return lines

    def _statistics_code(self, plan: ExecutionPlan) -> list[str]:
        if plan.metrics:
            cols = plan.metrics
        else:
            cols = plan.dataset_schema.numeric_columns[:5] if plan.dataset_schema else []

        if not cols:
            return ["result = df.describe()"]

        col_list = str(cols)
        return [f"result = df[{col_list}].describe().T.reset_index()"]

    def _correlation_code(self, plan: ExecutionPlan) -> list[str]:
        schema = plan.dataset_schema
        if schema and len(schema.numeric_columns) >= 2:
            if plan.metrics and len(plan.metrics) >= 2:
                cols = plan.metrics[:2]
            else:
                cols = schema.numeric_columns[:5]
            col_list = str(cols)
            return [f"result = df[{col_list}].corr().reset_index()"]
        return ["result = df.corr().reset_index()"]

    def _comparison_code(self, plan: ExecutionPlan) -> list[str]:
        if plan.group_by and plan.metrics:
            return self._aggregation_code(plan)
        return self._tabular_code(plan)

    def _filtering_code(self, plan: ExecutionPlan) -> list[str]:
        # Filters already applied at top; just return head
        lim = plan.limit or 50
        return [f"result = df.head({lim})"]

    def _tabular_code(self, plan: ExecutionPlan) -> list[str]:
        lim = plan.limit or 20
        if plan.metrics:
            cols = (plan.group_by + plan.metrics)[:8]
            col_list = str(cols)
            return [f"result = df[{col_list}].head({lim})"]
        return [f"result = df.head({lim})"]

    def _recommendation_preview_code(self, plan: ExecutionPlan) -> list[str]:
        """
        Lightweight preview used when RecommendationExecutor handles the full logic.
        Returns the raw grouped signals so the pandas code block is still meaningful.
        """
        schema = plan.dataset_schema
        entity_col = plan.group_by[0] if plan.group_by else (
            schema.categorical_columns[0] if schema and schema.categorical_columns else None
        )
        signal_cols = plan.metrics or (schema.numeric_columns[:4] if schema else [])

        if not entity_col or not signal_cols:
            return ["result = df.head(20)"]

        col_list = str(signal_cols)
        return [
            f"_signals = {col_list}",
            f"_grouped = df.groupby('{entity_col}')[_signals].mean().reset_index()",
            f"for _col in _signals:",
            f"    _mn, _mx = _grouped[_col].min(), _grouped[_col].max()",
            f"    _grouped[_col + '_norm'] = (_grouped[_col] - _mn) / (_mx - _mn + 1e-9)",
            f"_norm_cols = [c + '_norm' for c in _signals]",
            f"_grouped['composite_score'] = _grouped[_norm_cols].mean(axis=1) * 100",
            f"result = _grouped.sort_values('composite_score', ascending=False)",
        ]
