from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import subprocess
import random
import time
import uuid
import sqlite3
import os
from pydantic import BaseModel

print("🚀 BENERGY API v4.1 - WITH AGENT SUPPORT")

app = FastAPI(title="Benergy", version="4.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= STATIC FILES =================

static_path = "app/static"
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    print(f"✅ Static files mounted from {static_path}")
else:
    print(f"⚠️ Static folder not found at {static_path}")

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

# ================= PYDANTIC MODELS =================

class MetricsInput(BaseModel):
    """Metrics from agent"""
    api_key: str
    gpu_utilization: int
    memory_used: int
    temperature: int


# ================= DATABASE =================

def init_db():
    """Initialize database"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
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
        api_key TEXT UNIQUE,
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

# ================= AUTH FUNCTIONS =================

def validate_api_key(api_key: str):
    """
    Validate API key and return user_id
    Returns user_id if valid, None if invalid
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    try:
        c.execute("SELECT user_id FROM users WHERE api_key = ?", (api_key,))
        row = c.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


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

def save_metrics(user_id: str, gpu):
    """Save metrics to database"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("""
        INSERT INTO metrics (user_id, timestamp, gpu_utilization, memory_used, temperature, cost)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            int(time.time()),
            gpu["gpu_utilization"],
            gpu["memory_used"],
            gpu["temperature"],
            calculate_cost()
        ))
        conn.commit()
    except Exception as e:
        print(f"Error saving metrics: {e}")
    finally:
        conn.close()

# ================= ROUTES =================

@app.get("/")
def root():
    return {
        "message": "👽 Benergy GPU Monitoring API",
        "status": "✅ RUNNING",
        "version": "4.1",
        "gpu_type": GPU_TYPE,
        "features": [
            "Real-time GPU monitoring",
            "Agent integration",
            "API key authentication",
            "Historical metrics"
        ]
    }


@app.get("/health")
def health():
    """Health check"""
    return {"status": "✅ ok"}


@app.post("/metrics")
async def post_metrics(data: MetricsInput):
    """
    Accept metrics from agent
    Agent sends: api_key, gpu_utilization, memory_used, temperature
    """
    api_key = data.api_key
    
    # Validate API key
    user_id = validate_api_key(api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Store metrics
    metrics = {
        "gpu_utilization": data.gpu_utilization,
        "memory_used": data.memory_used,
        "temperature": data.temperature
    }
    
    save_metrics(user_id, metrics)
    
    return {
        "status": "✅ success",
        "message": "Metrics received",
        "timestamp": int(time.time()),
        "data": metrics
    }


@app.get("/metrics")
def get_metrics():
    """Get current GPU metrics (for testing without agent)"""
    gpu = get_gpu_metrics()
    cost = calculate_cost()

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
def history(api_key: str = None):
    """
    Get metrics history
    If api_key provided, return only that user's data
    Otherwise return demo data
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        if api_key:
            # Validate API key
            user_id = validate_api_key(api_key)
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid API key")
            
            # Get user's metrics
            c.execute("""
                SELECT timestamp, gpu_utilization, memory_used, temperature, cost
                FROM metrics
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 100
            """, (user_id,))
        else:
            # Get all metrics for demo
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
def insights(api_key: str = None):
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
    dashboard_path = "app/static/dashboard.html"
    try:
        if not os.path.exists(dashboard_path):
            return {"error": f"Dashboard not found at {dashboard_path}"}
        return FileResponse(dashboard_path, media_type="text/html")
    except Exception as e:
        print(f"❌ Dashboard error: {str(e)}")
        return {"error": f"Failed to load dashboard: {str(e)}"}


@app.get("/dashboard-data")
def dashboard_data(api_key: str = None):
    """Get dashboard data as JSON"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        if api_key:
            # Validate API key
            user_id = validate_api_key(api_key)
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid API key")
            
            # Get user's metrics
            c.execute("""
                SELECT gpu_utilization, memory_used, temperature, cost
                FROM metrics
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 100
            """, (user_id,))
        else:
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
                "✅ GPUs running efficiently" if avg_util >= 50 else "⚠️ GPUs underutilized. Batch smaller jobs.",
                "💡 Schedule heavy training during off-peak." if avg_util < 50 else "⚠️ High GPU utilization",
                "✅ System optimal" if avg_util >= 30 else "💤 Check idle GPUs."
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
            "plan": "free",
            "message": "Use this API key with benergy-agent"
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
    print("\n✅ Starting Benergy API v4.1 with Agent Support...\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
