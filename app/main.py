"""
Agentic AI Data Intelligence Platform — FastAPI backend
=======================================================
New pipeline (domain-agnostic):

  Upload  →  SchemaUnderstandingAgent  →  (cached)
  Ask     →  IntentClassifierAgent
          →  MetricEntityExtractor
          →  ExecutionPlanner          →  ExecutionPlan
          →  QueryVerifier             →  validated plan
          →  PandasExecutorAgent       →  result + code
          →  SQLGeneratorAgent         →  sql (transparency)
          →  ChartAgent                →  chart spec
          →  ConfidenceEngine          →  score
          →  DomainReasoningAgent      →  explanation + insights
          →  FollowUpQuestionAgent     →  follow-ups
"""
from __future__ import annotations

import json
import os
import shutil
from contextlib import asynccontextmanager
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.db import SessionLocal, engine, get_db
from app import models

# Services
from app.services.data_loader import load_csv
from app.services.result_normalizer import normalize_result

# New pipeline agents
from app.agents.schema_understanding_agent import SchemaUnderstandingAgent
from app.agents.execution_planner import ExecutionPlanner
from app.agents.query_verifier import QueryVerifier
from app.agents.pandas_executor_agent import PandasExecutorAgent
from app.agents.sql_generator_agent import SQLGeneratorAgent
from app.agents.chart_agent import generate_chart
from app.agents.confidence_engine import ConfidenceEngine
from app.agents.domain_reasoning_agent import DomainReasoningAgent
from app.agents.recommendation_executor import (
    RecommendationExecutor,
    RecommendationResult,
    recommendation_result_to_dict,
)

# Legacy / LLM-enhanced agents (graceful degradation)
from app.agents.dataset_understanding_agent import understand_dataset
from app.agents.insight_agent import generate_insights
from app.agents.followup_question_agent import FollowUpQuestionAgent
from app.agents.eda_agent import run_eda
from app.services.schema_extractor import extract_schema
from app.agents.planner import plan_analysis
from app.agents.ml_agent import run_ml


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Agentic AI Data Intelligence Platform")
    models.Base.metadata.create_all(bind=engine)
    yield
    logger.info("Shutdown")


app = FastAPI(
    title="Agentic AI Data Intelligence Platform",
    version="2.0.0",
    lifespan=lifespan,
)

UPLOAD_DIR = "uploaded_datasets"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Shared singletons
_schema_agent          = SchemaUnderstandingAgent()
_planner               = ExecutionPlanner()
_verifier              = QueryVerifier()
_pandas_executor       = PandasExecutorAgent()
_sql_generator         = SQLGeneratorAgent()
_confidence_engine     = ConfidenceEngine()
_reasoning_agent       = DomainReasoningAgent()
_followup_agent        = FollowUpQuestionAgent()
_recommendation_executor = RecommendationExecutor()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    dataset_id: int
    question: str
    chart_override: Optional[str] = None   # "bar"|"line"|"pie"|"scatter"|"histogram"|"none"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/")
def health_check():
    return {"status": "running", "message": "Agentic AI Data Intelligence Platform v2 is live"}


