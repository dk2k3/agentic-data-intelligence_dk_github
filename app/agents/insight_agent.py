from langchain_community.llms import Ollama
import os

_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def generate_insights(eda_results, sql_results):
    """
    Generate business insights using local LLM.
    """

    llm = Ollama(model="llama3.1", base_url=_OLLAMA_BASE_URL)

    prompt = f"""
    You are a senior data analyst.

    Based on the following analysis results, generate clear business insights.

    EDA Results:
    {eda_results}

    SQL System Analytics:
    {sql_results}

    Provide:
    1. Key observations
    2. Data quality issues
    3. Actionable recommendations
    """

    response = llm.invoke(prompt)

    return response
