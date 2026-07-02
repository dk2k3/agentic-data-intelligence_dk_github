def extract_schema(df):
    schema = []

    for col in df.columns:
        col_info = {
            "column_name": col,
            "data_type": str(df[col].dtype),
            "unique_values": int(df[col].nunique()),
            "missing_values": int(df[col].isnull().sum())
        }
        schema.append(col_info)

    return schema
