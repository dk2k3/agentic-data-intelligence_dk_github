import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from api_client import (
    check_backend_health,
    upload_dataset,
    get_dataset_summary,
    get_dataset_insights,
    ask_question,
)

st.set_page_config(page_title="Agentic AI Data Intelligence Platform", layout="wide")
st.title("Agentic AI Data Intelligence Platform")
st.markdown("### Domain-Agnostic Analytics Dashboard")
st.divider()

# ── Backend status ────────────────────────────────────────────────────────────
st.subheader("Backend Status")
health = check_backend_health()
if health.get("status") == "running":
    st.success("Backend is running")
else:
    st.error("Backend is not reachable")
    st.stop()

st.divider()

# ── Upload ────────────────────────────────────────────────────────────────────
st.subheader("Upload Dataset")
uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])

if uploaded_file and st.button("Upload Dataset"):
    with st.spinner("Uploading..."):
        resp = upload_dataset(uploaded_file)
    if "error" in resp:
        st.error(resp["error"])
        st.stop()
    st.session_state["dataset_id"] = resp["dataset_id"]
    st.success("Dataset uploaded. AI processing started.")

st.divider()

# ── Dataset understanding ─────────────────────────────────────────────────────
if "dataset_id" in st.session_state:
    dataset_id = st.session_state["dataset_id"]
    st.header("Dataset Understanding")
    data = get_dataset_summary(dataset_id)

    if data.get("status") == "processing":
        st.info("AI is analysing your dataset — this may take 1–3 min. You can already ask questions.")
        if st.button("Refresh Analysis"):
            st.rerun()
    elif "error" in data:
        st.error(data["error"])
    elif "summary" in data:
        summary = data["summary"]
        st.success("Dataset understanding complete")
        if isinstance(summary, dict):
            st.markdown(f"**Dataset Type:** {summary.get('dataset_type', 'Unknown')}")
            if summary.get("important_columns"):
                st.markdown("**Important Columns**")
                for col in summary["important_columns"]:
                    st.write(f"- **{col.get('column_name')}** (importance: {col.get('importance')})")
            if summary.get("suggested_questions"):
                st.markdown("**Suggested Questions**")
                for q in summary["suggested_questions"]:
                    st.write(f"- {q}")
        else:
            st.text(str(summary))

    st.divider()
    st.header("AI-Generated Insights")
    insights_data = get_dataset_insights(dataset_id)
    if insights_data.get("status") == "processing":
        st.info("Insights still generating…")
        if st.button("Refresh Insights"):
            st.rerun()
    elif insights_data.get("insights"):
        st.markdown(insights_data["insights"])

st.divider()

