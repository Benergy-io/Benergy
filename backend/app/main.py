from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
import sqlite3
import os
import time
import uuid
import stripe
import subprocess
import random

print("🚀 BENERGY CLEAN API STARTING...")

app = FastAPI(title="Benergy API", version="4.1")

# ================= SECURITY / CONFIG =================

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # DO NOT hardcode

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://benergy-io.github.io/")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://benergy-io.github.io/")

STRIPE_PLANS = {
    "solo": os.getenv("STRIPE_SOLO_PRICE_ID"),
    "team": os.getenv("STRIPE_TEAM_PRICE_ID"),
}

DB_NAME = "benergy.db"

GPU_TYPE = "A100"

PLAN_LIMITS = {
    "free": 20,
    "solo": 100,
    "team": 10000
}

# ================= CORS =================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= DB INIT =================

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
        user_id TEXT,
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

# ================= HELPERS =================

def create_user(email: str):
    user_id = str(uuid.uuid4())
    api_key = str(uuid.uuid4())

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("INSERT INTO users VALUES (?, ?, ?, ?)",
              (user_id, api_key, email, int(time.time())))

    c.execute("INSERT INTO subscriptions VALUES (?, ?, ?)",
              (user_id, "free", int(time.time())))

    conn.commit()
    conn.close()

    return {
        "user_id": user_id,
        "api_key": api_key,
        "email": email,
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


# ================= GPU MOCK =================

def get_gpu_metrics():
    return {
        "gpu_utilization": random.randint(20, 90),
        "memory_used": random.randint(1000, 9000),
        "temperature": random.randint(40, 80)
    }


def calc_cost():
    return round(time.time() % 100 / 10, 4)


# ================= ROUTES =================

@app.get("/")
def root():
    return {
        "status": "running",
        "version": "4.1",
        "endpoints": ["/dashboard", "/metrics", "/create-user"]
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/create-user")
def new_user(email: str = "user@example.com"):
    return create_user(email)


@app.get("/metrics")
def metrics(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(401, "Missing API key")

    user_id = get_user(x_api_key)
    if not user_id:
        raise HTTPException(401, "Invalid API key")

    plan = get_plan(user_id)

    gpu = get_gpu_metrics()

    return {
        "user_id": user_id,
        "plan": plan,
        "gpu_utilization": gpu["gpu_utilization"],
        "memory_used": gpu["memory_used"],
        "temperature": gpu["temperature"],
        "total_cost": calc_cost()
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return FileResponse("static/dashboard.html")


@app.get("/success")
def success():
    return RedirectResponse(STRIPE_SUCCESS_URL)


@app.get("/cancel")
def cancel():
    return RedirectResponse(STRIPE_CANCEL_URL)


@app.post("/create-checkout")
async def create_checkout(data: dict):
    plan = data.get("plan")

    if not stripe.api_key:
        return {"error": "Stripe not configured"}

    price_id = STRIPE_PLANS.get(plan)

    if not price_id:
        return {"error": "Invalid plan"}

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=STRIPE_SUCCESS_URL,
        cancel_url=STRIPE_CANCEL_URL
    )

    return {"url": session.url}
    

@app.post("/waitlist")
async def waitlist(data: dict):
    email = data.get("email")

    if not email:
        return {"error": "Email required"}

    print("WAITLIST:", email)

    return {"status": "ok", "email": email}


# ================= MAIN =================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
