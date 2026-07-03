"""
Query Enhancer Agent
--------------------
ALWAYS runs before any other pipeline step (no skip heuristic).

Given the user's raw question + the actual column names and their types,
the LLM rewrites the question into a precise analytical query that:
  - Uses the EXACT column names from the dataset
  - Resolves vague words ("sold" → QuantitySold, "price" → UnitPrice)
  - Resolves broken English ("top sold products names with its price")
  - Distinguishes entity columns (ProductName) from ID columns (ProductID)
  - Specifies the analysis type (rank/aggregate/filter/trend/etc.)

This means the downstream rule-based pipeline receives a clean,
unambiguous question every time — regardless of how the user typed it.

Graceful degradation: if Ollama is unavailable, returns the original question.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from app.core.logger import logger


_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")


class QueryEnhancerAgent:
    """
    Rewrites every user question into a precise, column-aware analytical query.
    Works for any dataset, any column names, any language quality.
    """

    def __init__(self):
        self._llm = None
        self._available = False
        self._init_llm()

    def _init_llm(self):
        try:
            from langchain_community.llms import Ollama
            self._llm = Ollama(
                model=_MODEL,
                base_url=_OLLAMA_BASE_URL,
                temperature=0.0,  # deterministic
            )
            self._available = True
            logger.info("QueryEnhancerAgent: LLM ready")
        except Exception as e:
            logger.warning(f"QueryEnhancerAgent: LLM unavailable ({e})")
            self._available = False

    def enhance(
        self,
        raw_question: str,
        column_names: List[str],
        column_types: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Rewrite the raw question into a precise analytical question.

        Args:
            raw_question:  what the user typed
            column_names:  actual column names in the dataset
            column_types:  dict of {col_name: 'numeric'|'categorical'|'date'|'id'}

        Returns:
            Rewritten question, or original if LLM unavailable.
        """
        if not self._available or self._llm is None:
            return raw_question

        # Build a rich schema description for the LLM
        schema_lines = []
        for col in column_names[:40]:  # cap at 40 columns
            ctype = (column_types or {}).get(col, "unknown")
            schema_lines.append(f"  - {col} ({ctype})")
        schema_str = "\n".join(schema_lines)

        prompt = f"""You are a data analyst assistant. A user asked a question about a dataset.
Your ONLY job: rewrite their question as ONE precise analytical question using the exact column names.

DATASET COLUMNS:
{schema_str}

USER QUESTION: "{raw_question}"

RULES:
1. Output ONLY the rewritten question — no explanation, no preamble, no markdown.
2. Use EXACT column names from the dataset (case-sensitive).
3. Map the user's words to real columns using meaning/semantics — not just exact word match:
   - "sold", "sell", "purchase", "buy", "transaction" → numeric column for quantity/sales/amount
   - "name", "names", "title", "label" → categorical name column (NEVER an ID column like ProductID)
   - "price", "cost", "rate", "charge", "fee" → numeric price/cost/unit_price column
   - "popular", "popularity", "famous", "trending", "hot" → popularity/score/rating column
   - "category", "type", "group", "kind", "segment" → categorical grouping column
   - "employee", "staff", "worker", "person", "who" → categorical name/employee column
   - "earn", "earning", "income", "pay", "wage", "salary" → numeric salary/income column
   - "region", "area", "place", "location", "where" → categorical location/region column
   - Any "XID" or "X_id" column (ProductID, CustomerID) is an identifier — use the name column instead
4. Choose the correct aggregation based on context:
   - "top sold", "most purchased", "most bought" → total SUM of quantity/sales
   - "most popular", "highest rated", "best scored" → MAX or MEAN of the score
   - "average X per Y" → MEAN aggregation
   - "total X per Y" → SUM aggregation
5. Include ALL columns the user asked to see:
   - "with its price" → include the price column in the result
   - "show name and quantity" → include both name and quantity columns
   - "along with category" → include category column
6. Produce a complete analytical statement:
   - For ranking: "Show the top [N] [entity_col] by total [metric_col], also showing [display_col]"
   - For aggregation: "What is the [agg] of [metric_col] grouped by [group_col]?"
   - For filtering: "Show all rows where [col] [operator] [value]"
7. Keep to 1-2 sentences. No markdown. No explanation.

Rewritten question:"""

        try:
            response = self._llm.invoke(prompt)
            enhanced = self._clean(response)

            if not enhanced or len(enhanced) < 5:
                logger.warning("QueryEnhancer: LLM returned empty, using original")
                return raw_question

            logger.info(f"QueryEnhancer: '{raw_question[:60]}' → '{enhanced[:80]}'")
            return enhanced

        except Exception as e:
            logger.warning(f"QueryEnhancer: call failed ({e}), using original")
            return raw_question

    @staticmethod
    def _clean(text: str) -> str:
        """Strip all LLM output artifacts and return clean question."""
        # Remove common prefixes LLMs add
        text = re.sub(
            r"^(rewritten question:?\s*|answer:?\s*|output:?\s*|here'?s?\s*(the\s*)?rewritten.*?:\s*)",
            "", text, flags=re.IGNORECASE
        )
        # Remove markdown
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Strip quotes and whitespace
        text = text.strip().strip('"').strip("'").strip()
        # Take first line only if multi-line response
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return lines[0] if lines else text
