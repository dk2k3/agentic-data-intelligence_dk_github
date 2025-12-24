from langchain_community.llms import Ollama
import json
import re


class IntentClassifierAgent:
    """
    Classifies user intent from a natural language question.
    Returns a strict JSON object describing analytical intent.
    """

    def __init__(self, model_name: str = "llama3.1"):
        self.llm = Ollama(model=model_name, temperature=0.2)

    def classify_intent(self, question: str) -> dict:
        """
        Classify the user's analytical intent.
        """

        prompt = f"""
You are an expert data analyst assistant.

Your task is to classify the user's intent from the question.

Return ONLY valid JSON. Do NOT include explanations or markdown.

Allowed values:

DATA_INTENT:
- sum
- average
- count
- compare
- trend
- distribution
- top_k
- unknown

VISUALIZATION_INTENT:
- bar
- line
- pie
- histogram
- scatter
- auto

TIME_INTENT:
- year
- financial_year
- quarter
- month
- date_range
- none

ENTITY examples:
- product
- artist
- customer
- category
- none

Metric examples:
- sales
- revenue
- popularity
- followers
- quantity
- amount
- unknown

Return JSON format EXACTLY like this:

{{
  "data_intent": "...",
  "metric": "...",
  "entity": "...",
  "time_intent": "...",
  "visualization": "...",
  "confidence": 0.0
}}

User question:
{question}
"""

        raw_response = self.llm.invoke(prompt)

        cleaned = self._clean_llm_output(raw_response)

        try:
            intent = json.loads(cleaned)
        except json.JSONDecodeError:
            # Hard fallback to safe defaults
            intent = {
                "data_intent": "unknown",
                "metric": "unknown",
                "entity": "none",
                "time_intent": "none",
                "visualization": "auto",
                "confidence": 0.0
            }

        return intent

    @staticmethod
    def _clean_llm_output(text: str) -> str:
        """
        Removes markdown, code fences, and stray text.
        """

        text = re.sub(r"```json", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```", "", text)
        text = text.strip()

        # Extract first JSON block if extra text exists
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)

        return text
