"""
Recommendation Executor
-----------------------
Transforms RECOMMENDATION and OPTIMIZATION intent queries into
decision-support output with:

  1. Multi-signal candidate scoring  — every candidate entity is scored
     across all relevant numeric signals from the dataset.
  2. Evidence rows                   — the actual data rows that support
     each recommendation.
  3. Ranked recommendation cards     — structured list of decisions with
     score, rationale, and supporting evidence.
  4. A human-readable decision brief — actionable summary the user can act on.

Design principles:
  - Zero hardcoded column names or domain knowledge.
  - Everything is derived from the DatasetSchema + ExecutionPlan.
  - Graceful fallback if signals are missing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.schemas.execution_plan import (
    AggregationFunc,
    ColumnSemantics,
    DatasetSchema,
    ExecutionPlan,
    QueryIntent,
)
from app.core.logger import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScoredSignal:
    """One numeric signal's contribution to the composite score."""
    column: str
    raw_value: float
    normalised: float        # 0–1; higher is better
    weight: float
    direction: str           # "higher_is_better" | "lower_is_better"
    contribution: float      # normalised * weight


@dataclass
class RecommendationCard:
    """A single decision recommendation."""
    rank: int
    entity: str              # value of the group-by column
    composite_score: float   # 0–100
    grade: str               # A / B / C / D / F
    signals: List[ScoredSignal]
    evidence_rows: List[Dict[str, Any]]
    rationale: str
    action: str


@dataclass
class RecommendationResult:
    """Full output of the Recommendation Executor."""
    intent: str
    question: str
    entity_column: str
    metric_columns: List[str]
    cards: List[RecommendationCard]
    decision_brief: str
    scoring_rationale: str
    total_candidates: int
    shown_candidates: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grade(score: float) -> str:
    if score >= 80: return "A"
    if score >= 65: return "B"
    if score >= 50: return "C"
    if score >= 35: return "D"
    return "F"


def _detect_signal_direction(col: str, schema: DatasetSchema) -> str:
    """
    Heuristic: columns whose names suggest cost / defect / risk / time
    are 'lower_is_better'. Everything else is 'higher_is_better'.
    """
    lower_keywords = [
        "cost", "defect", "error", "fail", "risk", "loss", "churn",
        "complaint", "return", "delay", "lead_time", "latency", "debt",
        "expense", "penalty", "waste", "reject",
    ]
    col_l = col.lower()
    if any(k in col_l for k in lower_keywords):
        return "lower_is_better"
    return "higher_is_better"


