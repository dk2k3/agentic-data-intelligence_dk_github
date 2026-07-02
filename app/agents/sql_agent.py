from sqlalchemy import text

def run_sql_analytics(db):
    """
    Run system-level SQL analytics (metadata only).
    """

    queries = {
        "total_datasets": """
            SELECT COUNT(*) AS total_datasets
            FROM datasets;
        """,

        "latest_dataset": """
            SELECT id, name, created_at
            FROM datasets
            ORDER BY created_at DESC
            LIMIT 1;
        """,

        "total_analysis_runs": """
            SELECT COUNT(*) AS total_runs
            FROM analysis_runs;
        """
    }

    results = {}

    for key, sql in queries.items():
        res = db.execute(text(sql)).mappings().all()
        results[key] = [dict(row) for row in res]

    return results
