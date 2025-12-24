# Agentic AI Data Intelligence Platform

An agent-based AI analytics platform powered by **Ollama-hosted large language models (LLMs)** that transforms natural-language questions into safe, explainable data insights using modular reasoning agents, automated Pandas execution, and interactive visualizations.

---

## 🚀 Overview

The **Agentic AI Data Intelligence Platform** enables users to upload structured datasets and ask questions in plain English (e.g., *“top 5 product category sold”*, *“total revenue in 2023”*).  
The system interprets the query using **agentic reasoning**, generates validated analytics logic, executes it safely, and presents results through an interactive dashboard.

The platform is designed to be **robust, explainable, and production-ready**, with built-in self-correction and validation mechanisms.

---

## 🧠 Key Features

- Natural Language → Data Analytics using **Ollama-hosted LLMs**
- Modular **Agentic Architecture** for reasoning and execution
- Supports:
  - Scalar KPIs
  - Ranking queries (Top-N, Most/Least)
  - Tabular aggregations
  - Time-based analysis
- Automated **Pandas code generation** with safety constraints
- Self-correction loop for incomplete or ambiguous queries
- Interactive **Streamlit dashboard** with dynamic charts
- **FastAPI backend** with clean JSON APIs
- Fully **Dockerized** for reproducible deployment

---

## 🏗️ Agentic Architecture

The platform is built using a multi-agent reasoning pipeline:

- **Query Planner Agent** – Interprets intent, grouping, and aggregation
- **Metric Resolver Agent** – Identifies relevant numerical measures
- **Time Resolver Agent** – Handles temporal filters and granularity
- **Strict Pandas Generator** – Produces safe, deterministic Pandas code
- **Result Validator** – Ensures result shape correctness
- **Self-Correction Agent** – Repairs incomplete or ambiguous query plans
- **Chart Agent** – Selects appropriate visualizations
- **Explanation & Confidence Agents** – Provide transparency and reliability

All reasoning is powered by **local Ollama LLMs**, enabling privacy-preserving and offline-friendly execution.

---

## 🛠️ Tech Stack

- **Language:** Python
- **Backend:** FastAPI
- **Frontend:** Streamlit
- **Analytics:** Pandas, NumPy
- **Visualization:** Plotly
- **LLMs:** **Ollama (local LLM hosting)**
- **Orchestration:** LangChain-style agent flow
- **Containerization:** Docker, Docker Compose

---

## 📊 Example Questions

- Total revenue in 2023  
- Top 5 product category sold  
- Most expensive product  
- Sales trend over time  
- Revenue by customer or category  

---

## ▶️ Run Locally (Without Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
streamlit run dashboard/streamlit_app.py