def _minmax(series: pd.Series, direction: str) -> pd.Series:
    """Min-max normalise; flip if lower_is_better."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([0.5] * len(series), index=series.index)
    normed = (series - mn) / (mx - mn)
    if direction == "lower_is_better":
        normed = 1.0 - normed
    return normed


def _choose_signals(
    plan: ExecutionPlan,
    schema: DatasetSchema,
    max_signals: int = 6,
) -> List[str]:
    """
    Pick numeric signal columns:
      1. Columns explicitly requested in plan.metrics.
      2. All other non-ID numeric columns up to max_signals total.
    """
    requested = list(plan.metrics)
    extras = [
        c for c in schema.numeric_columns
        if c not in requested
    ]
    combined = requested + extras
    return combined[:max_signals]


def _assign_weights(signal_cols: List[str], plan: ExecutionPlan) -> Dict[str, float]:
    """
    Weight distribution:
      - Explicitly requested metrics get double weight.
      - All other signals share the remainder equally.
    """
    if not signal_cols:
        return {}

    requested = set(plan.metrics)
    n_requested = sum(1 for c in signal_cols if c in requested)
    n_other = len(signal_cols) - n_requested

    if n_requested == 0:
        # Uniform weights
        w = 1.0 / len(signal_cols)
        return {c: w for c in signal_cols}

    # Requested columns get 2× the weight of others
    # Solve: n_requested * 2w + n_other * w = 1
    # w = 1 / (2*n_requested + n_other)
    unit = 1.0 / (2 * n_requested + max(n_other, 0))
    return {
        c: (2 * unit if c in requested else unit)
        for c in signal_cols
    }


def _build_rationale(entity: str, signals: List[ScoredSignal], grade: str) -> str:
    if not signals:
        return f"**{entity}** was evaluated but had no measurable signals."

    top = sorted(signals, key=lambda s: s.contribution, reverse=True)[:2]
    bottom = sorted(signals, key=lambda s: s.contribution)[:1]

    pos = [f"**{s.column}** ({s.direction.replace('_', ' ')}: {s.raw_value:,.2f})"
           for s in top]
    neg = [f"**{s.column}** ({s.direction.replace('_', ' ')}: {s.raw_value:,.2f})"
           for s in bottom if s.contribution < 0.4]

    parts = [f"**{entity}** scored **{grade}**."]
    if pos:
        parts.append(f"Strengths: {', '.join(pos)}.")
    if neg:
        parts.append(f"Weakness: {', '.join(neg)}.")
    return " ".join(parts)


def _build_action(entity: str, signals: List[ScoredSignal], grade: str,
                  intent: QueryIntent) -> str:
    verb = "prioritise" if intent == QueryIntent.RECOMMENDATION else "optimise"
    weak = [s for s in signals if s.contribution < 0.35]
    if not weak:
        return f"{verb.capitalize()} **{entity}** — consistently strong across all signals."
    weak_names = ", ".join(f"**{s.column}**" for s in weak[:2])
    return (
        f"Consider {verb}ing **{entity}**; "
        f"address low performance in {weak_names} first."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class RecommendationExecutor:
    """
    Executes RECOMMENDATION and OPTIMIZATION intents with evidence-based scoring.
    Returns a RecommendationResult (not a raw DataFrame).
    """

    def execute(
        self,
        df: pd.DataFrame,
        plan: ExecutionPlan,
    ) -> Tuple[RecommendationResult, str]:
        """
        Returns (RecommendationResult, pandas_code_string).
        The pandas_code_string is for transparency display.
        """
        schema = plan.dataset_schema
        assert schema is not None

        # ── 1. Resolve entity (group-by) column ──────────────────────────
        entity_col = self._resolve_entity_col(plan, schema)
        if entity_col is None:
            return self._fallback(df, plan, "No categorical column found to group candidates.")

        # ── 2. Resolve signal columns ─────────────────────────────────────
        signal_cols = _choose_signals(plan, schema)
        if not signal_cols:
            return self._fallback(df, plan, "No numeric columns available for scoring.")

        weights = _assign_weights(signal_cols, plan)
        directions = {c: _detect_signal_direction(c, schema) for c in signal_cols}

        logger.info(
            f"RecommendationExecutor: entity={entity_col} "
            f"signals={signal_cols} weights={weights}"
        )

        # ── 3. Aggregate signals per entity ───────────────────────────────
        agg_dict = {c: "mean" for c in signal_cols}
        grouped = (
            df.groupby(entity_col)[signal_cols]
            .agg(agg_dict)
            .reset_index()
        )

        # ── 4. Normalise each signal ──────────────────────────────────────
        normed: Dict[str, pd.Series] = {}
        for col in signal_cols:
            normed[col] = _minmax(grouped[col], directions[col])

        # ── 5. Composite score (0–100) ────────────────────────────────────
        composite = pd.Series(0.0, index=grouped.index)
        for col in signal_cols:
            composite += normed[col] * weights[col]
        grouped["_composite"] = (composite * 100).round(1)

        # ── 6. Sort and limit ─────────────────────────────────────────────
        limit = plan.limit or 10
        grouped = grouped.sort_values("_composite", ascending=False)
        top_n = grouped.head(limit).reset_index(drop=True)

        # ── 7. Build recommendation cards ────────────────────────────────
        cards: List[RecommendationCard] = []
        for rank, row in enumerate(top_n.to_dict("records"), start=1):
            entity_val = str(row[entity_col])
            comp_score = float(row["_composite"])
            grade = _grade(comp_score)

            signals: List[ScoredSignal] = []
            for col in signal_cols:
                raw = float(row.get(col, 0.0))
                if math.isnan(raw):
                    raw = 0.0
                norm_val = float(normed[col].iloc[rank - 1])
                w = weights[col]
                signals.append(ScoredSignal(
                    column=col,
                    raw_value=raw,
                    normalised=round(norm_val, 3),
                    weight=round(w, 3),
                    direction=directions[col],
                    contribution=round(norm_val * w, 3),
                ))

            # Evidence: top 3 source rows for this entity
            evidence = (
                df[df[entity_col] == row[entity_col]]
                .head(3)
                .replace({float("nan"): None})
                .to_dict("records")
            )

            cards.append(RecommendationCard(
                rank=rank,
                entity=entity_val,
                composite_score=comp_score,
                grade=grade,
                signals=signals,
                evidence_rows=evidence,
                rationale=_build_rationale(entity_val, signals, grade),
                action=_build_action(entity_val, signals, grade, plan.intent),
            ))

        # ── 8. Decision brief ─────────────────────────────────────────────
        decision_brief = self._build_brief(cards, entity_col, signal_cols, plan)
        scoring_rationale = self._build_scoring_rationale(
            signal_cols, weights, directions
        )

        # ── 9. Pandas code string (for UI transparency) ───────────────────
        code = self._generate_code(entity_col, signal_cols)

        result = RecommendationResult(
            intent=plan.intent.value,
            question=plan.original_question,
            entity_column=entity_col,
            metric_columns=signal_cols,
            cards=cards,
            decision_brief=decision_brief,
            scoring_rationale=scoring_rationale,
            total_candidates=len(grouped),
            shown_candidates=len(cards),
        )
        return result, code

    # ── Helpers ─────────────────────────────────────────────────────────

    def _resolve_entity_col(
        self, plan: ExecutionPlan, schema: DatasetSchema
    ) -> Optional[str]:
        # Prefer explicit group_by from plan
        if plan.group_by:
            return plan.group_by[0]
        # Fall back to first categorical column
        if schema.categorical_columns:
            return schema.categorical_columns[0]
        return None

    def _build_brief(
        self,
        cards: List[RecommendationCard],
        entity_col: str,
        signals: List[str],
        plan: ExecutionPlan,
    ) -> str:
        if not cards:
            return "No candidates could be evaluated."

        top_card = cards[0]
        verb = "recommend" if plan.intent == QueryIntent.RECOMMENDATION else "optimise for"
        signal_str = ", ".join(f"**{s}**" for s in signals[:4])
        grade_dist = {}
        for c in cards:
            grade_dist[c.grade] = grade_dist.get(c.grade, 0) + 1
        grade_summary = ", ".join(f"{g}: {n}" for g, n in sorted(grade_dist.items()))

        lines = [
            f"### Decision Brief",
            f"",
            f"**Question:** {plan.original_question}",
            f"",
            f"**Signals used:** {signal_str}",
            f"**Candidates evaluated:** {plan.limit or 10} {entity_col} groups",
            f"**Grade distribution:** {grade_summary}",
            f"",
            f"**Top recommendation:** {top_card.action}",
            f"",
            f"**Top {min(3, len(cards))} ranked {entity_col}s:**",
        ]
        for card in cards[:3]:
            lines.append(
                f"- **#{card.rank} {card.entity}** — Score: {card.composite_score:.1f}/100 "
                f"(Grade {card.grade}) — {card.rationale}"
            )

        return "\n".join(lines)

    def _build_scoring_rationale(
        self,
        signals: List[str],
        weights: Dict[str, float],
        directions: Dict[str, str],
    ) -> str:
        lines = ["**Scoring methodology:**"]
        for col in signals:
            w = weights.get(col, 0)
            d = directions.get(col, "higher_is_better").replace("_", " ")
            lines.append(f"- **{col}** — weight {w:.1%}, {d}")
        return "\n".join(lines)

    def _generate_code(self, entity_col: str, signal_cols: List[str]) -> str:
        col_list = str(signal_cols)
        return (
            f"# Multi-signal recommendation scoring\n"
            f"_signals = {col_list}\n"
            f"_grouped = df.groupby('{entity_col}')[_signals].mean().reset_index()\n"
            f"# Min-max normalise each signal, compute composite score\n"
            f"for _col in _signals:\n"
            f"    _mn, _mx = _grouped[_col].min(), _grouped[_col].max()\n"
            f"    _grouped[_col + '_norm'] = (_grouped[_col] - _mn) / (_mx - _mn + 1e-9)\n"
            f"_norm_cols = [c + '_norm' for c in _signals]\n"
            f"_grouped['composite_score'] = _grouped[_norm_cols].mean(axis=1) * 100\n"
            f"result = _grouped.sort_values('composite_score', ascending=False)"
        )

    def _fallback(
        self, df: pd.DataFrame, plan: ExecutionPlan, reason: str
    ) -> Tuple[RecommendationResult, str]:
        logger.warning(f"RecommendationExecutor fallback: {reason}")
        return RecommendationResult(
            intent=plan.intent.value,
            question=plan.original_question,
            entity_column="",
            metric_columns=[],
            cards=[],
            decision_brief=f"Could not generate recommendations: {reason}",
            scoring_rationale="",
            total_candidates=0,
            shown_candidates=0,
        ), f"result = df.head(20)  # fallback: {reason}"


# ---------------------------------------------------------------------------
# Serialisation helper — convert to JSON-safe dict for API response
# ---------------------------------------------------------------------------

def recommendation_result_to_dict(r: RecommendationResult) -> Dict[str, Any]:
    return {
        "intent": r.intent,
        "question": r.question,
        "entity_column": r.entity_column,
        "metric_columns": r.metric_columns,
        "total_candidates": r.total_candidates,
        "shown_candidates": r.shown_candidates,
        "decision_brief": r.decision_brief,
        "scoring_rationale": r.scoring_rationale,
        "cards": [
            {
                "rank": c.rank,
                "entity": c.entity,
                "composite_score": c.composite_score,
                "grade": c.grade,
                "rationale": c.rationale,
                "action": c.action,
                "signals": [
                    {
                        "column": s.column,
                        "raw_value": round(s.raw_value, 4),
                        "normalised": s.normalised,
                        "weight": s.weight,
                        "direction": s.direction,
                        "contribution": s.contribution,
                    }
                    for s in c.signals
                ],
                "evidence_rows": c.evidence_rows,
            }
            for c in r.cards
        ],
    }
