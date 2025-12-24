import pandas as pd
import numpy as np
from typing import Any, Dict, List


def generate_chart(result: Any) -> Dict:
    """
    Generate a Plotly-safe chart specification.
    Never raises. Always returns a valid dict.
    """

    # --------------------------------------------------
    # SCALAR RESULT
    # --------------------------------------------------
    if isinstance(result, (int, float, bool, np.number)):
        return {
            "data": [],
            "layout": {
                "title": "Result",
                "annotations": [
                    {
                        "text": f"Value: {result}",
                        "xref": "paper",
                        "yref": "paper",
                        "showarrow": False,
                        "font": {"size": 18},
                    }
                ],
            },
        }

    # --------------------------------------------------
    # NORMALIZED LIST OF DICTS (TABULAR)
    # --------------------------------------------------
    if isinstance(result, list) and result and isinstance(result[0], dict):
        keys = list(result[0].keys())
        if len(keys) >= 2:
            x_key, y_key = keys[0], keys[1]

            return {
                "data": [
                    {
                        "type": "bar",
                        "x": [row[x_key] for row in result],
                        "y": [row[y_key] for row in result],
                    }
                ],
                "layout": {
                    "title": f"{y_key} by {x_key}",
                    "xaxis": {"title": x_key},
                    "yaxis": {"title": y_key},
                },
            }

    # --------------------------------------------------
    # PANDAS SERIES
    # --------------------------------------------------
    if isinstance(result, pd.Series):
        return {
            "data": [
                {
                    "type": "bar",
                    "x": result.index.astype(str).tolist(),
                    "y": result.values.tolist(),
                }
            ],
            "layout": {
                "title": "Series Result",
                "xaxis": {"title": "Category"},
                "yaxis": {"title": "Value"},
            },
        }

    # --------------------------------------------------
    # PANDAS DATAFRAME
    # --------------------------------------------------
    if isinstance(result, pd.DataFrame) and result.shape[1] >= 2:
        x_col, y_col = result.columns[:2]

        chart_type = "line" if pd.api.types.is_datetime64_any_dtype(result[x_col]) else "bar"

        return {
            "data": [
                {
                    "type": chart_type,
                    "x": result[x_col].astype(str).tolist(),
                    "y": result[y_col].tolist(),
                }
            ],
            "layout": {
                "title": f"{y_col} by {x_col}",
                "xaxis": {"title": x_col},
                "yaxis": {"title": y_col},
            },
        }

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------
    return {
        "data": [],
        "layout": {
            "title": "No visualization available"
        },
    }