@app.get("/health")
def health():
    """Dedicated health endpoint for Docker health checks and load balancers."""
    return {"status": "ok", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# Background dataset pipeline
# ---------------------------------------------------------------------------

def _process_dataset_background(dataset_id: int, file_path: str):
    db = SessionLocal()
    try:
        df = load_csv(file_path)
        eda_results  = run_eda(df)
        schema_info  = extract_schema(df)

        # ML (optional)
        try:
            ml_plan = plan_analysis(df)
            if ml_plan.get("run_ml"):
                run_ml(df, ml_plan)
        except Exception:
            logger.warning("ML analysis skipped")

        # LLM dataset understanding
        try:
            understanding = understand_dataset(schema_info, eda_results)
        except Exception as e:
            logger.warning(f"LLM understanding failed: {e}")
            understanding = {
                "dataset_type": "Unknown",
                "important_columns": [],
                "suggested_questions": [],
                "recommended_charts": [],
            }

        db.add(models.DatasetSummary(
            dataset_id=dataset_id,
            summary=json.dumps(understanding),
        ))
        db.commit()
        logger.info(f"Dataset summary saved for dataset_id={dataset_id}")

        # Insights
        try:
            insights_text = generate_insights(eda_results, {})
            db.add(models.Insight(dataset_id=dataset_id, content=insights_text))
            db.commit()
        except Exception:
            logger.warning("Insight generation skipped")

    except Exception:
        logger.exception("Background processing failed")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@app.post("/upload-dataset")
def upload_dataset(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    df = load_csv(file_path)
    dataset = models.Dataset(
        name=file.filename, file_path=file_path,
        rows=df.shape[0], columns=df.shape[1],
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    background_tasks.add_task(_process_dataset_background, dataset.id, file_path)
    return {"dataset_id": dataset.id, "status": "processing"}


# ---------------------------------------------------------------------------
# Dataset summary & insights
# ---------------------------------------------------------------------------

@app.get("/dataset-summary/{dataset_id}")
def get_dataset_summary(dataset_id: int, db: Session = Depends(get_db)):
    record = db.query(models.DatasetSummary).filter(
        models.DatasetSummary.dataset_id == dataset_id
    ).first()
    if not record:
        return {"status": "processing"}
    try:
        parsed = json.loads(record.summary)
    except Exception:
        parsed = record.summary
    return {"dataset_id": dataset_id, "summary": parsed}


@app.get("/dataset-insights/{dataset_id}")
def get_dataset_insights(dataset_id: int, db: Session = Depends(get_db)):
    record = (
        db.query(models.Insight)
        .filter(models.Insight.dataset_id == dataset_id)
        .order_by(models.Insight.created_at.desc())
        .first()
    )
    if not record:
        return {"status": "processing", "insights": None}
    return {"dataset_id": dataset_id, "insights": record.content}


# ---------------------------------------------------------------------------
# Descriptive question detection
# ---------------------------------------------------------------------------

_DESCRIPTIVE_KW = [
    "what is this dataset", "about this dataset", "tell me about",
    "describe this", "describe the dataset", "what does this dataset",
    "what kind of data", "overview", "what columns", "what fields",
    "summarize this", "summary of this", "what data do we have",
]

def _is_descriptive(q: str) -> bool:
    ql = q.lower().strip()
    return any(k in ql for k in _DESCRIPTIVE_KW)


# ---------------------------------------------------------------------------
# /ask  — main analytics endpoint
# ---------------------------------------------------------------------------

@app.post("/ask")
def ask_question(payload: AskRequest, db: Session = Depends(get_db)):
    logger.info(f"Question: {payload.question}")

    dataset = db.query(models.Dataset).filter(
        models.Dataset.id == payload.dataset_id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    df = load_csv(dataset.file_path)

    try:
        # ----------------------------------------------------------------
        # Early-exit: descriptive meta questions
        # ----------------------------------------------------------------
        if _is_descriptive(payload.question):
            summary_rec = db.query(models.DatasetSummary).filter(
                models.DatasetSummary.dataset_id == payload.dataset_id
            ).first()
            summary_data: Any = {}
            if summary_rec:
                try:
                    summary_data = json.loads(summary_rec.summary)
                except Exception:
                    summary_data = summary_rec.summary

            if isinstance(summary_data, dict):
                dataset_type = summary_data.get("dataset_type", "Structured")
                cols = summary_data.get("important_columns", [])
                col_names = [c.get("column_name", "") for c in cols[:5]]
                suggested = summary_data.get("suggested_questions", [])[:3]
                answer = (
                    f"This is a **{dataset_type}** dataset with "
                    f"{df.shape[0]:,} rows and {df.shape[1]} columns.\n\n"
                    f"**Key columns:** {', '.join(col_names) or 'see schema'}.\n\n"
                    + ("**You could ask:** " + "; ".join(suggested) if suggested else "")
                )
            else:
                answer = str(summary_data)

            return {
                "question": payload.question,
                "execution_plan": {},
                "generated_pandas": "",
                "generated_sql": None,
                "result": answer,
                "confidence": 1.0,
                "confidence_explanation": "Descriptive query answered from dataset summary.",
                "explanation": "Descriptive dataset overview.",
                "insights": "",
                "recommendations": [],
                "chart": None,
                "chart_preference": "none",
                "followup_questions": summary_data.get("suggested_questions", [])[:5]
                    if isinstance(summary_data, dict) else [],
                "validation_issues": [],
                "is_executable": True,
            }

        # ----------------------------------------------------------------
        # 1. Schema understanding (per-request — fast, cached in prod)
        # ----------------------------------------------------------------
        dataset_schema = _schema_agent.analyse(df)

        # ----------------------------------------------------------------
        # 2. Build execution plan
        # ----------------------------------------------------------------
        plan = _planner.build(payload.question, dataset_schema)

        # Override chart if user selected one in UI
        if payload.chart_override and payload.chart_override.lower() != "auto":
            from app.schemas.execution_plan import ChartType
            try:
                plan.chart_type = ChartType(payload.chart_override.lower())
            except ValueError:
                pass

        # ----------------------------------------------------------------
        # 3. Verify plan
        # ----------------------------------------------------------------
        plan = _verifier.verify(plan)

        # ----------------------------------------------------------------
        # 4. Handle unsupported queries gracefully
        # ----------------------------------------------------------------
        if not plan.is_executable:
            return {
                "question": payload.question,
                "execution_plan": plan.to_dict(),
                "generated_pandas": "",
                "generated_sql": None,
                "result": plan.unsupported_reason,
                "confidence": 0.0,
                "confidence_explanation": plan.unsupported_reason,
                "explanation": plan.unsupported_reason,
                "insights": "",
                "recommendations": [],
                "chart": None,
                "chart_preference": "none",
                "followup_questions": [],
                "validation_issues": [i.model_dump() for i in plan.validation_issues],
                "is_executable": False,
            }

        # ----------------------------------------------------------------
        # 5. Execute
        # ----------------------------------------------------------------
        from app.schemas.execution_plan import QueryIntent as QI

        is_recommendation = plan.intent in (QI.RECOMMENDATION, QI.OPTIMIZATION)

        if is_recommendation:
            # ---- Decision-support path ----------------------------------
            raw_result, pandas_code = _recommendation_executor.execute(df, plan)
        else:
            # ---- Standard analytics path --------------------------------
            raw_result, pandas_code = _pandas_executor.execute(df, plan)

        # ----------------------------------------------------------------
        # 6. Generate SQL (transparency — not executed)
        # ----------------------------------------------------------------
        table_name = (
            dataset.name.replace(".csv", "").replace(" ", "_").replace("-", "_")
        )
        generated_sql = _sql_generator.generate(plan, table_name)

        # ----------------------------------------------------------------
        # 7. Normalise result
        # ----------------------------------------------------------------
        if isinstance(raw_result, RecommendationResult):
            result_data = recommendation_result_to_dict(raw_result)
        else:
            result_data = normalize_result(raw_result)

        # ----------------------------------------------------------------
        # 8. Chart
        # ----------------------------------------------------------------
        chart = None
        if payload.chart_override and payload.chart_override.lower() == "none":
            chart = None
        else:
            try:
                chart = generate_chart(raw_result, plan=plan)
            except Exception as e:
                logger.warning(f"Chart generation failed: {e}")

        # ----------------------------------------------------------------
        # 9. Confidence
        # ----------------------------------------------------------------
        confidence = _confidence_engine.compute(plan, result_data)
        confidence_explanation = _confidence_engine.explain(plan, confidence)

        # ----------------------------------------------------------------
        # 10. Explanation + insights + recommendations
        # ----------------------------------------------------------------
        explanation    = _reasoning_agent.generate_explanation(plan)
        insights       = _reasoning_agent.generate_insights(plan, result_data)
        recommendations = _reasoning_agent.generate_recommendations(plan, result_data)

        # ----------------------------------------------------------------
        # 11. Follow-up questions (LLM — graceful skip)
        # ----------------------------------------------------------------
        followup_questions: list = []
        try:
            summary_rec = db.query(models.DatasetSummary).filter(
                models.DatasetSummary.dataset_id == payload.dataset_id
            ).first()
            ds = summary_rec.summary if summary_rec else ""
            followup_questions = _followup_agent.suggest(
                dataset_summary=ds,
                user_question=payload.question,
                analysis_result=str(result_data)[:500],
            )
        except Exception as e:
            logger.warning(f"Follow-up questions skipped: {e}")

        # ----------------------------------------------------------------
        # 12. Persist history
        # ----------------------------------------------------------------
        try:
            db.add(models.QueryHistory(
                dataset_id=payload.dataset_id,
                question=payload.question,
                result_preview=str(result_data)[:500],
                pandas_code=pandas_code,
                confidence=str(confidence),
            ))
            db.commit()
        except Exception as e:
            logger.warning(f"Query history save skipped: {e}")

        # ----------------------------------------------------------------
        # Response
        # ----------------------------------------------------------------
        return {
            "question": payload.question,
            # Plan (serialised without the heavy schema object)
            "execution_plan": plan.to_dict(),
            # Code
            "generated_pandas": pandas_code,
            "generated_sql": generated_sql,
            # Result
            "result": result_data,
            # Confidence
            "confidence": confidence,
            "confidence_explanation": confidence_explanation,
            # Reasoning
            "explanation": explanation,
            "insights": insights,
            "recommendations": recommendations,
            # Visualization
            "chart": chart,
            "chart_preference": plan.chart_type.value,
            # Follow-ups
            "followup_questions": followup_questions,
            # Diagnostics
            "validation_issues": [i.model_dump() for i in plan.validation_issues],
            "is_executable": plan.is_executable,
        }

    except Exception as e:
        logger.exception("Question answering failed")
        raise HTTPException(status_code=500, detail=str(e))
