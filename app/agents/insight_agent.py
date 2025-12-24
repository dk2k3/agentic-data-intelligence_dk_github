from langchain_community.llms import Ollama

def generate_insights(eda_results, sql_results):
    """
    Generate business insights using local LLM.
    """

    llm = Ollama(model="llama3.1")

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
