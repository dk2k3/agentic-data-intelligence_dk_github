"""
Recommendation Executor end-to-end smoke test.
Run: python -m tests.smoke_recommendation
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.schema_understanding_agent import SchemaUnderstandingAgent
from app.agents.execution_planner import ExecutionPlanner
from app.agents.query_verifier import QueryVerifier
from app.agents.recommendation_executor import RecommendationExecutor, recommendation_result_to_dict
from app.agents.domain_reasoning_agent import DomainReasoningAgent
from app.agents.confidence_engine import ConfidenceEngine
from app.schemas.execution_plan import QueryIntent

# ── Synthetic datasets ────────────────────────────────────────────────────────

def make_supply_df():
    rng = np.random.default_rng(42)
    n = 300
    return pd.DataFrame({
        "supplier":       rng.choice(["Alpha", "Beta", "Gamma", "Delta"], n),
        "stock_level":    rng.integers(0, 1000, n),
        "lead_time_days": rng.integers(1, 60, n),
        "unit_cost":      rng.uniform(1, 500, n).round(2),
        "defect_rate":    rng.uniform(0, 0.1, n).round(4),
        "reorder_point":  rng.integers(10, 300, n),
    })


def make_ecom_df():
    rng = np.random.default_rng(7)
    n = 400
    return pd.DataFrame({
        "product":   rng.choice(["Widget", "Gadget", "Doohickey", "Thingamajig", "Gizmo"], n),
        "category":  rng.choice(["Electronics", "Clothing", "Food", "Home"], n),
        "revenue":   rng.uniform(100, 5000, n).round(2),
        "units":     rng.integers(1, 200, n),
        "cost":      rng.uniform(50, 2000, n).round(2),
        "returns":   rng.integers(0, 30, n),
    })


def make_hr_df():
    rng = np.random.default_rng(13)
    n = 250
    return pd.DataFrame({
        "department":   rng.choice(["Engineering", "Sales", "HR", "Finance"], n),
        "salary":       rng.uniform(30000, 200000, n).round(0),
        "performance":  rng.uniform(1, 5, n).round(1),
        "tenure_years": rng.uniform(0.5, 20, n).round(1),
        "attrition":    rng.uniform(0, 0.3, n).round(3),
    })


# ── Test runner ───────────────────────────────────────────────────────────────

TESTS = [
    # (dataset_fn, question, expected_intent)
    (make_supply_df, "Recommend an optimal procurement strategy considering stock levels, lead times, and defect rates", QueryIntent.RECOMMENDATION),
    (make_supply_df, "Which supplier should we prioritize?",                                                  QueryIntent.RECOMMENDATION),
    (make_supply_df, "Optimize supplier selection to minimize cost and defect rate",                           QueryIntent.OPTIMIZATION),
    (make_ecom_df,   "Recommend the best products to promote based on revenue and returns",                    QueryIntent.RECOMMENDATION),
    (make_ecom_df,   "Which product category should we invest in?",                                           QueryIntent.RECOMMENDATION),
    (make_ecom_df,   "Optimize our product mix to maximize revenue and minimize cost",                         QueryIntent.OPTIMIZATION),
    (make_hr_df,     "Recommend which departments need the most investment",                                   QueryIntent.RECOMMENDATION),
    (make_hr_df,     "Which department should we hire in to maximize performance?",                            QueryIntent.RECOMMENDATION),
    (make_hr_df,     "Optimize team allocation to improve performance and reduce attrition",                   QueryIntent.OPTIMIZATION),
]

schema_agent = SchemaUnderstandingAgent()
planner      = ExecutionPlanner()
verifier     = QueryVerifier()
executor     = RecommendationExecutor()
reasoning    = DomainReasoningAgent()
confidence   = ConfidenceEngine()

passed = failed = 0

for df_fn, question, expected_intent in TESTS:
    df = df_fn()
    try:
        schema = schema_agent.analyse(df)
        plan   = planner.build(question, schema)
        plan   = verifier.verify(plan)

        assert plan.intent == expected_intent, \
            f"Intent mismatch: expected {expected_intent}, got {plan.intent}"
        assert plan.is_executable, f"Plan not executable: {plan.unsupported_reason}"

        rec_result, code = executor.execute(df, plan)

        # Structural checks
        assert rec_result.cards, "No recommendation cards produced"
        assert rec_result.cards[0].composite_score >= 0
        assert rec_result.cards[0].grade in ("A", "B", "C", "D", "F")
        assert len(rec_result.cards[0].signals) > 0
        assert rec_result.decision_brief

        # Serialisation check
        serialised = recommendation_result_to_dict(rec_result)
        assert "cards" in serialised
        assert serialised["cards"][0]["composite_score"] >= 0

        # Reasoning integration
        explanation = reasoning.generate_explanation(plan)
        insights    = reasoning.generate_insights(plan, rec_result)
        recs        = reasoning.generate_recommendations(plan, rec_result)
        conf_score  = confidence.compute(plan, rec_result)

        top = rec_result.cards[0]
        print(
            f"  PASS  {question[:60]:<60}\n"
            f"        → #{1} {top.entity} score={top.composite_score:.1f} grade={top.grade} "
            f"signals={len(top.signals)} conf={conf_score:.0%}"
        )
        passed += 1

    except Exception as e:
        import traceback
        print(f"  FAIL  {question[:60]}\n        ERROR: {e}")
        traceback.print_exc()
        failed += 1

print(f"\n{'='*70}")
print(f"  {passed} passed, {failed} failed out of {len(TESTS)} recommendation tests.")
print(f"{'='*70}")
