from fastapi import FastAPI, UploadFile, File, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import os
import shutil
import pandas as pd
import numpy as np
from typing import Any

from app.db import engine, get_db, SessionLocal
from app import models

from app.services.data_loader import load_csv
from app.services.schema_extractor import extract_schema
from app.services.pandas_executor import execute_pandas

from app.agents.query_planner import build_query_plan
from app.agents.strict_pandas_generator import generate_pandas_from_plan
from app.agents.result_validator import validate_result_shape
from app.agents.self_correction_agent import needs_correction, apply_self_correction
from app.agents.confidence_agent import calculate_confidence
from app.agents.explanation_agent import generate_explanation
from app.agents.chart_agent import generate_chart
from app.agents.eda_agent import run_eda
from app.agents.dataset_understanding_agent import understand_dataset

from app.core.logger import logger


# --------------------------------------------------
# APP LIFESPAN (SAFE DB INIT)
# --------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")
    models.Base.metadata.create_all(bind=engine)
    yield
    logger.info("Shutting down application")


app = FastAPI(
    title="Agentic AI Data Intelligence Platform",
    lifespan=lifespan
)

UPLOAD_DIR = "uploaded_datasets"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# --------------------------------------------------
# REQUEST SCHEMAS
# --------------------------------------------------
class AskRequest(BaseModel):
    dataset_id: int
    question: str


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------
@app.get("/")
def health_check():
    return {
        "status": "running",
        "message": "Agentic AI Data Intelligence Platform is live"
    }


# --------------------------------------------------
# BACKGROUND DATASET PIPELINE
# --------------------------------------------------
def process_dataset_background(dataset_id: int, file_path: str):
    db = SessionLocal()
    try:
        df = load_csv(file_path)
        eda_results = run_eda(df)
        schema_info = extract_schema(df)
        understanding = understand_dataset(schema_info, eda_results)

        summary = models.DatasetSummary(
            dataset_id=dataset_id,
            summary=str(understanding)
        )

        db.add(summary)
        db.commit()

    except Exception:
        logger.exception("Background processing failed")

    finally:
        db.close()


# --------------------------------------------------
# UPLOAD DATASET
# --------------------------------------------------
@app.post("/upload-dataset")
def upload_dataset(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    df = load_csv(file_path)

    dataset = models.Dataset(
        name=file.filename,
        file_path=file_path,
        rows=df.shape[0],
        columns=df.shape[1]
    )

    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    background_tasks.add_task(
        process_dataset_background,
        dataset.id,
        file_path
    )

    return {
        "dataset_id": dataset.id,
        "status": "processing"
    }


# --------------------------------------------------
# DATASET SUMMARY
# --------------------------------------------------
@app.get("/dataset-summary/{dataset_id}")
def get_dataset_summary(dataset_id: int, db: Session = Depends(get_db)):
    record = db.query(models.DatasetSummary).filter(
        models.DatasetSummary.dataset_id == dataset_id
    ).first()

    if not record:
        return {"status": "processing"}

    return {
        "dataset_id": dataset_id,
        "summary": record.summary
    }


# --------------------------------------------------
# RESULT NORMALIZATION (ROBUST)
# --------------------------------------------------
def normalize_result(result: Any):
    if result is None:
        return None

    if isinstance(result, pd.DataFrame):
        return result.replace({np.nan: None}).to_dict(orient="records")

    if isinstance(result, pd.Series):
        return result.replace({np.nan: None}).to_dict()

    if isinstance(result, (np.integer, np.floating)):
        return result.item()

    if isinstance(result, (np.bool_, bool)):
        return bool(result)

    if isinstance(result, (int, float, str)):
        return result

    if hasattr(result, "tolist"):
        return result.tolist()

    return str(result)


# --------------------------------------------------
# NL → PANDAS QUESTION ANSWERING
# --------------------------------------------------
@app.post("/ask")
def ask_question(payload: AskRequest, db: Session = Depends(get_db)):

    logger.info(f"Question received: {payload.question}")

    dataset = db.query(models.Dataset).filter(
        models.Dataset.id == payload.dataset_id
    ).first()

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    df = load_csv(dataset.file_path)
    schema = df.dtypes.astype(str).to_dict()

    try:
        plan = build_query_plan(payload.question, schema)
        pandas_code = generate_pandas_from_plan(plan)
        result = execute_pandas(df, pandas_code)

        validate_result_shape(result, plan.intent)

        if needs_correction(result, plan.intent):
            plan = apply_self_correction(plan)
            pandas_code = generate_pandas_from_plan(plan)
            result = execute_pandas(df, pandas_code)

        result_data = normalize_result(result)
        confidence = calculate_confidence(plan, result_data)
        explanation = generate_explanation(plan)

        chart = None
        try:
            chart = generate_chart(result)
        except Exception:
            logger.warning("Chart generation skipped (non-tabular result)")

        return {
            "question": payload.question,
            "query_plan": plan.to_dict(),
            "generated_pandas": pandas_code,
            "result": result_data,
            "confidence": confidence,
            "explanation": explanation,
            "chart": chart
        }

    except Exception as e:
        logger.exception("Question answering failed")
        raise HTTPException(status_code=500, detail=str(e))
