"""
Domain Reasoning Agent
-----------------------
Generates dataset-context-aware explanations, recommendations, and insights.
No hardcoded business rules — everything is derived from the ExecutionPlan
and the actual result data.
"""
from __future__ import annotations

from typing import Any

from app.schemas.execution_plan import ExecutionPlan, QueryIntent
from app.core.logger import logger


class DomainReasoningAgent:

    def generate_explanation(self, plan: ExecutionPlan) -> str:
        """Human-readable explanation of what the system did."""
        if not plan.is_executable:
            return f"This query cannot be executed: {plan.unsupported_reason}"

        parts = []

        intent_phrases = {
            QueryIntent.AGGREGATION:    "computed an aggregation",
            QueryIntent.RANKING:        "ranked entities",
            QueryIntent.TREND:          "analysed trends over time",
            QueryIntent.STATISTICS:     "calculated descriptive statistics",
            QueryIntent.CORRELATION:    "analysed correlations",
            QueryIntent.COMPARISON:     "compared groups",
            QueryIntent.FILTERING:      "filtered rows",
            QueryIntent.SUMMARIZATION:  "summarised the dataset",
            QueryIntent.ANOMALY:        "looked for anomalies",
            QueryIntent.RECOMMENDATION: "generated evidence-based recommendations",
            QueryIntent.OPTIMIZATION:   "performed multi-signal optimisation scoring",
            QueryIntent.ROOT_CAUSE:     "investigated root causes",
            QueryIntent.VISUALIZATION:  "prepared data for visualisation",
            QueryIntent.FORECASTING:    "attempted forecasting",
            QueryIntent.UNKNOWN:        "processed the query",
        }
        parts.append(
            f"The system {intent_phrases.get(plan.intent, 'processed the query')}."
        )

        if plan.metrics and plan.aggregation:
            parts.append(
                f"It applied **{plan.aggregation.value}** to "
                f"**{', '.join(plan.metrics)}**."
            )
        elif plan.metrics:
            parts.append(f"It analysed **{', '.join(plan.metrics)}**.")

        if plan.group_by:
            parts.append(f"Results are grouped by **{', '.join(plan.group_by)}**.")

        if plan.time_band:
            tb = plan.time_band
            if tb.start and tb.end:
                parts.append(f"Data was filtered from **{tb.start}** to **{tb.end}**.")
            else:
                parts.append(
                    f"Data was grouped by **{tb.granularity}** "
                    f"using column **{tb.column}**."
                )

        if plan.filters:
            filter_descs = [
                f"{f.column} {f.operator} {f.value}" for f in plan.filters
            ]
            parts.append(f"Filters applied: {', '.join(filter_descs)}.")

        if plan.validation_issues:
            warnings = [
                i.message for i in plan.validation_issues
                if i.severity in ("warning", "info")
            ]
            if warnings:
                parts.append(f"Note: {'; '.join(warnings[:2])}.")

        return " ".join(parts)

    def generate_insights(self, plan: ExecutionPlan, result: Any) -> str:
        """
        Generate contextual insights from the result.
        Handles RecommendationResult objects directly.
        """
        if not plan.is_executable:
            return ""

        # RecommendationResult — return its decision brief
        from app.agents.recommendation_executor import RecommendationResult
        if isinstance(result, RecommendationResult):
            return result.decision_brief

        insights: list[str] = []

        if isinstance(result, list) and result and isinstance(result[0], dict):
            keys = list(result[0].keys())
            if len(keys) >= 2 and len(result) >= 2:
                top = result[0]
                bot = result[-1]
                xk, yk = keys[0], keys[1]
                top_val = top.get(yk)
                bot_val = bot.get(yk)
                top_name = top.get(xk, "top entry")
                bot_name = bot.get(xk, "bottom entry")

                if isinstance(top_val, (int, float)) and isinstance(bot_val, (int, float)):
                    if top_val != 0:
                        ratio = top_val / bot_val if bot_val else float("inf")
                        insights.append(
                            f"**{top_name}** leads with a {yk} of "
                            f"**{top_val:,.2f}**, which is "
                            f"**{ratio:.1f}x** that of **{bot_name}** ({bot_val:,.2f})."
                        )
            insights.append(f"The result contains **{len(result)} records**.")

        elif isinstance(result, (int, float)):
            if plan.metrics:
                insights.append(
                    f"The {plan.aggregation.value if plan.aggregation else 'value'} "
                    f"of **{plan.metrics[0]}** is **{result:,.2f}**."
                )

        if plan.intent == QueryIntent.CORRELATION and isinstance(result, list):
            insights.append(
                "Review the correlation matrix above for strongly positive (>0.7) "
                "or strongly negative (<-0.7) relationships."
            )

        return "  \n".join(insights)

    def generate_recommendations(self, plan: ExecutionPlan, result: Any) -> list[str]:
        """
        Return data-driven next-step recommendations.
        For RECOMMENDATION/OPTIMIZATION intents the RecommendationExecutor
        already produced the primary output; here we add analytical follow-ups.
        """
        recs: list[str] = []
        if not plan.is_executable or result is None:
            return recs

        schema = plan.dataset_schema
        if schema is None:
            return recs

        from app.agents.recommendation_executor import RecommendationResult
        if isinstance(result, RecommendationResult):
            if result.cards:
                top = result.cards[0]
                if schema.date_columns:
                    recs.append(
                        f"Analyse **{top.entity}** trend over time using "
                        f"**{schema.date_columns[0]}**."
                    )
                weak = [s for s in top.signals if s.contribution < 0.35]
                if weak:
                    recs.append(
                        f"Investigate why **{top.entity}** scores low on "
                        f"**{weak[0].column}** before acting."
                    )
            return recs

        if plan.intent == QueryIntent.RANKING:
            cat_cols = [c for c in schema.categorical_columns if c not in plan.group_by]
            if cat_cols:
                recs.append(f"Drill down by **{cat_cols[0]}** to refine these rankings.")
            if schema.date_columns:
                recs.append(
                    f"Analyse how these rankings change over time "
                    f"using **{schema.date_columns[0]}**."
                )

        elif plan.intent == QueryIntent.AGGREGATION and schema.date_columns and plan.metrics:
            recs.append(
                f"Explore the trend of **{plan.metrics[0]}** over time "
                f"using **{schema.date_columns[0]}**."
            )

        elif plan.intent == QueryIntent.STATISTICS and len(schema.numeric_columns) >= 2:
            recs.append(
                f"Run a correlation analysis between **{schema.numeric_columns[0]}** "
                f"and **{schema.numeric_columns[1]}** to discover relationships."
            )

        return recs
