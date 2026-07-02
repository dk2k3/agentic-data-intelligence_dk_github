from typing import Optional, Dict, List


class MetricResolver:
    """
    Resolve ambiguous metric terms into concrete dataset columns
    using semantic rules (dataset-agnostic).
    """

    def __init__(self, schema: Dict[str, str]):
        self.schema = schema
        self.columns = list(schema.keys())

    # --------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------
    def resolve_metric_from_question(self, question: str) -> Optional[str]:
        q = question.lower()

        # -------------------------
        # COUNT QUERIES
        # -------------------------
        if any(k in q for k in ["count", "how many", "number of"]):
            return None

        # -------------------------
        # REVENUE / SALES
        # -------------------------
        if any(k in q for k in ["revenue", "sales", "amount", "total"]):
            col = self._find_by_keywords(
                ["revenue", "sales", "amount", "total"]
            )
            if col:
                return col

        # -------------------------
        # POPULARITY / STREAMS
        # -------------------------
        if any(k in q for k in ["popular", "popularity", "streams", "plays", "listeners"]):
            col = self._find_by_keywords(
                ["popularity", "streams", "plays", "listeners"]
            )
            if col:
                return col

        # -------------------------
        # RATINGS
        # -------------------------
        if any(k in q for k in ["rating", "ratings", "score", "stars"]):
            col = self._find_by_keywords(
                ["rating", "score", "stars"]
            )
            if col:
                return col

        # -------------------------
        # SAFE FALLBACK
        # -------------------------
        return self._find_best_numeric_metric()

    # --------------------------------------------------
    # HELPERS
    # --------------------------------------------------
    def _is_id_column(self, col: str) -> bool:
        col_l = col.lower()
        return (
            col_l.endswith("id")
            or col_l == "id"
            or "uuid" in col_l
            or "hash" in col_l
        )

    def _is_numeric(self, dtype: str) -> bool:
        dtype_l = dtype.lower()
        return "int" in dtype_l or "float" in dtype_l

    def _find_by_keywords(self, keywords: List[str]) -> Optional[str]:
        for col, dtype in self.schema.items():
            if self._is_id_column(col):
                continue
            if not self._is_numeric(dtype):
                continue
            col_l = col.lower()
            if any(k in col_l for k in keywords):
                return col
        return None

    def _find_best_numeric_metric(self) -> Optional[str]:
        """
        Final safe fallback:
        - numeric
        - not an ID
        """
        for col, dtype in self.schema.items():
            if self._is_numeric(dtype) and not self._is_id_column(col):
                return col
        return None
