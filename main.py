
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    DateTime,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List
import subprocess
import os

# ================= CONFIG =================

DATABASE_URL = "sqlite:///./benergy.db"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

# ================= DATABASE =================

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

# ================= DATABASE MODELS =================


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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True)
    password_hash = Column(String)

    api_key = Column(String, unique=True, index=True)

    tier = Column(String, default="free")

    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)

# ================= PYDANTIC MODELS =================


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


class DashboardData(BaseModel):
    total_gpus: int
    avg_utilization: float
    idle_percentage: float
    peak_utilization: float
    memory_usage: float
    estimated_monthly_cost: float

    recommendations: List[str]

    gpu_metrics: List[GPUMetricRead]


# ================= DATABASE DEPENDENCY =================


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ================= GPU COLLECTION =================


def get_gpu_metrics():
    """
    Collect GPU metrics using nvidia-smi
    """

    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return []

        metrics = []

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue

            parts = [x.strip() for x in line.split(",")]

            metrics.append(
                {
                    "gpu_id": int(parts[0]),
                    "utilization": float(parts[1]),
                    "memory_used": float(parts[2]),
                    "memory_total": float(parts[3]),
                    "temperature": float(parts[4]),
                    "power_draw": float(parts[5]),
                }
            )

        return metrics

    except Exception as e:
        print(f"GPU metric collection failed: {e}")
        return []


def store_gpu_metrics(db: Session):
    metrics = get_gpu_metrics()

    for metric in metrics:
        db_metric = GPUMetric(
            gpu_id=metric["gpu_id"],
            timestamp=datetime.utcnow(),
            utilization=metric["utilization"],
            memory_used=metric["memory_used"],
            memory_total=metric["memory_total"],
            temperature=metric["temperature"],
            power_draw=metric["power_draw"],
        )

        db.add(db_metric)

    db.commit()


# ================= ANALYSIS =================


def calculate_recommendations(
    metrics: List[GPUMetricRead],
    avg_utilization: float,
):
    recommendations = []

    if avg_utilization < 30:
        recommendations.append(
            "GPUs are underutilized. Consider batching workloads."
        )

    elif avg_utilization > 90:
        recommendations.append(
            "GPU utilization is very high. Watch for bottlenecks."
        )

    recent_metrics = [
        m
        for m in metrics
        if (datetime.utcnow() - m.timestamp).total_seconds() < 3600
    ]

    if recent_metrics:
        max_util = max([m.utilization for m in recent_metrics])

        if max_util < 10:
            recommendations.append(
                "GPU appears idle for the last hour."
            )

    recommendations.append(
        "Schedule heavy workloads during cheaper off-peak hours."
    )

    return recommendations[:3]


def estimate_monthly_cost(metrics: List[GPUMetricRead]):
    if not metrics:
        return 0.0

    avg_utilization = (
        sum([m.utilization for m in metrics]) / len(metrics)
    )

    idle_percentage = (100 - avg_utilization) / 100

    num_gpus = len(set([m.gpu_id for m in metrics]))

    hours_per_month = 730
    cost_per_idle_hour = 0.25

    return (
        num_gpus
        * hours_per_month
        * idle_percentage
        * cost_per_idle_hour
    )


# ================= FASTAPI APP =================

app = FastAPI(
    title="Benergy GPU Monitoring API",
    version="1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= ROUTES =================


@app.get("/")
def root():
    return {
        "message": "Benergy GPU Monitoring API",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/collect-metrics")
def collect_metrics(db: Session = Depends(get_db)):
    store_gpu_metrics(db)

    return {"message": "Metrics collected successfully"}


@app.get("/dashboard", response_model=DashboardData)
def get_dashboard(
    hours: int = 24,
    db: Session = Depends(get_db),
):
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)

    metrics = (
        db.query(GPUMetric)
        .filter(GPUMetric.timestamp >= cutoff_time)
        .all()
    )

    if not metrics:
        return DashboardData(
            total_gpus=0,
            avg_utilization=0,
            idle_percentage=100,
            peak_utilization=0,
            memory_usage=0,
            estimated_monthly_cost=0,
            recommendations=[
                "No GPU data collected yet."
            ],
            gpu_metrics=[],
        )

    gpu_metrics_read = [
        GPUMetricRead.model_validate(m)
        for m in metrics
    ]

    utilizations = [m.utilization for m in gpu_metrics_read]

    avg_utilization = sum(utilizations) / len(utilizations)

    peak_utilization = max(utilizations)

    idle_percentage = 100 - avg_utilization

    memory_usage = (
        sum([m.memory_used for m in gpu_metrics_read])
        / len(gpu_metrics_read)
    )

    total_gpus = len(
        set([m.gpu_id for m in gpu_metrics_read])
    )

    estimated_cost = estimate_monthly_cost(
        gpu_metrics_read
    )

    recommendations = calculate_recommendations(
        gpu_metrics_read,
        avg_utilization,
    )

    return DashboardData(
        total_gpus=total_gpus,
        avg_utilization=round(avg_utilization, 2),
        idle_percentage=round(idle_percentage, 2),
        peak_utilization=round(peak_utilization, 2),
        memory_usage=round(memory_usage, 2),
        estimated_monthly_cost=round(estimated_cost, 2),
        recommendations=recommendations,
        gpu_metrics=gpu_metrics_read[-100:],
    )


@app.get("/metrics/gpu/{gpu_id}")
def get_single_gpu_metrics(
    gpu_id: int,
    hours: int = 24,
    db: Session = Depends(get_db),
):
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)

    metrics = (
        db.query(GPUMetric)
        .filter(
            GPUMetric.gpu_id == gpu_id,
            GPUMetric.timestamp >= cutoff_time,
        )
        .all()
    )

    return [
        GPUMetricRead.model_validate(m)
        for m in metrics
    ]


@app.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    cutoff_time = datetime.utcnow() - timedelta(hours=1)

    metrics = (
        db.query(GPUMetric)
        .filter(GPUMetric.timestamp >= cutoff_time)
        .all()
    )

    alerts = []

    if not metrics:
        return {"alerts": []}

    for metric in metrics:
        if metric.temperature > 80:
            alerts.append(
                {
                    "type": "high_temperature",
                    "gpu_id": metric.gpu_id,
                    "value": metric.temperature,
                    "severity": "warning",
                }
            )

    avg_utilization = (
        sum([m.utilization for m in metrics])
        / len(metrics)
    )

    if avg_utilization < 20:
        alerts.append(
            {
                "type": "underutilized",
                "avg_utilization": round(
                    avg_utilization,
                    2,
                ),
                "severity": "info",
            }
        )

    return {"alerts": alerts}


# ================= MAIN =================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )