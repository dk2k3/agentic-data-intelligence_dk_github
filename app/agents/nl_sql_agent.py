from langchain_community.llms import Ollama
import re
import os

_OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def generate_sql(question, schema_info, dataset_table):
    """
    Convert natural language question to SQL.
    """

    llm = Ollama(model="llama3.1", base_url=_OLLAMA_BASE_URL)

    prompt = f"""
    You are a senior data engineer.

    Convert the following user question into a VALID PostgreSQL SQL query.

    Rules:
    - Use ONLY the table: {dataset_table}
    - Use ONLY the provided columns
    - No markdown
    - No explanation
    - Only SQL

    Table schema:
    {schema_info}

    User question:
    {question}
    """

    sql = llm.invoke(prompt)

    # Cleanup safety
    sql = re.sub(r"```sql", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"```", "", sql)
    return sql.strip()