# ── Ask questions ─────────────────────────────────────────────────────────────
if "dataset_id" in st.session_state:
    st.header("Ask Questions About Your Dataset")

    col1, col2 = st.columns([3, 1])
    with col1:
        question = st.text_input(
            "Ask a question in plain English",
            placeholder="e.g. Top 10 products by revenue, Monthly sales trend, Correlations"
        )
    with col2:
        chart_choice = st.selectbox(
            "Chart Type",
            options=["Auto", "Bar", "Line", "Pie", "Scatter", "Histogram", "None"],
            index=0,
        )

    if question and st.button("Ask"):
        with st.spinner("Analysing…"):
            chart_override = None if chart_choice == "Auto" else chart_choice.lower()
            result = ask_question(st.session_state["dataset_id"], question,
                                  chart_override=chart_override)

        if "error" in result:
            st.error(result["error"])
            st.stop()

        # Unsupported query
        if not result.get("is_executable", True):
            st.warning(f"⚠ This query cannot be executed: {result.get('result', '')}")
            st.stop()

        # ── Execution plan ────────────────────────────────────────────────
        with st.expander("Execution Plan", expanded=False):
            st.json(result.get("execution_plan", {}))

        # ── Validation issues ─────────────────────────────────────────────
        issues = result.get("validation_issues", [])
        for issue in issues:
            sev = issue.get("severity", "info")
            msg = issue.get("message", "")
            if sev == "error":
                st.error(f"Validation error: {msg}")
            elif sev == "warning":
                st.warning(f"Warning: {msg}")
            else:
                st.info(f"Info: {msg}")

        # ── Generated code ────────────────────────────────────────────────
        st.subheader("Generated Pandas Code")
        st.code(result.get("generated_pandas", ""), language="python")

        if result.get("generated_sql"):
            with st.expander("Equivalent SQL (reference only)"):
                st.code(result["generated_sql"], language="sql")

        # ── Result ────────────────────────────────────────────────────────
        st.subheader("Result")
        data_result = result.get("result")

        # --- Recommendation / Optimisation cards -------------------------
        if isinstance(data_result, dict) and "cards" in data_result:
            rec = data_result

            st.markdown(f"**Entity analysed:** `{rec.get('entity_column', '')}` | "
                        f"**Signals:** {', '.join(rec.get('metric_columns', []))} | "
                        f"**Candidates:** {rec.get('total_candidates', 0)}")

            st.markdown(rec.get("scoring_rationale", ""))

            for card in rec.get("cards", []):
                grade_colour = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}
                icon = grade_colour.get(card.get("grade", "F"), "⚪")
                with st.expander(
                    f"{icon} #{card['rank']} **{card['entity']}** — "
                    f"Score: {card['composite_score']:.1f}/100 (Grade {card['grade']})",
                    expanded=card["rank"] <= 3,
                ):
                    st.markdown(card.get("rationale", ""))
                    st.markdown(f"**Action:** {card.get('action', '')}")

                    # Signal breakdown table
                    sigs = card.get("signals", [])
                    if sigs:
                        import pandas as pd
                        sig_df = pd.DataFrame([{
                            "Signal": s["column"],
                            "Raw Value": f"{s['raw_value']:,.3f}",
                            "Normalised": f"{s['normalised']:.2f}",
                            "Weight": f"{s['weight']:.1%}",
                            "Direction": s["direction"].replace("_", " "),
                            "Contribution": f"{s['contribution']:.3f}",
                        } for s in sigs])
                        st.dataframe(sig_df, use_container_width=True, hide_index=True)

                    # Evidence rows
                    ev = card.get("evidence_rows", [])
                    if ev:
                        st.caption("Sample evidence rows:")
                        st.dataframe(pd.DataFrame(ev), use_container_width=True, hide_index=True)

        elif isinstance(data_result, str):
            st.markdown(data_result)
        elif isinstance(data_result, (int, float)):
            st.metric(label="Result", value=f"{data_result:,.4g}")
        elif isinstance(data_result, list) and data_result:
            st.dataframe(pd.DataFrame(data_result), use_container_width=True)
        elif isinstance(data_result, dict):
            st.json(data_result)
        else:
            st.info("No data returned.")

        # ── Confidence ────────────────────────────────────────────────────
        st.subheader("Confidence")
        conf = result.get("confidence", 0)
        conf_col1, conf_col2 = st.columns([1, 3])
        with conf_col1:
            st.metric("Score", f"{conf:.0%}")
        with conf_col2:
            st.caption(result.get("confidence_explanation", ""))

        # ── Explanation ───────────────────────────────────────────────────
        if result.get("explanation"):
            st.subheader("Explanation")
            st.markdown(result["explanation"])

        # ── Insights ─────────────────────────────────────────────────────
        if result.get("insights"):
            st.subheader("Insights")
            st.markdown(result["insights"])

        # ── Recommendations ───────────────────────────────────────────────
        recs = result.get("recommendations", [])
        if recs:
            st.subheader("Recommendations")
            for r in recs:
                st.write(f"→ {r}")

        # ── Visualization ─────────────────────────────────────────────────
        chart_spec = result.get("chart")
        is_rec_result = isinstance(data_result, dict) and "cards" in data_result
        if (
            chart_spec
            and not is_rec_result
            and chart_choice != "None"
            and result.get("chart_preference") != "none"
            and isinstance(data_result, list)
            and len(data_result) > 0
        ):
            st.subheader("Visualization")
            try:
                fig = go.Figure(chart_spec)
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.warning("Chart could not be rendered for this result type.")

        # ── Follow-up questions ───────────────────────────────────────────
        fqs = result.get("followup_questions", [])
        if fqs:
            st.subheader("Suggested Follow-up Questions")
            for i, q in enumerate(fqs, 1):
                st.write(f"{i}. {q}")
