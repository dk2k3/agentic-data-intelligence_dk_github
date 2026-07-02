"""
SQL Generator Agent
-------------------
Generates a SQL string from the SAME ExecutionPlan used by PandasExecutorAgent.
Guarantees consistent logic between SQL and Pandas.
"""
from __future__ import annotations

from app.schemas.execution_plan import AggregationFunc, ExecutionPlan, QueryIntent
from app.core.logger import logger


def _agg_sql(agg: AggregationFunc | None, col: str) -> str:
    if agg is None:
        return col
    a = agg.value.upper()
    return f"{a}({col})" if a != "COUNT" else f"COUNT({col})"


def _filter_sql(plan: ExecutionPlan) -> list[str]:
    clauses = []
    op_map = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=",
              "lt": "<", "lte": "<=", "contains": "LIKE"}
    for f in plan.filters:
        op = op_map.get(f.operator, "=")
        val = f"'{f.value}'" if isinstance(f.value, str) else str(f.value)
        if f.operator == "contains":
            val = f"'%{f.value}%'"
        clauses.append(f"{f.column} {op} {val}")
    if plan.time_band and plan.time_band.start and plan.time_band.end:
        tb = plan.time_band
        clauses.append(f"{tb.column} BETWEEN '{tb.start}' AND '{tb.end}'")
    return clauses


class SQLGeneratorAgent:

    def generate(self, plan: ExecutionPlan, table_name: str = "dataset") -> str:
        if not plan.is_executable:
            return f"-- Query not executable: {plan.unsupported_reason}"

        intent = plan.intent
        metric = plan.metrics[0] if plan.metrics else None
        gb = plan.group_by[0] if plan.group_by else None
        agg = plan.aggregation
        lim = plan.limit or 20
        order = "DESC" if plan.sort_order.value == "desc" else "ASC"

        where_clauses = _filter_sql(plan)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        try:
            if intent == QueryIntent.RANKING and gb and metric:
                agg_expr = _agg_sql(agg, metric)
                sql = (
                    f"SELECT {gb}, {agg_expr} AS {metric}\n"
                    f"FROM {table_name}\n"
                    f"{where_sql}\n"
                    f"GROUP BY {gb}\n"
                    f"ORDER BY {metric} {order}\n"
                    f"LIMIT {lim}"
                )

            elif intent == QueryIntent.TREND and plan.time_band:
                tb = plan.time_band
                gran_map = {"year": "YEAR", "month": "MONTH", "quarter": "QUARTER", "day": "DAY"}
                date_fn = gran_map.get(tb.granularity or "year", "YEAR")
                agg_expr = _agg_sql(agg, metric) if metric else "COUNT(*)"
                period = f"{date_fn}({tb.column})"
                sql = (
                    f"SELECT {period} AS period, {agg_expr} AS value\n"
                    f"FROM {table_name}\n"
                    f"{where_sql}\n"
                    f"GROUP BY {period}\n"
                    f"ORDER BY period"
                )

            elif intent == QueryIntent.STATISTICS and metric:
                sql = (
                    f"SELECT\n"
                    f"  COUNT({metric}) AS count,\n"
                    f"  AVG({metric}) AS mean,\n"
                    f"  MIN({metric}) AS min,\n"
                    f"  MAX({metric}) AS max\n"
                    f"FROM {table_name}\n"
                    f"{where_sql}"
                )

            elif intent == QueryIntent.AGGREGATION:
                if gb and metric:
                    agg_expr = _agg_sql(agg, metric)
                    sql = (
                        f"SELECT {gb}, {agg_expr} AS {metric}\n"
                        f"FROM {table_name}\n"
                        f"{where_sql}\n"
                        f"GROUP BY {gb}\n"
                        f"ORDER BY {metric} {order}\n"
                        f"LIMIT {lim}"
                    )
                elif metric:
                    agg_expr = _agg_sql(agg, metric)
                    sql = f"SELECT {agg_expr} AS result FROM {table_name} {where_sql}"
                else:
                    sql = f"SELECT COUNT(*) AS total_rows FROM {table_name} {where_sql}"

            else:
                cols = "*"
                if plan.metrics or plan.group_by:
                    col_list = list(dict.fromkeys(plan.group_by + plan.metrics))
                    cols = ", ".join(col_list) if col_list else "*"
                sql = (
                    f"SELECT {cols}\n"
                    f"FROM {table_name}\n"
                    f"{where_sql}\n"
                    f"LIMIT {lim}"
                )

            return sql.strip()

        except Exception as e:
            logger.error(f"SQLGeneratorAgent error: {e}")
            return f"-- SQL generation failed: {e}"
