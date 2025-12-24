import requests
from typing import Optional, Dict, Any
import os

BACKEND_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


# --------------------------------------------------
# Backend Health Check
# --------------------------------------------------
def check_backend_health() -> Dict[str, Any]:
    try:
        response = requests.get(
            f"{BACKEND_URL}/",
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# --------------------------------------------------
# Upload Dataset
# --------------------------------------------------
def upload_dataset(file) -> Dict[str, Any]:
    """
    Upload CSV dataset to backend.
    Returns dataset_id immediately (background processing).
    """
    try:
        files = {
            "file": (
                file.name,
                file.getvalue(),
                "text/csv"
            )
        }

        response = requests.post(
            f"{BACKEND_URL}/upload-dataset",
            files=files,
            timeout=120
        )
        response.raise_for_status()
        return response.json()

    except Exception as e:
        return {
            "error": str(e)
        }


# --------------------------------------------------
# Get Dataset Summary
# --------------------------------------------------
def get_dataset_summary(dataset_id: int) -> Dict[str, Any]:
    """
    Poll dataset understanding result.
    """
    try:
        response = requests.get(
            f"{BACKEND_URL}/dataset-summary/{dataset_id}",
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    except Exception as e:
        return {
            "error": str(e)
        }


# --------------------------------------------------
# Ask Question (NL → Pandas)
# --------------------------------------------------
def ask_question(
    dataset_id: int,
    question: str,
    chart_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ask analytical questions about dataset.

    chart_override:
        Optional chart preference from UI
        Example: "bar", "line", "pie", "none"
    """
    try:
        payload = {
            "dataset_id": dataset_id,
            "question": question
        }

        # Future-proof: send chart preference if provided
        if chart_override:
            payload["chart_override"] = chart_override

        response = requests.post(
            f"{BACKEND_URL}/ask",
            json=payload,   # ✅ CORRECT
            timeout=120
        )
        response.raise_for_status()
        return response.json()

    except Exception as e:
        return {
            "error": str(e)
        }
