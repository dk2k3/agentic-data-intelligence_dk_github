from langchain_community.llms import Ollama
import re
import os

_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _clean_pandas_code(code: str) -> str:
    """
    Clean LLM-generated Pandas code:
    - Remove markdown
    - Remove imports
    """

    code = re.sub(r"```python", "", code, flags=re.IGNORECASE)
    code = re.sub(r"```", "", code)

    lines = code.splitlines()
    cleaned_lines = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith(("import", "from "))
    ]

    cleaned_code = " ".join(cleaned_lines)

    forbidden = ["exec(", "eval(", "__", "open(", "os.", "sys."]
    if any(tok in cleaned_code for tok in forbidden):
        raise ValueError("Unsafe Pandas code detected")

    if not cleaned_code.startswith("df"):
        raise ValueError("Invalid Pandas code: must start with df")

    return cleaned_code


def _extract_groupby_metric(code: str) -> tuple[str | None, str | None]:
    """
    Extract (groupby_column, metric_column)
    Example:
    df.groupby('artist_name')['artist_popularity']
    """
    group_match = re.search(r"groupby\(\s*['\"]([^'\"]+)['\"]\s*\)", code)
    metric_match = re.search(r"\[\s*['\"]([^'\"]+)['\"]\s*\]", code)

    group_col = group_match.group(1) if group_match else None
    metric_col = metric_match.group(1) if metric_match else None

    return group_col, metric_col


def generate_pandas_code(question: str, df_schema: dict) -> str:
    """
    Convert a natural-language question into a SAFE Pandas expression.
    """

    llm = Ollama(model="llama3.1", base_url=_OLLAMA_BASE_URL)

    prompt = f"""
You are a senior data analyst.

Convert the user question into ONE Pandas expression.

STRICT RULES:
- Use dataframe name: df
- NO imports
- NO markdown
- NO explanations
- ONE expression only

ENTITY QUESTIONS ("who", "which"):
- MUST group by entity
- MUST aggregate
- MUST return entity + metric

POPULARITY / SCORE QUESTIONS:
- Use mean()

IMPORTANT:
- After aggregation, ALWAYS do:
  .reset_index().nlargest(n, metric_column)

DataFrame schema:
{df_schema}

User question:
{question}
"""

    raw_code = llm.invoke(prompt)
    cleaned_code = _clean_pandas_code(raw_code)

    # Detect groupby + metric
    group_col, metric_col = _extract_groupby_metric(cleaned_code)

    if group_col and metric_col:
        # Determine n (default 10, or 1 if "most")
        n = 1 if "most" in question.lower() else 10

        # 🔒 FORCE SAFE, CANONICAL FORM
        cleaned_code = (
            f"df.groupby('{group_col}')['{metric_col}']"
            f".mean().reset_index().nlargest({n}, '{metric_col}')"
        )

    return cleaned_code
