def plan_analysis(df):
    """
    Decide what analysis steps to run based on dataset properties.
    """

    numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_columns = df.select_dtypes(exclude=["number"]).columns.tolist()

    plan = {
        "run_eda": True,
        "run_ml": False,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns
    }

    # Simple decision rules
    if len(numeric_columns) >= 2 and len(df) >= 50:
        plan["run_ml"] = True

    return plan
