from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List
import os

DATABASE_URL = "sqlite:///./benergy.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


class GPUMetric(Base):
    __tablename__ = "gpu_metrics"

    id = Column(Integer, primary_key=True, index=True)
    gpu_id = Column(Integer, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    utilization = Column(Float)
    memory_used = Column(Float)
    memory_total = Column(Float)
    temperature = Column(Float)
    power_draw = Column(Float)


Base.metadata.create_all(bind=engine)


class GPUMetricRead(BaseModel):
    gpu_id: int
    timestamp: datetime
    utilization: float
    memory_used: float
    memory_total: float
    temperature: float
    power_draw: float

    class Config:
        from_attributes = True


app = FastAPI(title="Benergy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {"message": "Benergy backend running"}


@app.get("/health")
def health():
    return {"status": "ok"}
