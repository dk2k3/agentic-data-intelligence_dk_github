import pandas as pd
from typing import Any, Tuple, Optional

from app.schemas.final_reasoning_schema import IntentType


class ResultShapeError(Exception):
    """Raised when result shape is invalid after correction attempts."""
    pass


def validate_result_shape(
    result: Any,
    intent: IntentType
) -> Tuple[bool, Optional[str], Any]:
    """
    Validate whether the execution result matches the expected
    structure for the given intent.

    Returns:
        (ok, error_message, normalized_result)

    IMPORTANT:
    - This function must NEVER crash the pipeline.
    - It only reports problems; agentic repair happens elsewhere.
    """

    # --------------------------------------------------
    # NULL RESULT
    # --------------------------------------------------
    if result is None:
        return False, "Result is empty", None

    # --------------------------------------------------
    # SCALAR
    # --------------------------------------------------
    if intent == IntentType.SCALAR:
        if isinstance(result, (pd.Series, pd.DataFrame)):
            if len(result) != 1:
                return False, "Scalar intent must return exactly one value", None
        return True, None, result

    # --------------------------------------------------
    # TABULAR
    # --------------------------------------------------
    if intent == IntentType.TABULAR:
        if not isinstance(result, pd.DataFrame):
            return False, "Tabular intent must return a DataFrame", None
        return True, None, result

    # --------------------------------------------------
    # RANKING
    # --------------------------------------------------
    if intent == IntentType.RANKING:
        if not isinstance(result, pd.DataFrame):
            return False, "Ranking intent must return tabular data", None

        if len(result) == 0:
            return False, "Ranking returned no rows", None

        # UX safety cap (non-fatal)
        if len(result) > 50:
            result = result.head(50)

        return True, None, result

    # --------------------------------------------------
    # TIME SERIES
    # --------------------------------------------------
    if intent == IntentType.TIME_SERIES:
        if not isinstance(result, pd.DataFrame):
            return False, "Time-series intent must return a DataFrame", None

        if len(result) < 2:
            return False, "Time-series must contain multiple time points", None

        return True, None, result

    # --------------------------------------------------
    # BOOLEAN
    # --------------------------------------------------
    if intent == IntentType.BOOLEAN:
        if not isinstance(result, (bool, int)):
            return False, "Boolean intent must return a boolean-like value", None
        return True, None, result

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------
    return True, None, result
