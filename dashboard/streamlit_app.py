import streamlit as st
import time
import pandas as pd
import plotly.graph_objects as go

from api_client import (
    check_backend_health,
    upload_dataset,
    get_dataset_summary,
    ask_question
)

# ----------------------------
# Page Config
# ----------------------------
st.set_page_config(
    page_title="Agentic AI Data Intelligence Platform",
    layout="wide"
)

st.title("📊 Agentic AI Data Intelligence Platform")
st.markdown("### Interactive Agentic Analytics Dashboard")

st.divider()

# ----------------------------
# Backend Status
# ----------------------------
st.subheader("Backend Status")

health = check_backend_health()

if health.get("status") == "running":
    st.success("Backend is running")
else:
    st.error("Backend is not reachable")
    st.stop()

st.divider()

# ----------------------------
# Dataset Upload
# ----------------------------
st.subheader("📤 Upload Dataset")

uploaded_file = st.file_uploader(
    "Upload a CSV file",
    type=["csv"]
)

if uploaded_file and st.button("Upload Dataset"):
    with st.spinner("Uploading dataset..."):
        response = upload_dataset(uploaded_file)

    if "error" in response:
        st.error(response["error"])
        st.stop()

    st.session_state["dataset_id"] = response["dataset_id"]
    st.success("Dataset uploaded successfully. AI processing started.")

st.divider()

# ----------------------------
# Dataset Understanding
# ----------------------------
if "dataset_id" in st.session_state:
    dataset_id = st.session_state["dataset_id"]

    st.header("🧠 Dataset Understanding")

    summary = None

    with st.spinner("AI is analyzing the dataset..."):
        for _ in range(30):
            data = get_dataset_summary(dataset_id)

            if data.get("status") == "processing":
                time.sleep(2)
                continue

            if "summary" in data:
                summary = data["summary"]
                break

            if "error" in data:
                st.error(data["error"])
                break

    if summary:
        st.success("Dataset understanding completed")

        # ----------------------------
        # Structured Display
        # ----------------------------
        if isinstance(summary, dict):
            st.markdown("### 📌 Dataset Type")
            st.write(summary.get("dataset_type", "Unknown"))

            if "important_columns" in summary:
                st.markdown("### ⭐ Important Columns")
                for col in summary["important_columns"]:
                    st.write(
                        f"- **{col.get('column_name')}** "
                        f"(importance: {col.get('importance')})"
                    )

            if "suggested_questions" in summary:
                st.markdown("### 💡 Suggested Questions")
                for q in summary["suggested_questions"]:
                    st.write(f"- {q}")

            if "recommended_charts" in summary:
                st.markdown("### 📊 Recommended Charts")
                for chart in summary["recommended_charts"]:
                    st.json(chart)

        else:
            st.text(summary)

    else:
        st.warning("Dataset is still processing. Please wait or refresh.")

st.divider()

# ============================
# Ask Questions
# ============================
if "dataset_id" in st.session_state:
    st.header("💬 Ask Questions About Your Dataset")

    col1, col2 = st.columns([3, 1])

    with col1:
        question = st.text_input(
            "Ask a question in plain English",
            placeholder="e.g. Total revenue in 2023, Revenue by category"
        )

    with col2:
        chart_choice = st.selectbox(
            "Chart Type",
            options=["Auto", "Bar", "Line", "Pie", "None"],
            index=0
        )

    if question and st.button("Ask"):
        with st.spinner("Analyzing your question..."):
            chart_override = None if chart_choice == "Auto" else chart_choice.lower()
            result = ask_question(
                st.session_state["dataset_id"],
                question,
                chart_override=chart_override
            )

        if "error" in result:
            st.error(result["error"])
            st.stop()

        # ----------------------------
        # Query Plan
        # ----------------------------
        st.subheader("🧠 Query Plan")
        st.json(result.get("query_plan", {}))

        # ----------------------------
        # Generated Pandas Code
        # ----------------------------
        st.subheader("🧾 Generated Pandas Code")
        st.code(result.get("generated_pandas", ""), language="python")

        # ----------------------------
        # Result
        # ----------------------------
        st.subheader("📊 Result")

        data_result = result.get("result")

        if isinstance(data_result, (int, float)):
            st.metric(
                label="Result",
                value=f"{data_result:,.2f}"
            )

        elif isinstance(data_result, list) and len(data_result) > 0:
            df = pd.DataFrame(data_result)
            st.dataframe(df, use_container_width=True)

        else:
            st.info("No data returned")

        # ----------------------------
        # Visualization (UX-SAFE)
        # ----------------------------
        chart_spec = result.get("chart")

        if (
            chart_spec
            and chart_choice != "None"
            and isinstance(data_result, list)
            and len(data_result) > 0
        ):
            st.subheader("📈 Visualization")
            try:
                fig = go.Figure(chart_spec)
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.warning("Chart not applicable for this result.")

        elif chart_choice != "None":
            st.info(
                "ℹ️ A chart cannot be shown for a single-value result. "
                "Try asking for a breakdown (e.g. 'revenue by category' or 'by month')."
            )
