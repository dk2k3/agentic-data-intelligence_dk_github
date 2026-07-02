from langchain_community.llms import Ollama
import json
import re
import os

_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _clean_llm_json(response: str) -> str:
    """
    Remove markdown code fences and extra text from LLM output.
    """
    # Remove ```json and ``` blocks
    response = re.sub(r"```json", "", response, flags=re.IGNORECASE)
    response = re.sub(r"```", "", response)

    # Trim whitespace
    return response.strip()


def understand_dataset(schema_info, eda_results):
    """
    Uses LLM to understand the dataset based on schema and EDA.
    """

    llm = Ollama(model="llama3.1", base_url=_OLLAMA_BASE_URL)

    prompt = f"""
    You are a senior data analyst.

    Given the following dataset information, analyze and respond in STRICT JSON.

    Dataset Schema:
    {schema_info}

    EDA Summary:
    {eda_results}

    Return ONLY valid JSON with:
    - dataset_type (string)
    - important_columns (list of objects with column_name + importance)
    - suggested_questions (list of strings)
    - recommended_charts (list of objects)

    Do NOT include markdown.
    Do NOT include explanations.
    """

    response = llm.invoke(prompt)

    try:
        cleaned = _clean_llm_json(response)
        return json.loads(cleaned)
    except Exception as e:
        return {
            "error": "LLM response could not be parsed",
            "raw_response": response,
            "exception": str(e)
        }
