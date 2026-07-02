"""
Query Verifier
--------------
Validates an ExecutionPlan BEFORE execution.
Adds ValidationIssues (errors / warnings) to the plan in-place.
Never raises — errors are communicated through the plan object.
"""
from __future__ import annotations

from app.schemas.execution_plan import (
    AggregationFunc,
    ColumnSemantics,
    ExecutionPlan,
    QueryIntent,
    ValidationIssue,
)
from app.core.logger import logger


# Aggregations that don't make sense on categorical columns
_NUMERIC_ONLY_AGGS = {
    AggregationFunc.SUM,
    AggregationFunc.MEAN,
    AggregationFunc.MEDIAN,
    AggregationFunc.STD,
    AggregationFunc.VAR,
}


class QueryVerifier:

    def verify(self, plan: ExecutionPlan) -> ExecutionPlan:
        """
        Validates the plan and annotates it with issues.
        Returns the (modified) plan — never raises.
        """
        if not plan.is_executable:
            return plan   # already marked unsupported

        schema = plan.dataset_schema
        if schema is None:
            plan.validation_issues.append(
                ValidationIssue(severity="error", message="No dataset schema available.")
            )
            plan.is_executable = False
            return plan

        self._check_metrics(plan)
        self._check_group_by(plan)
        self._check_aggregation_type(plan)
        self._check_time_band(plan)
        self._check_filters(plan)
        self._check_intent_feasibility(plan)

        if plan.has_errors():
            plan.is_executable = False
            logger.warning(
                f"QueryVerifier: plan has errors: "
                f"{[i.message for i in plan.validation_issues if i.severity=='error']}"
            )
        else:
            logger.info("QueryVerifier: plan is valid")

        return plan

    # ------------------------------------------------------------------
    def _check_metrics(self, plan: ExecutionPlan) -> None:
        schema = plan.dataset_schema
        for col in plan.metrics:
            if not schema.has_column(col):
                plan.validation_issues.append(ValidationIssue(
                    severity="error",
                    message=f"Metric column '{col}' not found in dataset.",
                    field="metrics",
                ))

    def _check_group_by(self, plan: ExecutionPlan) -> None:
        schema = plan.dataset_schema
        valid = []
        for col in plan.group_by:
            if not schema.has_column(col):
                plan.validation_issues.append(ValidationIssue(
                    severity="warning",
                    message=f"Group-by column '{col}' not found — ignored.",
                    field="group_by",
                ))
            else:
                valid.append(col)
        plan.group_by = valid

    def _check_aggregation_type(self, plan: ExecutionPlan) -> None:
        if plan.aggregation not in _NUMERIC_ONLY_AGGS:
            return
        schema = plan.dataset_schema
        for col in plan.metrics:
            sc = schema.col(col)
            if sc and sc.semantics not in (ColumnSemantics.NUMERIC, ColumnSemantics.TARGET):
                plan.validation_issues.append(ValidationIssue(
                    severity="warning",
                    message=(
                        f"Aggregation '{plan.aggregation}' applied to "
                        f"non-numeric column '{col}' — results may be wrong."
                    ),
                    field="aggregation",
                ))

    def _check_time_band(self, plan: ExecutionPlan) -> None:
        if plan.time_band is None:
            return
        schema = plan.dataset_schema
        col = plan.time_band.column
        if not schema.has_column(col):
            plan.validation_issues.append(ValidationIssue(
                severity="error",
                message=f"Time column '{col}' not found in dataset.",
                field="time_band",
            ))

    def _check_filters(self, plan: ExecutionPlan) -> None:
        schema = plan.dataset_schema
        valid = []
        for f in plan.filters:
            if not schema.has_column(f.column):
                plan.validation_issues.append(ValidationIssue(
                    severity="warning",
                    message=f"Filter column '{f.column}' not found — ignored.",
                    field="filters",
                ))
            else:
                valid.append(f)
        plan.filters = valid

    def _check_intent_feasibility(self, plan: ExecutionPlan) -> None:
        schema = plan.dataset_schema
        if plan.intent == QueryIntent.RANKING and not plan.group_by:
            # Auto-assign first categorical
            if schema.categorical_columns:
                plan.group_by = [schema.categorical_columns[0]]
                plan.validation_issues.append(ValidationIssue(
                    severity="info",
                    message=(
                        f"Ranking group-by not specified; "
                        f"defaulted to '{plan.group_by[0]}'."
                    ),
                    field="group_by",
                ))
            else:
                plan.validation_issues.append(ValidationIssue(
                    severity="error",
                    message="Ranking requires a categorical column to group by, but none found.",
                    field="group_by",
                ))

        if plan.intent == QueryIntent.RANKING and not plan.metrics:
            if schema.numeric_columns:
                plan.metrics = [schema.numeric_columns[0]]
                plan.validation_issues.append(ValidationIssue(
                    severity="info",
                    message=(
                        f"Ranking metric not specified; "
                        f"defaulted to '{plan.metrics[0]}'."
                    ),
                    field="metrics",
                ))
            else:
                plan.validation_issues.append(ValidationIssue(
                    severity="error",
                    message="Ranking requires a numeric metric column, but none found.",
                    field="metrics",
                ))
