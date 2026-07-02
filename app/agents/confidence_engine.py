"""
Confidence Engine
-----------------
Computes a composite confidence score from:
  - Schema coverage   (were all requested columns found?)
  - Ambiguity         (was the question clear?)
  - Complexity        (how hard was the query to reason about?)
  - Validation issues (errors / warnings from QueryVerifier)
  - Execution success (was a non-empty result returned?)
"""
from __future__ import annotations

from typing import Any

from app.schemas.execution_plan import ExecutionPlan
from app.core.logger import logger


class ConfidenceEngine:

    def compute(self, plan: ExecutionPlan, result: Any) -> float:
        """Returns a score in [0.0, 1.0]."""
        score = 1.0

        # 1. Schema coverage penalty
        score -= (1.0 - plan.schema_coverage) * 0.3

        # 2. Ambiguity penalty
        score -= plan.ambiguity_score * 0.2

        # 3. Complexity penalty (complex = harder to be right)
        score -= plan.complexity_score * 0.1

        # 4. Validation issues
        for issue in plan.validation_issues:
            if issue.severity == "error":
                score -= 0.25
            elif issue.severity == "warning":
                score -= 0.08

        # 5. Execution result quality
        if result is None:
            score -= 0.4
        elif isinstance(result, list):
            if len(result) == 0:
                score -= 0.3
        elif isinstance(result, str) and result.startswith("Error"):
            score -= 0.3

        final = round(max(0.0, min(1.0, score)), 2)
        logger.debug(f"ConfidenceEngine: {final}")
        return final

    def explain(self, plan: ExecutionPlan, score: float) -> str:
        parts = []
        if plan.schema_coverage < 0.8:
            parts.append(f"some requested columns were not found (coverage {plan.schema_coverage:.0%})")
        if plan.ambiguity_score > 0.2:
            parts.append("the question was somewhat ambiguous")
        if plan.validation_issues:
            issues = [i.message for i in plan.validation_issues]
            parts.append(f"validation: {'; '.join(issues[:2])}")
        if not parts:
            return f"Confidence is {score:.0%} — query interpreted cleanly."
        return f"Confidence is {score:.0%} because: {', '.join(parts)}."
