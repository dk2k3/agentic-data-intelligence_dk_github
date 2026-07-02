"""
Chart Agent
-----------
Generates a Plotly-compatible chart spec from a result + ExecutionPlan.
Uses ChartType from the plan — never guesses from the result alone.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import numpy as np

from app.schemas.execution_plan import ChartType, ExecutionPlan
from app.core.logger import logger


def _to_series(result: Any) -> tuple[list, list, str, str]:
    """
    Normalise any result into (x_vals, y_vals, x_label, y_label).
    Returns ([], [], "", "") if result is not plottable.
    """
    if isinstance(result, list) and result and isinstance(result[0], dict):
        keys = list(result[0].keys())
        if len(keys) >= 2:
            xk, yk = keys[0], keys[1]
            return (
                [str(r.get(xk, "")) for r in result],
                [r.get(yk) for r in result],
                xk, yk,
            )

    if isinstance(result, pd.Series):
        return (
            result.index.astype(str).tolist(),
            result.values.tolist(),
            str(result.index.name or "index"),
            str(result.name or "value"),
        )

    if isinstance(result, pd.DataFrame) and result.shape[1] >= 2:
        xk = str(result.columns[0])
        yk = str(result.columns[1])
        return (
            result[xk].astype(str).tolist(),
            result[yk].tolist(),
            xk, yk,
        )

    return [], [], "", ""


def generate_chart(result: Any,
                   plan: Optional[ExecutionPlan] = None,
                   chart_type: str = "auto") -> Dict:
    """
    Build a Plotly figure dict.

    Args:
        result      : execution result (list of dicts, DataFrame, Series, scalar)
        plan        : ExecutionPlan (preferred source of chart_type)
        chart_type  : fallback string if plan is None
    """
    # Resolve chart type from plan first, then kwarg
    ct: str = chart_type
    if plan is not None:
        ct = plan.chart_type.value

    # Scalar result
    if isinstance(result, (int, float, bool, np.number)):
        return {
            "data": [],
            "layout": {
                "annotations": [{
                    "text": f"Value: {result}",
                    "xref": "paper", "yref": "paper",
                    "showarrow": False, "font": {"size": 20},
                }],
                "title": "Result",
            },
        }

    x_vals, y_vals, x_label, y_label = _to_series(result)

    if not x_vals:
        return {"data": [], "layout": {"title": "No visualization available"}}

    title = f"{y_label} by {x_label}" if x_label and y_label else "Result"

    # Resolve auto
    if ct == "auto":
        # Use line for time-period x-axis
        try:
            if x_vals and str(x_vals[0]).isdigit() or "-" in str(x_vals[0]):
                ct = "line"
            else:
                ct = "bar"
        except Exception:
            ct = "bar"

    # Build trace
    if ct == "pie":
        trace = {"type": "pie", "labels": [str(v) for v in x_vals], "values": y_vals}
        layout = {"title": title}

    elif ct == "histogram":
        trace = {"type": "histogram", "x": y_vals, "name": y_label}
        layout = {
            "title": f"Distribution of {y_label}",
            "xaxis": {"title": y_label},
            "yaxis": {"title": "Count"},
        }

    elif ct == "scatter":
        trace = {"type": "scatter", "mode": "markers", "x": x_vals, "y": y_vals}
        layout = {"title": title, "xaxis": {"title": x_label}, "yaxis": {"title": y_label}}

    elif ct in ("line", "trend"):
        trace = {"type": "scatter", "mode": "lines+markers", "x": x_vals, "y": y_vals}
        layout = {"title": title, "xaxis": {"title": x_label}, "yaxis": {"title": y_label}}

    elif ct == "heatmap":
        # For heatmap results (correlation matrix) result should already be a matrix
        if isinstance(result, pd.DataFrame):
            numeric_df = result.select_dtypes(include=[np.number])
            trace = {
                "type": "heatmap",
                "z": numeric_df.values.tolist(),
                "x": list(numeric_df.columns),
                "y": list(numeric_df.index.astype(str)),
                "colorscale": "RdBu",
            }
            layout = {"title": "Correlation Matrix"}
        else:
            trace = {"type": "bar", "x": x_vals, "y": y_vals}
            layout = {"title": title}

    else:
        # bar (default)
        trace = {"type": "bar", "x": x_vals, "y": y_vals}
        layout = {"title": title, "xaxis": {"title": x_label}, "yaxis": {"title": y_label}}

    return {"data": [trace], "layout": layout}
