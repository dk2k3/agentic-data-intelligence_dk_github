from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from .db import Base

class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    file_path = Column(String)          # 👈 NEW
    rows = Column(Integer)
    columns = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)




class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Insight(Base):
    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer)
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class DatasetSummary(Base):
    __tablename__ = "dataset_summaries"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer)
    summary = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserQuery(Base):
    __tablename__ = "user_queries"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer)
    question = Column(String)
    generated_sql = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
