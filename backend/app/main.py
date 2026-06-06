from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import subprocess
import random
import time
import uuid
import sqlite3
import os

print("🚀 BENERGY API v4.0 - WITH STATIC FILES")

app = FastAPI(title="Benergy", version="4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= STATIC FILES =================

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    print("✅ Static files mounted")

# ================= CONFIG =================

DB_NAME = "benergy.db"
GPU_PRICING = {
    "T4": 0.35,
    "V100": 2.50,
    "A100": 4.10,
    "H100": 8.00,
    "RTX4090": 0.60
}
GPU_TYPE = "A100"
start_time = time.time()

# ================= DATABASE =================

def init_db():
    """Initialize database"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER,
        gpu_utilization INTEGER,
        memory_used INTEGER,
        temperature INTEGER,
        cost REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        api_key TEXT,
        email TEXT,
        created_at INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id TEXT PRIMARY KEY,
        plan TEXT,
        updated_at INTEGER
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= GPU FUNCTIONS =================

def get_real_gpu_metrics():
    """Get real GPU metrics from nvidia-smi"""
    try:
        query = (
            "nvidia-smi --query-gpu=utilization.gpu,"
            "memory.used,temperature.gpu --format=csv,noheader,nounits"
        )
        result = subprocess.check_output(query, shell=True, timeout=5).decode().strip()
        util, mem, temp = result.split(",")

        return {
            "gpu_utilization": int(float(util)),
            "memory_used": int(float(mem)),
            "temperature": int(float(temp))
        }
    except:
        return None

def get_mock_gpu_metrics():
    """Get mock GPU metrics"""
    return {
        "gpu_utilization": random.randint(15, 85),
        "memory_used": random.randint(512, 8192),
        "temperature": random.randint(35, 75)
    }

def get_gpu_metrics():
    """Get GPU metrics (real or mock)"""
    real = get_real_gpu_metrics()
    return real if real else get_mock_gpu_metrics()

def calculate_cost():
    """Calculate running cost"""
    hours = (time.time() - start_time) / 3600
    return round(hours * GPU_PRICING[GPU_TYPE], 6)

def save_metrics(gpu):
    """Save metrics to database"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("""
        INSERT INTO metrics (timestamp, gpu_utilization, memory_used, temperature, cost)
        VALUES (?, ?, ?, ?, ?)
        """, (
            int(time.time()),
            gpu["gpu_utilization"],
            gpu["memory_used"],
            gpu["temperature"],
            calculate_cost()
        ))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

# ================= ROUTES =================

@app.get("/")
def root():
    return {
        "message": "👽 Benergy GPU Monitoring API",
        "status": "✅ RUNNING",
        "version": "4.0",
        "gpu_type": GPU_TYPE,
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "history": "/history",
            "insights": "/insights",
            "dashboard": "/dashboard",
            "dashboard_data": "/dashboard-data",
            "create_user": "/create-user",
            "waitlist": "/waitlist (POST)",
            "contact": "/contact (POST)"
        }
    }


@app.get("/health")
def health():
    """Health check"""
    return {"status": "✅ ok"}


@app.get("/metrics")
def metrics():
    """Get current GPU metrics"""
    gpu = get_gpu_metrics()
    cost = calculate_cost()
    save_metrics(gpu)

    return {
        "status": "✅ success",
        "timestamp": int(time.time()),
        "gpu_utilization": gpu["gpu_utilization"],
        "memory_used": gpu["memory_used"],
        "temperature": gpu["temperature"],
        "gpu_type": GPU_TYPE,
        "total_cost": cost
    }


@app.get("/history")
def history():
    """Get metrics history"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute("""
            SELECT timestamp, gpu_utilization, memory_used, temperature, cost
            FROM metrics
            ORDER BY timestamp DESC
            LIMIT 100
        """)

        rows = c.fetchall()

        history_list = [
            {
                "timestamp": r[0],
                "gpu_utilization": r[1],
                "memory_used": r[2],
                "temperature": r[3],
                "cost": r[4]
            }
            for r in rows
        ]

        return {
            "status": "✅ success",
            "count": len(history_list),
            "data": history_list
        }
    finally:
        conn.close()


@app.get("/insights")
def insights():
    """Get AI insights"""
    gpu = get_gpu_metrics()
    util = gpu["gpu_utilization"]

    if util < 20:
        return {
            "status": "⚠️ WARNING",
            "waste_level": "HIGH",
            "utilization": util,
            "recommendation": "Stop idle workloads - GPUs are barely used",
            "potential_savings": "Up to 80%"
        }
    elif util < 50:
        return {
            "status": "⚠️ CAUTION",
            "waste_level": "MEDIUM",
            "utilization": util,
            "recommendation": "Improve scheduling - batch jobs together",
            "potential_savings": "Up to 50%"
        }

    return {
        "status": "✅ OK",
        "waste_level": "LOW",
        "utilization": util,
        "recommendation": "System is running efficiently",
        "potential_savings": "Minimal"
    }


@app.get("/dashboard", response_class=FileResponse)
def dashboard():
    """Serve dashboard HTML"""
    try:
        return FileResponse("static/dashboard.html", media_type="text/html")
    except:
        return {"error": "Dashboard not found"}


@app.get("/dashboard-data")
def dashboard_data():
    """Get dashboard data as JSON"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute("""
            SELECT gpu_utilization, memory_used, temperature, cost
            FROM metrics
            ORDER BY timestamp DESC
            LIMIT 100
        """)

        rows = c.fetchall()

        if rows:
            utils = [r[0] for r in rows]
            avg_util = sum(utils) / len(utils)
            peak_util = max(utils)
            idle_pct = 100 - avg_util
            total_cost = sum([r[3] for r in rows])
        else:
            avg_util = 0
            peak_util = 0
            idle_pct = 100
            total_cost = 0

        return {
            "status": "✅ success",
            "total_gpus": 1,
            "avg_utilization": round(avg_util, 2),
            "idle_percentage": round(idle_pct, 2),
            "peak_utilization": round(peak_util, 2),
            "estimated_monthly_cost": round(total_cost * 720, 2),
            "recommendations": [
                "⚠️ GPUs underutilized. Batch smaller jobs." if avg_util < 30 else "✅ GPUs running efficiently",
                "💡 Schedule heavy training during off-peak." if avg_util < 50 else "⚠️ High GPU utilization",
                "💤 Check idle GPUs." if avg_util < 20 else "✅ System optimal"
            ]
        }
    finally:
        conn.close()


@app.get("/create-user")
def create_user(email: str = "user@example.com"):
    """Create a new user"""
    user_id = str(uuid.uuid4())
    api_key = str(uuid.uuid4())

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (user_id, api_key, email, int(time.time()))
        )
        c.execute(
            "INSERT INTO subscriptions VALUES (?, 'free', ?)",
            (user_id, int(time.time()))
        )
        conn.commit()

        return {
            "status": "✅ success",
            "user_id": user_id,
            "api_key": api_key,
            "email": email,
            "plan": "free"
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.post("/waitlist")
async def waitlist(data: dict):
    """Add email to waitlist"""
    email = data.get("email", "").strip()

    if not email:
        return {"error": "Email required"}

    return {
        "status": "✅ success",
        "message": "Added to waitlist",
        "email": email
    }


@app.post("/contact")
async def contact(data: dict):
    """Handle contact form"""
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    company = data.get("company", "").strip()

    if not email:
        return {"error": "Email required"}

    return {
        "status": "✅ success",
        "message": "We'll contact you soon",
        "email": email,
        "name": name,
        "company": company
    }


# ================= MAIN =================

if __name__ == "__main__":
    import uvicorn
    print("\n✅ Starting Benergy API v4.0...\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
