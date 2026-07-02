import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Any


def _normalize_scalar(value: Any):
    if value is None:
        return None

    if isinstance(value, (np.integer, np.floating)):
        return value.item()

    if isinstance(value, (np.bool_, bool)):
        return bool(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None

    return value


def normalize_result(result: Any):
    """
    Convert ANY Pandas / NumPy / Python output into JSON-safe data.
    Guaranteed not to raise serialization errors.
    """

    # -------------------------
    # Pandas DataFrame
    # -------------------------
    if isinstance(result, pd.DataFrame):
        df = result.copy()

        # Reset index safely
        df = df.reset_index(drop=False)

        # Replace NaN / NaT
        df = df.replace({np.nan: None})

        # Convert datetimes
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].astype(str)

        return df.to_dict(orient="records")

    # -------------------------
    # Pandas Series
    # -------------------------
    if isinstance(result, pd.Series):
        series = result.copy()
        series = series.replace({np.nan: None})

        if series.index is not None:
            return [
                {
                    "key": _normalize_scalar(k),
                    "value": _normalize_scalar(v),
                }
                for k, v in series.items()
            ]

        return [_normalize_scalar(v) for v in series.tolist()]

    # -------------------------
    # NumPy array
    # -------------------------
    if isinstance(result, np.ndarray):
        return [_normalize_scalar(v) for v in result.tolist()]

    # -------------------------
    # Dict
    # -------------------------
    if isinstance(result, dict):
        return {
            str(k): normalize_result(v)
            for k, v in result.items()
        }

    # -------------------------
    # List / Tuple
    # -------------------------
    if isinstance(result, (list, tuple)):
        return [normalize_result(v) for v in result]

    # -------------------------
    # Scalar
    # -------------------------
    return _normalize_scalar(result)
