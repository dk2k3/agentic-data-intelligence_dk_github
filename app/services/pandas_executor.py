import pandas as pd
from typing import Any


class PandasExecutionError(RuntimeError):
    pass


def execute_pandas(df: pd.DataFrame, code: str) -> Any:
    """
    Execute generated pandas code in a restricted environment.

    Rules:
    - `df` is the input DataFrame
    - Code MUST assign output to variable named `result`
    - Only pandas operations are allowed
    """

    if not code or not isinstance(code, str):
        raise PandasExecutionError("Empty or invalid pandas code")

    # Restricted execution environment
    safe_globals = {
        "__builtins__": {},
        "pd": pd,
    }

    safe_locals = {
        "df": df.copy(),  # prevent mutation of original df
        "result": None,
    }

    try:
        exec(code, safe_globals, safe_locals)
    except Exception as e:
        raise PandasExecutionError(f"Pandas execution failed: {str(e)}")

    if "result" not in safe_locals:
        raise PandasExecutionError("Generated pandas code did not define `result`")

    return safe_locals["result"]
