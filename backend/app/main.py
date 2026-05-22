from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import random
import time
import os

app = FastAPI(title="Benergy API", version="1.0")

# -----------------------------
# CORS (FRONTEND ACCESS)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# STATIC FILES (optional assets)
# -----------------------------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")


# -----------------------------
# GPU PRICING MAP
# -----------------------------
GPU_PRICING = {
    "T4": 0.35,
    "V100": 2.50,
    "A100": 4.10,
    "H100": 8.00,
    "RTX 4090": 0.60
}

GPU_TYPE = "A100"


# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return {
        "status": "Benergy API Running",
        "version": "1.0"
    }


# -----------------------------
# METRICS
# -----------------------------
@app.get("/metrics")
def metrics():

    gpu_util = random.randint(5, 95)
    memory_used = random.randint(2000, 24000)
    temperature = random.randint(45, 85)

    gpu_hourly_cost = GPU_PRICING.get(GPU_TYPE, 1.0)

    return {
        "timestamp": int(time.time()),
        "gpu_type": GPU_TYPE,
        "gpu_utilization": gpu_util,
        "memory_used": memory_used,
        "temperature": temperature,
        "gpu_hourly_cost": gpu_hourly_cost
    }


# -----------------------------
# HISTORY
# -----------------------------
@app.get("/history")
def history():

    return [
        {
            "gpu_utilization": random.randint(10, 95),
            "time": int(time.time()) - (30 - i) * 5
        }
        for i in range(30)
    ]


# -----------------------------
# INSIGHTS / ALERT ENGINE
# -----------------------------
@app.get("/insights")
def insights():

    gpu_util = random.randint(5, 95)

    alerts = []
    recommendation = "System operating normally"

    if gpu_util < 20:
        alerts.append("⚠ GPU severely underutilized")
        recommendation = "Stop idle workloads or batch jobs"

    elif gpu_util < 50:
        alerts.append("⚠ Moderate GPU underutilization")
        recommendation = "Improve scheduling efficiency"

    else:
        alerts.append("🟢 GPU usage healthy")
        recommendation = "No optimization needed"

    return {
        "status": "OK" if gpu_util > 30 else "WARNING",
        "gpu_utilization": gpu_util,
        "alerts": alerts,
        "recommendation": recommendation
    }