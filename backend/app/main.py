from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import random
import shutil
import subprocess

from app.database import init_db, DB_PATH

app = FastAPI(title="Benergy API")

# -----------------------------
# CORS (frontend ready)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# INIT DB
# -----------------------------
init_db()


# -----------------------------
# GPU DETECTOR
# -----------------------------
def has_nvidia_gpu():
    return shutil.which("nvidia-smi") is not None


# -----------------------------
# ROOT / HEALTH / TEST
# -----------------------------
@app.get("/")
def root():
    return {"message": "Benergy backend running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/test")
def test():
    return {"status": "backend is alive"}


# -----------------------------
# METRICS (REAL + FALLBACK)
# -----------------------------
@app.get("/metrics")
def metrics():

    if has_nvidia_gpu():
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,temperature.gpu",
                    "--format=csv,noheader,nounits"
                ],
                capture_output=True,
                text=True
            )

            gpu_util, mem_used, temp = result.stdout.strip().split(",")

            gpu_util = int(gpu_util)
            mem_used = int(mem_used)
            temp = int(temp)

            mode = "real_gpu"

        except Exception:
            gpu_util = 0
            mem_used = 0
            temp = 0
            mode = "gpu_error_fallback"

    else:
        gpu_util = random.randint(10, 95)
        mem_used = random.randint(1000, 8000)
        temp = random.randint(40, 85)
        mode = "simulated"

    # Save to DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO metrics (gpu_util, memory_used, temperature)
        VALUES (?, ?, ?)
    """, (gpu_util, mem_used, temp))

    conn.commit()
    conn.close()

    return {
        "gpu_utilization": gpu_util,
        "memory_used": mem_used,
        "temperature": temp,
        "mode": mode
    }


# -----------------------------
# HISTORY
# -----------------------------
@app.get("/history")
def history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT gpu_util, memory_used, temperature, timestamp
        FROM metrics
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()
    conn.close()

    return {
        "data": [
            {
                "gpu_util": r[0],
                "memory_used": r[1],
                "temperature": r[2],
                "timestamp": r[3]
            }
            for r in rows
        ]
    }


# -----------------------------
# INSIGHTS (INTELLIGENCE LAYER)
# -----------------------------
@app.get("/insights")
def insights():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT gpu_util
        FROM metrics
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {"message": "No data yet"}

    values = [r[0] for r in rows]
    avg = sum(values) / len(values)

    waste = 100 - avg

    gpu_cost_per_hour = 3
    waste_cost = (waste / 100) * gpu_cost_per_hour

    if avg < 30:
        status = "CRITICAL underutilization"
        recommendation = "Shutdown idle GPU or consolidate workloads"
    elif avg < 60:
        status = "Moderate utilization"
        recommendation = "Optimize workload distribution"
    else:
        status = "Healthy utilization"
        recommendation = "No action needed"

    return {
        "average_gpu_utilization": round(avg, 2),
        "waste_estimate_percent": round(waste, 2),
        "estimated_waste_cost_per_hour_usd": round(waste_cost, 2),
        "status": status,
        "recommendation": recommendation
    }