"""
Schema Understanding Agent
--------------------------
Analyses a DataFrame and produces a rich DatasetSchema with column semantics.
Zero hardcoded column names — all inference is statistical / heuristic.
"""
from __future__ import annotations

import re
from typing import Any, List

import pandas as pd

from app.schemas.execution_plan import (
    ColumnSemantics,
    DatasetSchema,
    SchemaColumn,
)
from app.core.logger import logger


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

_ID_PATTERNS = re.compile(
    r"(^id$|_id$|uuid|hash|key$|code$|ref$|index$)",
    re.IGNORECASE,
)

_DATE_PATTERNS = re.compile(
    r"(date|time|year|month|day|period|timestamp|created|updated|at$)",
    re.IGNORECASE,
)

_TEXT_PATTERNS = re.compile(
    r"(description|comment|note|text|body|content|message|review|summary)",
    re.IGNORECASE,
)


def _infer_semantics(col: str, dtype: str, series: pd.Series) -> ColumnSemantics:
    """Pure heuristic — no LLM required."""
    col_l = col.lower()
    dtype_l = dtype.lower()

    # Identifier check (name + cardinality)
    if _ID_PATTERNS.search(col_l):
        return ColumnSemantics.IDENTIFIER

    # Datetime
    if "datetime" in dtype_l or "period" in dtype_l:
        return ColumnSemantics.DATE
    if _DATE_PATTERNS.search(col_l) and "object" in dtype_l:
        # Try parsing a sample
        sample = series.dropna().head(5)
        try:
            pd.to_datetime(sample, errors="raise")
            return ColumnSemantics.DATE
        except Exception:
            pass

    # Boolean
    if "bool" in dtype_l:
        return ColumnSemantics.BOOLEAN

    # Numeric
    if "int" in dtype_l or "float" in dtype_l:
        # High-cardinality int that looks like an ID
        if series.nunique() == len(series.dropna()) and _ID_PATTERNS.search(col_l):
            return ColumnSemantics.IDENTIFIER
        return ColumnSemantics.NUMERIC

    # Text (long free-form strings)
    if "object" in dtype_l:
        if _TEXT_PATTERNS.search(col_l):
            return ColumnSemantics.TEXT
        avg_len = series.dropna().astype(str).str.len().mean() if len(series.dropna()) else 0
        if avg_len > 80:
            return ColumnSemantics.TEXT
        return ColumnSemantics.CATEGORICAL

    return ColumnSemantics.UNKNOWN


def _pick_target_candidates(cols: List[SchemaColumn]) -> List[str]:
    """
    Potential regression / classification targets:
    numeric columns that are not IDs and not clearly grouping dimensions.
    """
    candidates = []
    for c in cols:
        if c.semantics == ColumnSemantics.NUMERIC and c.n_unique > 10:
            candidates.append(c.name)
    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SchemaUnderstandingAgent:
    """
    Analyses a pandas DataFrame and returns a DatasetSchema.
    Call once per dataset upload; cache the result.
    """

    def analyse(self, df: pd.DataFrame) -> DatasetSchema:
        logger.info(f"SchemaUnderstandingAgent: analysing {df.shape}")
        columns: List[SchemaColumn] = []

        for col in df.columns:
            series = df[col]
            dtype = str(series.dtype)
            semantics = _infer_semantics(col, dtype, series)

            sample_vals: List[Any] = (
                series.dropna().unique()[:5].tolist()
                if series.dropna().nunique() <= 20
                else series.dropna().head(3).tolist()
            )
            # make JSON-safe
            sample_vals = [
                str(v) if not isinstance(v, (int, float, bool, str)) else v
                for v in sample_vals
            ]

            columns.append(
                SchemaColumn(
                    name=col,
                    dtype=dtype,
                    semantics=semantics,
                    n_unique=int(series.nunique()),
                    n_missing=int(series.isnull().sum()),
                    sample_values=sample_vals,
                )
            )

        date_cols   = [c.name for c in columns if c.semantics == ColumnSemantics.DATE]
        numeric_cols= [c.name for c in columns if c.semantics == ColumnSemantics.NUMERIC]
        cat_cols    = [c.name for c in columns if c.semantics == ColumnSemantics.CATEGORICAL]
        id_cols     = [c.name for c in columns if c.semantics == ColumnSemantics.IDENTIFIER]
        targets     = _pick_target_candidates(columns)

        schema = DatasetSchema(
            columns=columns,
            row_count=len(df),
            date_columns=date_cols,
            numeric_columns=numeric_cols,
            categorical_columns=cat_cols,
            identifier_columns=id_cols,
            potential_targets=targets,
        )
        logger.info(
            f"Schema: {len(numeric_cols)} numeric, {len(cat_cols)} categorical, "
            f"{len(date_cols)} date, {len(id_cols)} id"
        )
        return schema
