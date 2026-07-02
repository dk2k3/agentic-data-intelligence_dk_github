from langchain_community.llms import Ollama
import json
import re
import os

_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


class FollowUpQuestionAgent:
    """
    Suggests intelligent follow-up questions based on dataset and current analysis.
    """

    def __init__(self, model_name: str = "llama3.1"):
        self.llm = Ollama(model=model_name, base_url=_OLLAMA_BASE_URL, temperature=0.4)

    def suggest(
        self,
        dataset_summary: str,
        user_question: str,
        analysis_result: str
    ) -> list:
        """
        Returns a list of suggested follow-up questions.
        """

        prompt = f"""
You are a senior data analyst assisting a user.

Based on:
- the dataset summary
- the user's last question
- the analysis result

Suggest 3–5 insightful follow-up questions the user might want to ask next.

Rules:
- Questions must be specific and actionable
- Avoid repeating the same question
- Cover different analytical angles (trend, comparison, breakdown)
- Return ONLY valid JSON
- No markdown
- No explanations

Return format EXACTLY:

[
  "question 1",
  "question 2",
  "question 3"
]

Dataset summary:
{dataset_summary}

User question:
{user_question}

Analysis result:
{analysis_result}
"""

        raw = self.llm.invoke(prompt)
        cleaned = self._clean_output(raw)

        try:
            questions = json.loads(cleaned)
        except json.JSONDecodeError:
            questions = []

        return questions

    @staticmethod
    def _clean_output(text: str) -> str:
        """
        Extract clean JSON array from LLM output.
        """

        text = re.sub(r"```json", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```", "", text)
        text = text.strip()

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            return match.group(0)

        return "[]"
