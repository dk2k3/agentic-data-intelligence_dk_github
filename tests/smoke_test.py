"""Quick smoke test — no pytest needed. Run: python tests/smoke_test.py"""
import numpy as np
import pandas as pd

from app.agents.schema_understanding_agent import SchemaUnderstandingAgent
from app.agents.execution_planner import ExecutionPlanner
from app.agents.query_verifier import QueryVerifier
from app.agents.pandas_executor_agent import PandasExecutorAgent
from app.agents.sql_generator_agent import SQLGeneratorAgent
from app.agents.chart_agent import generate_chart
from app.agents.confidence_engine import ConfidenceEngine
from app.agents.domain_reasoning_agent import DomainReasoningAgent
from app.schemas.execution_plan import QueryIntent

rng = np.random.default_rng(1)
n = 200
df = pd.DataFrame({
    "product":    rng.choice(["A", "B", "C", "D"], n),
    "category":   rng.choice(["X", "Y"], n),
    "revenue":    rng.uniform(10, 5000, n).round(2),
    "units":      rng.integers(1, 100, n),
    "order_date": pd.date_range("2021-01-01", periods=n, freq="D"),
})

schema_agent = SchemaUnderstandingAgent()
planner      = ExecutionPlanner()
verifier     = QueryVerifier()
executor     = PandasExecutorAgent()
sql_gen      = SQLGeneratorAgent()
confidence   = ConfidenceEngine()
reasoning    = DomainReasoningAgent()

TESTS = [
    ("Top 5 products by revenue",               QueryIntent.RANKING),
    ("Total revenue by category",               QueryIntent.AGGREGATION),
    ("Revenue trend over time",                 QueryIntent.TREND),
    ("Distribution of revenue",                 QueryIntent.STATISTICS),
    ("Correlation between revenue and units",   QueryIntent.CORRELATION),
    ("Compare X vs Y categories",               QueryIntent.COMPARISON),
    ("Show rows where revenue > 1000",          QueryIntent.FILTERING),
    ("Summarize the dataset",                   QueryIntent.SUMMARIZATION),
    ("Are there revenue outliers?",             QueryIntent.ANOMALY),
    ("Recommend strategies to grow revenue",    QueryIntent.RECOMMENDATION),
    ("Forecast revenue next month",             None),   # unsupported guard
]

schema = schema_agent.analyse(df)
passed = failed = 0

for question, expected_intent in TESTS:
    try:
        plan = planner.build(question, schema)
        plan = verifier.verify(plan)
        sql  = sql_gen.generate(plan, "orders")

        if plan.is_executable:
            result, code = executor.execute(df, plan)
            score = confidence.compute(plan, result)
            explanation = reasoning.generate_explanation(plan)
            chart = generate_chart(result, plan=plan)
            status = f"OK  intent={plan.intent.value} conf={score:.0%}"
        else:
            status = f"UNSUPPORTED: {plan.unsupported_reason}"

        if expected_intent and plan.is_executable:
            assert plan.intent == expected_intent, (
                f"Expected {expected_intent}, got {plan.intent}"
            )
        print(f"  PASS  {question[:55]:<55} {status}")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {question[:55]:<55} ERROR: {e}")
        failed += 1

print(f"\n{passed} passed, {failed} failed out of {len(TESTS)} tests.")
