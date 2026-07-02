from langchain_community.llms import Ollama
import json
import re
import os

_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


class ConfidenceScoringAgent:
    """
    Estimates confidence level for an analytical answer.
    """

    def __init__(self, model_name: str = "llama3.1"):
        self.llm = Ollama(model=model_name, base_url=_OLLAMA_BASE_URL, temperature=0.1)

    def score(
        self,
        question: str,
        pandas_code: str,
        result_preview: str
    ) -> dict:
        """
        Returns a confidence score and short explanation.
        """

        prompt = f"""
You are an AI quality auditor.

Evaluate how confident the system should be in the following analysis.

Rules:
- Score confidence from 0.0 (low) to 1.0 (high)
- Consider:
  - clarity of the question
  - correctness of the pandas logic
  - ambiguity of metrics or time
- Return ONLY valid JSON
- No markdown
- No explanations outside JSON

Return format EXACTLY:

{{
  "confidence": 0.0,
  "reason": "<short explanation>"
}}

User question:
{question}

Generated Pandas code:
{pandas_code}

Result preview:
{result_preview}
"""

        raw = self.llm.invoke(prompt)
        cleaned = self._clean_output(raw)

        try:
            score = json.loads(cleaned)
        except json.JSONDecodeError:
            score = {
                "confidence": 0.5,
                "reason": "Unable to reliably assess confidence"
            }

        return score

    @staticmethod
    def _clean_output(text: str) -> str:
        """
        Remove markdown and extract JSON.
        """

        text = re.sub(r"```json", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```", "", text)
        text = text.strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        return text
