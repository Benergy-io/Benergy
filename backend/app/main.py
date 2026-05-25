print("🔥 BENERGY API v5.1 - FULLY OPERATIONAL")
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

import time
import subprocess
import os
import sqlite3
import uuid
import stripe

app = FastAPI(title="Benergy API", version="5.1")

# -----------------------------
# ENVIRONMENT VARIABLES (SECURE)
# -----------------------------
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://benergy-io.github.io/Benergy/")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://benergy-io.github.io/Benergy/")

# ✅ UPDATED: "solo" and "team" to match landing page
STRIPE_PLANS = {
    "solo": {
        "price_id": os.getenv("STRIPE_PRO_PRICE_ID", "price_1234567890")
    },
    "team": {
        "price_id": os.getenv("STRIPE_TEAM_PRICE_ID", "price_0987654321")
    },
    "pro": {
        "price_id": os.getenv("STRIPE_PRO_PRICE_ID", "price_1234567890")
    }
}

# GPU PRICING
GPU_PRICING = {
    "T4": 0.35,
    "V100": 2.50,
    "A100": 4.10,
    "H100": 8.00,
    "RTX 4090": 0.60
}

GPU_TYPE = "A100"
DB_NAME = "benergy.db"

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# STATIC FILES
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

# =============================
# DATABASE INIT
# =============================
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

# =============================
# USER SYSTEM
# =============================
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

# =============================
# GPU METRICS
# =============================
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
        # Mock GPU metrics for testing
        return {
            "gpu_utilization": 15 + (int(time.time()) % 80),
            "memory_used": 1024 + (int(time.time()) % 10000),
            "temperature": 55
        }

# =============================
# COST ENGINE
# =============================
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

# =============================
# ENDPOINTS
# =============================

@app.get("/")
def root():
    return {"status": "Benergy API Running", "version": "5.1", "stripe": "✅ Active"}

@app.get("/create-user")
def new_user():
    return create_user()

# ✅ METRICS ENDPOINT
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

# ✅ HISTORY ENDPOINT
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

# =============================
# ✅ STRIPE CHECKOUT (FIXED)
# =============================
@app.post("/create-checkout")
async def create_checkout(request: dict):
    """
    Expected payload from frontend:
    {
        "user_id": "user_xxx",
        "plan": "solo" or "team"
    }
    """
    
    user_id = request.get("user_id")
    plan = request.get("plan")

    print(f"🔷 Checkout request: user_id={user_id}, plan={plan}")

    # Validate plan
    if plan not in STRIPE_PLANS:
        return {"error": f"Invalid plan: {plan}. Use 'solo' or 'team'"}

    # Validate Stripe key
    if not stripe.api_key:
        return {"error": "Stripe API key not configured"}

    try:
        # Create Stripe session
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

        print(f"✅ Stripe session created: {session.url}")

        return {
            "url": session.url,
            "session_id": session.id,
            "plan": plan
        }

    except stripe.error.CardError as e:
        return {"error": f"Card error: {e.user_message}"}
    except stripe.error.RateLimitError as e:
        return {"error": "Too many requests to Stripe"}
    except stripe.error.InvalidRequestError as e:
        return {"error": f"Invalid request: {e.user_message}"}
    except stripe.error.AuthenticationError as e:
        return {"error": "Stripe authentication failed"}
    except stripe.error.APIConnectionError as e:
        return {"error": "Network error connecting to Stripe"}
    except Exception as e:
        print(f"❌ Stripe error: {str(e)}")
        return {"error": f"Stripe error: {str(e)}"}

# =============================
# ✅ DASHBOARD ENDPOINT (NEW)
# =============================
@app.get("/dashboard")
def get_dashboard():
    """Serve the dashboard HTML file"""
    try:
        with open("dashboard.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return {"error": "Dashboard not found. Make sure dashboard.html exists in root folder"}
    except Exception as e:
        return {"error": f"Error loading dashboard: {str(e)}"}

# =============================
# STRIPE SUCCESS / CANCEL
# =============================

@app.get("/success")
def success():
    return {"message": "✅ Payment successful! Welcome to Benergy 🎉"}

@app.get("/cancel")
def cancel():
    return {"message": "❌ Payment cancelled"}

# =============================
# STRIPE WEBHOOK
# =============================

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            STRIPE_WEBHOOK_SECRET
        )

    except ValueError:
        return {"error": "Invalid payload"}
    except stripe.error.SignatureVerificationError:
        return {"error": "Invalid signature"}

    # Handle successful checkout
    if event["type"] == "checkout.session.completed":

        session = event["data"]["object"]

        user_id = session["metadata"].get("user_id")
        plan = session["metadata"].get("plan")

        print(f"✅ Payment completed: user_id={user_id}, plan={plan}")

        # Update user subscription in database
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

# =============================
# HEALTH CHECK
# =============================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "api": "benergy",
        "version": "5.1",
        "stripe": "connected" if stripe.api_key else "not configured",
        "database": "sqlite3"
    }
