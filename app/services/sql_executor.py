from sqlalchemy import text


def execute_sql(db, sql):
    """
    Executes read-only SQL safely.
    """

    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER"]

    for word in forbidden:
        if word.lower() in sql.lower():
            raise ValueError("Unsafe SQL detected")

    result = db.execute(text(sql)).mappings().all()
    return [dict(row) for row in result]
