print("🔥 WEBHOOK FILE ACTIVE")
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import time
import subprocess
import os
import sqlite3
import uuid
import stripe

app = FastAPI(title="Benergy API", version="5.0")

# -----------------------------
# ENVIRONMENT VARIABLES (SECURE)
# -----------------------------
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://your-frontend.com/success")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://your-frontend.com/cancel")

# -----------------------------
# STRIPE PLANS (PUT YOUR PRICE IDS HERE)
# -----------------------------
STRIPE_PLANS = {
    "pro": {
        "price_id": os.getenv("STRIPE_PRO_PRICE_ID")
    },
    "team": {
        "price_id": os.getenv("STRIPE_TEAM_PRICE_ID")
    }
}

# -----------------------------
# GPU PRICING MODEL
# -----------------------------
GPU_PRICING = {
    "T4": 0.35,
    "V100": 2.50,
    "A100": 4.10,
    "H100": 8.00,
    "RTX 4090": 0.60
}

GPU_TYPE = "A100"
DB_NAME = "benergy.db"

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# STATIC FILES
# -----------------------------
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

# -----------------------------
# DATABASE INIT
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

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

    c.execute("""
    CREATE TABLE IF NOT EXISTS usage (
        user_id TEXT,
        timestamp INTEGER,
        gpu_util INTEGER,
        memory_used INTEGER,
        temperature INTEGER,
        cost REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()

# -----------------------------
# USER SYSTEM
# -----------------------------
def create_user(email="user@example.com"):
    user_id = str(uuid.uuid4())
    api_key = str(uuid.uuid4())

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?)",
        (user_id, api_key, email, int(time.time()))
    )

    c.execute(
        "INSERT INTO subscriptions VALUES (?, 'free', ?)",
        (user_id, int(time.time()))
    )

    conn.commit()
    conn.close()

    return {
        "user_id": user_id,
        "api_key": api_key,
        "plan": "free"
    }

def get_user(api_key: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT user_id FROM users WHERE api_key = ?", (api_key,))
    row = c.fetchone()

    conn.close()
    return row[0] if row else None

def get_plan(user_id: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT plan FROM subscriptions WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    conn.close()
    return row[0] if row else "free"

# -----------------------------
# GPU METRICS
# -----------------------------
def get_gpu_metrics():
    try:
        query = (
            "nvidia-smi --query-gpu=utilization.gpu,"
            "memory.used,temperature.gpu --format=csv,noheader,nounits"
        )

        result = subprocess.check_output(query, shell=True).decode().strip()
        util, mem, temp = result.split(",")

        return {
            "gpu_utilization": int(util),
            "memory_used": int(mem),
            "temperature": int(temp)
        }

    except Exception:
        return {
            "gpu_utilization": 15,
            "memory_used": 1024,
            "temperature": 55
        }

# -----------------------------
# COST ENGINE
# -----------------------------
start_time = time.time()

def calculate_cost():
    hours = (time.time() - start_time) / 3600
    return round(hours * GPU_PRICING.get(GPU_TYPE, 1.0), 6)

def save_usage(user_id, gpu, cost):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    INSERT INTO usage VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        int(time.time()),
        gpu["gpu_utilization"],
        gpu["memory_used"],
        gpu["temperature"],
        cost
    ))

    conn.commit()
    conn.close()

# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return {"status": "Benergy API Running", "version": "5.0"}

# -----------------------------
# CREATE USER
# -----------------------------
@app.get("/create-user")
def new_user():
    return create_user()

# -----------------------------
# METRICS
# -----------------------------
@app.get("/metrics")
def metrics(x_api_key: str = Header(None)):

    user_id = get_user(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    plan = get_plan(user_id)

    gpu = get_gpu_metrics()
    cost = calculate_cost()

    save_usage(user_id, gpu, cost)

    return {
        "user_id": user_id,
        "plan": plan,
        "gpu_type": GPU_TYPE,
        "gpu_utilization": gpu["gpu_utilization"],
        "memory_used": gpu["memory_used"],
        "temperature": gpu["temperature"],
        "total_cost": cost
    }

# -----------------------------
# HISTORY
# -----------------------------
@app.get("/history")
def history(x_api_key: str = Header(None)):

    user_id = get_user(x_api_key)
    if not user_id:
        return {"error": "invalid api key"}

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT timestamp, gpu_util, cost
        FROM usage
        WHERE user_id = ?
        ORDER BY timestamp ASC
        LIMIT 200
    """, (user_id,))

    rows = c.fetchall()
    conn.close()

    return {
        "timestamps": [r[0] for r in rows],
        "gpu_utilization": [r[1] for r in rows],
        "cost": [r[2] for r in rows]
    }

# -----------------------------
# STRIPE CHECKOUT
# -----------------------------
@app.post("/create-checkout")
def create_checkout(user_id: str, plan: str):

    if plan not in STRIPE_PLANS:
        return {"error": "invalid plan"}

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{
            "price": STRIPE_PLANS[plan]["price_id"],
            "quantity": 1
        }],
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL,
        metadata={
            "user_id": user_id,
            "plan": plan
        }
    )

    return {"url": session.url}

# -----------------------------
# SECURE STRIPE WEBHOOK
# -----------------------------
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):

    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            STRIPE_WEBHOOK_SECRET
        )

    except Exception:
        return {"error": "invalid webhook"}

    if event["type"] == "checkout.session.completed":

        session = event["data"]["object"]

        user_id = session["metadata"]["user_id"]
        plan = session["metadata"]["plan"]

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("""
        UPDATE subscriptions
        SET plan = ?, updated_at = ?
        WHERE user_id = ?
        """, (plan, int(time.time()), user_id))

        conn.commit()
        conn.close()

    return {"status": "success"}