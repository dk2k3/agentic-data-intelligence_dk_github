"""
Intent Classification Agent
---------------------------
Rule-based primary classifier with optional LLM enhancement.
Returns a QueryIntent enum value. Never raises.
"""
from __future__ import annotations

import re
from typing import Optional

from app.schemas.execution_plan import QueryIntent, AggregationFunc, ChartType
from app.core.logger import logger


# ---------------------------------------------------------------------------
# Keyword maps  (ordered — first match wins)
# ---------------------------------------------------------------------------

_INTENT_RULES: list[tuple[QueryIntent, list[str]]] = [
    (QueryIntent.FORECASTING,    ["forecast", "predict next", "future", "projection", "will be"]),
    (QueryIntent.ANOMALY,        ["anomal", "outlier", "unusual", "spike", "abnormal", "weird"]),
    (QueryIntent.CORRELATION,    ["correlat", "relationship between", "related to", "depends on", "affect"]),
    (QueryIntent.ROOT_CAUSE,     ["why", "root cause", "reason for", "cause of", "explain why"]),
    (QueryIntent.RECOMMENDATION, [
        "recommend", "suggest", "should i", "best action", "optimal strategy",
        "what should", "which should we", "should we use", "which is best",
        "which is better", "should we choose", "should we invest",
        "should we prioritize", "should we prioritise",
        "should we focus", "should we hire",
        "which to choose", "which to use", "which to buy",
        "which one", "which option", "what to do",
    ]),
    (QueryIntent.OPTIMIZATION,   [
        "optimiz", "maximiz", "minimiz", "best combination",
        "trade-off", "tradeoff", "to maximize", "to minimize",
        "to maximise", "to minimise",
    ]),
    (QueryIntent.RANKING,        ["top ", "bottom ", "highest", "lowest", "best", "worst", "most", "least", "rank"]),
    (QueryIntent.TREND,          ["trend", "over time", "per year", "per month", "per quarter", "growth", "decline", "change over"]),
    (QueryIntent.COMPARISON,     ["compar", "vs", "versus", "difference between", "better than", "worse than"]),
    (QueryIntent.STATISTICS,     ["distribut", "std", "standard deviation", "variance", "median", "percentile", "skew", "histogram"]),
    (QueryIntent.SUMMARIZATION,  ["summariz", "overview", "describe", "what is this", "about this", "tell me about"]),
    (QueryIntent.FILTERING,      ["where ", "filter", "only ", "exclude", "include", "show me rows", "list all"]),
    (QueryIntent.VISUALIZATION,  ["chart", "plot", "graph", "visualiz", "show me a", "draw"]),
    (QueryIntent.AGGREGATION,    ["total", "sum", "average", "mean", "count", "how many", "number of", "revenue", "sales"]),
]

_AGG_RULES: list[tuple[AggregationFunc, list[str]]] = [
    (AggregationFunc.COUNT,  ["count", "how many", "number of"]),
    (AggregationFunc.MEAN,   ["average", "mean", "avg"]),
    (AggregationFunc.MEDIAN, ["median"]),
    (AggregationFunc.SUM,    ["total", "sum", "revenue", "sales"]),
    (AggregationFunc.MIN,    ["minimum", "lowest value", "smallest"]),
    (AggregationFunc.MAX,    ["maximum", "highest value", "largest"]),
    (AggregationFunc.STD,    ["standard deviation", "std dev", "std"]),
]

_CHART_RULES: list[tuple[ChartType, list[str]]] = [
    (ChartType.PIE,       ["pie chart", "pie graph", "pie"]),
    (ChartType.LINE,      ["line chart", "line graph", "line plot", "trend line"]),
    (ChartType.SCATTER,   ["scatter", "scatter plot", "bubble"]),
    (ChartType.HISTOGRAM, ["histogram", "distribution chart"]),
    (ChartType.HEATMAP,   ["heatmap", "heat map", "correlation matrix"]),
    (ChartType.BAR,       ["bar chart", "bar graph", "bar plot"]),
]


def _match_keywords(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class IntentClassifierAgent:
    """
    Classifies user question into a QueryIntent.
    Falls back to AGGREGATION for simple metric questions.
    """

    def classify(self, question: str) -> QueryIntent:
        q = question.lower()
        for intent, keywords in _INTENT_RULES:
            if _match_keywords(q, keywords):
                logger.debug(f"Intent classified as {intent} for: {question[:60]}")
                return intent
        return QueryIntent.AGGREGATION   # safe default

    def suggest_aggregation(self, question: str) -> Optional[AggregationFunc]:
        q = question.lower()
        for agg, keywords in _AGG_RULES:
            if _match_keywords(q, keywords):
                return agg
        return AggregationFunc.SUM       # safe default

    def suggest_chart(self, question: str, intent: QueryIntent) -> ChartType:
        q = question.lower()
        for chart, keywords in _CHART_RULES:
            if _match_keywords(q, keywords):
                return chart
        # Intent-based defaults
        defaults = {
            QueryIntent.TREND:       ChartType.LINE,
            QueryIntent.RANKING:     ChartType.BAR,
            QueryIntent.STATISTICS:  ChartType.HISTOGRAM,
            QueryIntent.CORRELATION: ChartType.SCATTER,
            QueryIntent.AGGREGATION: ChartType.BAR,
            QueryIntent.COMPARISON:  ChartType.BAR,
            QueryIntent.FILTERING:   ChartType.BAR,
        }
        return defaults.get(intent, ChartType.AUTO)

    # Legacy shim — keeps old call sites working
    def classify_intent(self, question: str) -> dict:
        intent = self.classify(question)
        agg = self.suggest_aggregation(question)
        chart = self.suggest_chart(question, intent)
        return {
            "data_intent": intent.value,
            "aggregation": agg.value if agg else None,
            "visualization": chart.value,
            "confidence": 0.85,
        }
