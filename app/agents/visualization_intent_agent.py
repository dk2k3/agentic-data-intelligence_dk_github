from langchain_community.llms import Ollama
import json
import re
import os

_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


class VisualizationIntentAgent:
    """
    Extracts visualization intent from user question.
    """

    SUPPORTED_CHARTS = [
        "bar",
        "line",
        "pie",
        "histogram",
        "scatter",
        "auto"
    ]

    def __init__(self, model_name: str = "llama3.1"):
        self.llm = Ollama(model=model_name, base_url=_OLLAMA_BASE_URL, temperature=0.1)

    def detect(self, question: str) -> dict:
        """
        Detect visualization intent from the user question.
        """

        prompt = f"""
You are a visualization intent classifier.

Your task:
Detect whether the user explicitly requests a chart type.

Supported chart types:
- bar
- line
- pie
- histogram
- scatter

Rules:
- If no chart type is explicitly mentioned, return "auto"
- Return ONLY valid JSON
- No explanations
- No markdown

Return format EXACTLY:

{{
  "chart_type": "<bar|line|pie|histogram|scatter|auto>",
  "confidence": 0.0
}}

User question:
{question}
"""

        raw = self.llm.invoke(prompt)
        cleaned = self._clean_output(raw)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            result = {
                "chart_type": "auto",
                "confidence": 0.0
            }

        chart = result.get("chart_type", "auto")

        if chart not in self.SUPPORTED_CHARTS:
            result["chart_type"] = "auto"

        return result

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
