"""
Metric & Entity Extractor
--------------------------
Extracts requested metrics, grouping entities, filters, and time references
from a natural-language question and validates them against the DatasetSchema.

Key guarantee: NEVER substitutes a missing metric with an unrelated column.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.schemas.execution_plan import (
    AggregationFunc,
    ColumnSemantics,
    DatasetSchema,
    FilterCondition,
    TimeBand,
)
from app.core.logger import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> List[str]:
    """Lower-case tokens, keeping multi-word phrases intact for matching."""
    return re.findall(r"[a-z0-9_]+", text.lower())


def _fuzzy_match_column(token: str, schema: DatasetSchema, allowed_semantics: set) -> Optional[str]:
    """
    Find the best column whose name contains the token or vice-versa.
    Returns None if no confident match found.
    """
    token_l = token.lower().replace(" ", "_").replace("-", "_")
    best: Optional[str] = None
    best_score = 0

    for col in schema.columns:
        if col.semantics not in allowed_semantics:
            continue
        col_l = col.name.lower().replace(" ", "_").replace("-", "_")
        # Exact
        if token_l == col_l:
            return col.name
        # Substring either way
        score = 0
        if token_l in col_l:
            score = len(token_l) / len(col_l)
        elif col_l in token_l:
            score = len(col_l) / len(token_l)
        if score > best_score and score >= 0.5:
            best_score = score
            best = col.name

    return best


def _extract_time_band(question: str, schema: DatasetSchema) -> Optional[TimeBand]:
    if not schema.date_columns:
        return None

    col = schema.date_columns[0]
    q = question.lower()

    # Year range  e.g. "between 2020 and 2023"
    range_m = re.search(r"(20\d{2})\s*(?:to|and|-)\s*(20\d{2})", q)
    if range_m:
        return TimeBand(column=col, start=f"{range_m.group(1)}-01-01",
                        end=f"{range_m.group(2)}-12-31", granularity="year")

    # Single year  e.g. "in 2022"
    year_m = re.search(r"\b(20\d{2})\b", q)
    if year_m:
        y = year_m.group(1)
        return TimeBand(column=col, start=f"{y}-01-01", end=f"{y}-12-31", granularity="year")

    # Month + year  e.g. "March 2023"
    month_m = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(20\d{2})\b", q
    )
    if month_m:
        month_map = dict(jan="01",feb="02",mar="03",apr="04",may="05",jun="06",
                         jul="07",aug="08",sep="09",oct="10",nov="11",dec="12")
        m = month_map[month_m.group(1)]
        y = month_m.group(2)
        return TimeBand(column=col, start=f"{y}-{m}-01", end=f"{y}-{m}-31", granularity="month")

    # "over time" / "trend" — use full date column, yearly granularity
    if any(k in q for k in ["over time", "trend", "per year", "per month", "monthly", "yearly"]):
        granularity = "month" if any(k in q for k in ["per month", "monthly"]) else "year"
        return TimeBand(column=col, start=None, end=None, granularity=granularity)

    return None


def _extract_limit(question: str) -> Optional[int]:
    q = question.lower()
    m = re.search(r"\b(top|bottom|first|last)\s+(\d+)\b", q)
    if m:
        return int(m.group(2))
    for word, val in [("five", 5), ("ten", 10), ("twenty", 20), ("hundred", 100)]:
        if word in q:
            return val
    if any(k in q for k in ["top ", "most ", "best ", "highest "]):
        return 10
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class MetricEntityExtractor:
    """
    Extracts metrics, group-by columns, filters, and time from a question.
    All outputs are validated against the DatasetSchema.
    """

    def extract_metrics(self, question: str, schema: DatasetSchema) -> List[str]:
        """
        Returns column names that are plausible metrics for this question.
        Returns [] if nothing confident found — never substitutes randomly.
        """
        q = question.lower()
        found: List[str] = []

        # Scan every word/bigram in question against numeric column names
        tokens = _tokenise(q)
        for i, tok in enumerate(tokens):
            # bigram
            bigram = f"{tok}_{tokens[i+1]}" if i + 1 < len(tokens) else ""
            for candidate in [tok, bigram]:
                col = _fuzzy_match_column(
                    candidate, schema,
                    {ColumnSemantics.NUMERIC, ColumnSemantics.TARGET}
                )
                if col and col not in found:
                    found.append(col)

        # If still empty: only fall back when aggregation is obviously global
        if not found:
            count_words = ["how many", "count", "number of"]
            if any(k in q for k in count_words):
                return []           # COUNT(*) — no metric column needed
            # Last resort: first non-ID numeric column
            for col in schema.columns:
                if col.semantics == ColumnSemantics.NUMERIC:
                    logger.warning(f"MetricExtractor fallback to first numeric col: {col.name}")
                    return [col.name]

        return found

    def extract_group_by(self, question: str, schema: DatasetSchema) -> List[str]:
        """Returns categorical columns to group by."""
        q = question.lower()
        found: List[str] = []

        # Explicit grouping words
        group_triggers = ["by ", "per ", "for each ", "grouped by ", "breakdown by "]
        has_trigger = any(t in q for t in group_triggers)

        tokens = _tokenise(q)
        for i, tok in enumerate(tokens):
            bigram = f"{tok}_{tokens[i+1]}" if i + 1 < len(tokens) else ""
            for candidate in [tok, bigram]:
                col = _fuzzy_match_column(
                    candidate, schema,
                    {ColumnSemantics.CATEGORICAL}
                )
                if col and col not in found:
                    found.append(col)

        # If no trigger and no match, don't invent grouping
        if not has_trigger and not found:
            return []
        return found

    def extract_filters(self, question: str, schema: DatasetSchema) -> List[FilterCondition]:
        """
        Very lightweight filter extraction — catches "X > N", "X = Y" patterns.
        Extend with LLM for complex cases.
        """
        filters: List[FilterCondition] = []
        q = question

        # Pattern: column_like_word operator value  e.g. "age > 30", "category = electronics"
        pattern = re.finditer(
            r"\b([a-zA-Z_][a-zA-Z0-9_ ]*?)\s*(>=|<=|!=|>|<|=|==)\s*(['\"]?[a-zA-Z0-9_.]+['\"]?)",
            q
        )
        op_map = {"=": "eq", "==": "eq", "!=": "ne", ">": "gt", ">=": "gte",
                  "<": "lt", "<=": "lte"}

        for m in pattern:
            raw_col = m.group(1).strip().replace(" ", "_")
            op_str  = op_map.get(m.group(2), "eq")
            raw_val = m.group(3).strip("'\"")
            col = _fuzzy_match_column(raw_col, schema, set(ColumnSemantics))
            if col:
                try:
                    val: object = float(raw_val) if "." in raw_val else int(raw_val)
                except ValueError:
                    val = raw_val
                filters.append(FilterCondition(column=col, operator=op_str, value=val))

        return filters

    def extract_time_band(self, question: str, schema: DatasetSchema) -> Optional[TimeBand]:
        return _extract_time_band(question, schema)

    def extract_limit(self, question: str) -> Optional[int]:
        return _extract_limit(question)
