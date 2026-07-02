def run_eda(df):
    """
    Perform basic Exploratory Data Analysis.
    """

    # Summary statistics for numeric columns
    summary_stats = df.describe().to_dict()

    # Missing values per column
    missing_values = df.isnull().sum().to_dict()

    eda_results = {
        "summary_statistics": summary_stats,
        "missing_values": missing_values,
        "row_count": len(df),
        "column_count": len(df.columns)
    }

    return eda_results
