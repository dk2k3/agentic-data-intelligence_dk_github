"""
Execution Planner
-----------------
Assembles an ExecutionPlan from intent + extracted components.
Handles unsupported-query detection (forecasting without dates, etc.)
"""
from __future__ import annotations

from app.agents.intent_classifier_agent import IntentClassifierAgent
from app.agents.metric_entity_extractor import MetricEntityExtractor
from app.schemas.execution_plan import (
    AggregationFunc,
    ChartType,
    DatasetSchema,
    ExecutionPlan,
    QueryIntent,
    SortOrder,
    ValidationIssue,
)
from app.core.logger import logger


_INTENT_CLASSIFIER = IntentClassifierAgent()
_EXTRACTOR = MetricEntityExtractor()


# ---------------------------------------------------------------------------
# Unsupported-query guard table
# ---------------------------------------------------------------------------

_UNSUPPORTED_GUARDS: list[tuple[QueryIntent, str, str]] = [
    (
        QueryIntent.FORECASTING,
        "date_columns",
        "Forecasting requires at least one date/time column, "
        "but none were found in this dataset.",
    ),
    (
        QueryIntent.TREND,
        "date_columns",
        "Trend analysis requires a date/time column, "
        "but none were found in this dataset.",
    ),
    (
        QueryIntent.CORRELATION,
        "numeric_columns_2",
        "Correlation requires at least two numeric columns, "
        "but fewer than two were found.",
    ),
]


def _check_unsupported(intent: QueryIntent, schema: DatasetSchema) -> str | None:
    for guard_intent, requirement, message in _UNSUPPORTED_GUARDS:
        if intent != guard_intent:
            continue
        if requirement == "date_columns" and not schema.date_columns:
            return message
        if requirement == "numeric_columns_2" and len(schema.numeric_columns) < 2:
            return message
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ExecutionPlanner:
    """
    Produces a fully validated ExecutionPlan from question + DatasetSchema.
    """

    def build(self, question: str, schema: DatasetSchema) -> ExecutionPlan:
        logger.info(f"ExecutionPlanner.build: {question[:80]}")

        # 1. Classify intent
        intent = _INTENT_CLASSIFIER.classify(question)
        agg    = _INTENT_CLASSIFIER.suggest_aggregation(question)
        chart  = _INTENT_CLASSIFIER.suggest_chart(question, intent)

        # 2. Check unsupported
        unsupported = _check_unsupported(intent, schema)
        if unsupported:
            return ExecutionPlan(
                intent=intent,
                original_question=question,
                dataset_schema=schema,
                is_executable=False,
                unsupported_reason=unsupported,
                chart_type=ChartType.NONE,
            )

        # 3. Extract components
        metrics   = _EXTRACTOR.extract_metrics(question, schema)
        group_by  = _EXTRACTOR.extract_group_by(question, schema)
        filters   = _EXTRACTOR.extract_filters(question, schema)
        time_band = _EXTRACTOR.extract_time_band(question, schema)
        limit     = _EXTRACTOR.extract_limit(question)

        # 4. Intent-specific overrides
        if intent == QueryIntent.RANKING and limit is None:
            limit = 10
        if intent in (QueryIntent.TREND, QueryIntent.FORECASTING) and time_band is None:
            # Already caught above for forecasting; trend just uses full date col
            if schema.date_columns:
                from app.schemas.execution_plan import TimeBand
                time_band = TimeBand(column=schema.date_columns[0], granularity="year")

        # 5. Sort order
        sort_order = (
            SortOrder.ASC
            if any(k in question.lower() for k in ["lowest", "worst", "least", "bottom"])
            else SortOrder.DESC
        )

        # 6. Schema coverage
        requested = set(metrics) | set(group_by)
        if requested:
            found = sum(1 for c in requested if schema.has_column(c))
            schema_coverage = found / len(requested)
        else:
            schema_coverage = 1.0

        # 7. Ambiguity (simple heuristic)
        ambiguity = 0.0
        if not metrics and intent not in (QueryIntent.SUMMARIZATION, QueryIntent.FILTERING):
            ambiguity += 0.3
        if not group_by and intent == QueryIntent.RANKING:
            ambiguity += 0.2

        # 8. Complexity
        complexity = min(1.0, (
            (0.1 if filters else 0.0) +
            (0.1 if time_band else 0.0) +
            (0.2 if intent in (QueryIntent.CORRELATION, QueryIntent.ANOMALY) else 0.0) +
            (0.3 if intent in (QueryIntent.RECOMMENDATION, QueryIntent.OPTIMIZATION) else 0.0)
        ))

        plan = ExecutionPlan(
            intent=intent,
            original_question=question,
            metrics=metrics,
            aggregation=agg,
            group_by=group_by,
            filters=filters,
            time_band=time_band,
            limit=limit,
            sort_order=sort_order,
            chart_type=chart,
            dataset_schema=schema,
            is_executable=True,
            schema_coverage=schema_coverage,
            ambiguity_score=ambiguity,
            complexity_score=complexity,
        )
        logger.info(
            f"Plan: intent={intent} metrics={metrics} "
            f"group_by={group_by} agg={agg} time={time_band}"
        )
        return plan
