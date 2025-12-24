from sklearn.linear_model import LinearRegression
from sklearn.cluster import KMeans
from sklearn.metrics import r2_score
from sklearn.preprocessing import StandardScaler

def run_ml(df, plan):
    """
    Run lightweight ML based on planner decision.
    """

    numeric_cols = plan["numeric_columns"]

    # Not enough data for ML
    if not plan["run_ml"] or len(numeric_cols) < 2:
        return {
            "status": "skipped",
            "reason": "Not enough numeric columns"
        }

    # Choose target: last numeric column
    target = numeric_cols[-1]
    features = numeric_cols[:-1]

    X = df[features]
    y = df[target]

    # REGRESSION
    if y.nunique() > 10:
        model = LinearRegression()
        model.fit(X, y)
        preds = model.predict(X)

        return {
            "model_type": "LinearRegression",
            "target": target,
            "features": features,
            "r2_score": round(r2_score(y, preds), 4)
        }

    # CLUSTERING
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=3, random_state=42)
    labels = kmeans.fit_predict(X_scaled)

    return {
        "model_type": "KMeans",
        "features": features,
        "clusters": 3,
        "inertia": round(kmeans.inertia_, 2)
    }
