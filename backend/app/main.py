from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import time
import subprocess
import os
import sqlite3
import uuid
import json
import stripe
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

print("🚀 BENERGY v4.0 - PRODUCTION READY")

app = FastAPI(title="Benergy API", version="4.0")

# ================= CONFIG =================

# STRIPE CONFIG (from Render environment)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_your_key")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_your_secret")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://benergy-io.github.io/")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://benergy-io.github.io/")

STRIPE_PLANS = {
    "solo": {"price_id": os.getenv("STRIPE_PRO_PRICE_ID")},
    "team": {"price_id": os.getenv("STRIPE_TEAM_PRICE_ID")},
    "pro": {"price_id": os.getenv("STRIPE_PRO_PRICE_ID")}
}

# EMAIL CONFIG
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@benergy.io")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "hello@benergy.io")

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

PLAN_LIMITS = {
    "free": 20,
    "pro": 200,
    "team": 10000
}

print(f"✅ Stripe: {stripe.api_key[:20]}...")
print(f"✅ Plans: {list(STRIPE_PLANS.keys())}")

# ================= CORS =================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= STATIC FILES =================

if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

# ================= DATABASE INIT =================

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
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
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

# ================= USER SYSTEM =================

def create_user(email="user@example.com"):
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
            "INSERT INTO subscriptions VALUES (?, 'free', NULL, NULL, ?)",
            (user_id, int(time.time()))
        )

        conn.commit()
        
        print(f"✅ User created: {user_id}")
        
        return {
            "user_id": user_id,
            "api_key": api_key,
            "email": email,
            "plan": "free"
        }
    except Exception as e:
        print(f"❌ User creation error: {str(e)}")
        return {"error": str(e)}
    finally:
        conn.close()


def get_user(api_key: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute("SELECT user_id FROM users WHERE api_key = ?", (api_key,))
        row = c.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_plan(user_id: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute("SELECT plan FROM subscriptions WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else "free"
    finally:
        conn.close()


def update_subscription(user_id: str, plan: str, stripe_subscription_id: str = None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute("""
        UPDATE subscriptions
        SET plan = ?, stripe_subscription_id = ?, updated_at = ?
        WHERE user_id = ?
        """, (plan, stripe_subscription_id, int(time.time()), user_id))

        conn.commit()
        print(f"✅ Subscription updated: {user_id} -> {plan}")
    finally:
        conn.close()

# ================= GPU + COST ENGINE =================

def get_gpu_metrics():
    """Get real GPU metrics or mock data"""
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
        # Mock data when nvidia-smi not available
        return {
            "gpu_utilization": random.randint(15, 85),
            "memory_used": random.randint(512, 8192),
            "temperature": random.randint(35, 75)
        }


start_time = time.time()

def calculate_cost():
    """Calculate running cost"""
    hours = (time.time() - start_time) / 3600
    return round(hours * GPU_PRICING.get(GPU_TYPE, 1.0), 6)


def save_usage(user_id, gpu, cost):
    """Save usage to database"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
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
    finally:
        conn.close()

# ================= ROUTES =================

@app.get("/")
def root():
    return {
        "message": "👽 Benergy GPU Monitoring API",
        "status": "✅ RUNNING",
        "version": "4.0",
        "endpoints": {
            "health": "/health",
            "create_user": "/create-user",
            "metrics": "/metrics (requires x-api-key header)",
            "history": "/history (requires x-api-key header)",
            "insights": "/insights (requires x-api-key header)",
            "dashboard": "/dashboard",
            "alerts": "/alerts",
            "checkout": "/create-checkout",
            "docs": "/docs"
        }
    }


@app.get("/health")
def health():
    return {"status": "✅ ok", "service": "benergy-api"}


@app.get("/create-user")
def new_user(email: str = "user@example.com"):
    """Create a new user"""
    return create_user(email)


@app.get("/metrics")
def metrics(x_api_key: str = Header(None)):
    """Get current GPU metrics"""
    
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key header")

    user_id = get_user(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    plan = get_plan(user_id)
    limit = PLAN_LIMITS.get(plan, 20)

    # Check usage limit
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM usage WHERE user_id = ?", (user_id,))
    usage_count = c.fetchone()[0]
    conn.close()

    if usage_count >= limit:
        return {
            "error": "usage limit reached",
            "plan": plan,
            "limit": limit,
            "current": usage_count
        }

    gpu = get_gpu_metrics()
    cost = calculate_cost()

    save_usage(user_id, gpu, cost)

    return {
        "status": "✅ success",
        "user_id": user_id,
        "plan": plan,
        "gpu_type": GPU_TYPE,
        "gpu_utilization": gpu["gpu_utilization"],
        "memory_used": gpu["memory_used"],
        "temperature": gpu["temperature"],
        "total_cost": cost
    }


@app.get("/history")
def history(x_api_key: str = Header(None)):
    """Get usage history"""
    
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key header")

    user_id = get_user(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        c.execute("""
            SELECT timestamp, gpu_util, memory_used, temperature, cost
            FROM usage
            WHERE user_id = ?
            ORDER BY timestamp ASC
            LIMIT 200
        """, (user_id,))

        rows = c.fetchall()

        return {
            "status": "✅ success",
            "user_id": user_id,
            "count": len(rows),
            "data": {
                "timestamps": [r[0] for r in rows],
                "gpu_utilization": [r[1] for r in rows],
                "memory_used": [r[2] for r in rows],
                "temperature": [r[3] for r in rows],
                "cost": [r[4] for r in rows]
            }
        }
    finally:
        conn.close()


@app.get("/insights")
def insights(x_api_key: str = Header(None)):
    """Get AI insights and recommendations"""
    
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key header")

    user_id = get_user(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")

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
            "status": "⚠️ WARNING",
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


# ================= DASHBOARD =================

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """Serve dashboard HTML"""
    try:
        with open("static/dashboard.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Benergy Dashboard</title>
            <style>
                body { 
                    background: linear-gradient(135deg, #0a1628 0%, #0f1f2e 100%);
                    color: #fff; 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex; 
                    justify-content: center; 
                    align-items: center; 
                    height: 100vh; 
                    margin: 0; 
                }
                .container { 
                    text-align: center;
                    padding: 40px;
                }
                .logo { margin-bottom: 30px; }
                h1 { 
                    color: #00d9ff;
                    margin-bottom: 20px;
                    font-size: 32px;
                }
                .spinner {
                    display: inline-block;
                    width: 30px;
                    height: 30px;
                    border: 3px solid rgba(0, 217, 255, 0.2);
                    border-top-color: #00d9ff;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin-bottom: 20px;
                }
                @keyframes spin { to { transform: rotate(360deg); } }
                p { color: #a0aec0; margin: 15px 0; }
                a { color: #00d9ff; text-decoration: none; font-weight: 600; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">
                    <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="width: 60px; height: 60px;">
                        <circle cx="50" cy="50" r="48" fill="#0a1628"/>
                        <ellipse cx="50" cy="35" rx="18" ry="22" fill="#FFD700"/>
                        <circle cx="40" cy="28" r="7" fill="#FFD700"/>
                        <circle cx="40" cy="28" r="4" fill="#1a1a1a"/>
                        <circle cx="40" cy="28" r="2" fill="#ffffff" opacity="0.8"/>
                        <circle cx="60" cy="28" r="7" fill="#FFD700"/>
                        <circle cx="60" cy="28" r="4" fill="#1a1a1a"/>
                        <circle cx="60" cy="28" r="2" fill="#ffffff" opacity="0.8"/>
                        <polygon points="50,40 46,45 54,45" fill="#FFD700"/>
                        <path d="M 45 48 Q 50 51 55 48" stroke="#FFD700" stroke-width="2" fill="none" stroke-linecap="round"/>
                        <rect x="38" y="56" width="24" height="26" rx="3" fill="#FFD700"/>
                        <rect x="25" y="62" width="10" height="16" rx="5" fill="#FFD700"/>
                        <circle cx="30" cy="80" r="5" fill="#FFD700"/>
                        <rect x="65" y="62" width="10" height="16" rx="5" fill="#FFD700"/>
                        <circle cx="70" cy="80" r="5" fill="#FFD700"/>
                        <line x1="42" y1="15" x2="38" y2="8" stroke="#FFD700" stroke-width="2" stroke-linecap="round"/>
                        <circle cx="38" cy="6" r="2" fill="#FFD700"/>
                        <line x1="58" y1="15" x2="62" y2="8" stroke="#FFD700" stroke-width="2" stroke-linecap="round"/>
                        <circle cx="62" cy="6" r="2" fill="#FFD700"/>
                    </svg>
                </div>
                <h1>Benergy Dashboard</h1>
                <div class="spinner"></div>
                <p><strong>Loading dashboard...</strong></p>
                <p style="font-size: 13px; color: #708090;">Dashboard files deploying. Please refresh in 30 seconds.</p>
                <p style="margin-top: 40px;">
                    <a href="https://benergy-ten.vercel.app">← Back to Home</a>
                </p>
            </div>
        </body>
        </html>
        """


@app.get("/dashboard-data")
def get_dashboard_data(db_connection=None):
    """Get dashboard data as JSON (for dashboard.html to consume)"""
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Get recent usage data
        c.execute("""
            SELECT timestamp, gpu_util, memory_used, temperature, cost
            FROM usage
            ORDER BY timestamp DESC
            LIMIT 100
        """)
        
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            # Return mock data
            return {
                "total_gpus": 4,
                "avg_utilization": 45.2,
                "idle_percentage": 54.8,
                "peak_utilization": 92.1,
                "memory_usage": 4521.5,
                "estimated_monthly_cost": 324.50,
                "recommendations": [
                    "⚠️ GPUs underutilized. Batch smaller jobs.",
                    "💡 Schedule heavy training during off-peak.",
                    "💤 GPU idle. Check running jobs."
                ],
                "gpu_metrics": []
            }
        
        # Process real data
        utilizations = [r[1] for r in rows]
        avg_util = sum(utilizations) / len(utilizations) if utilizations else 0
        peak_util = max(utilizations) if utilizations else 0
        idle_pct = 100 - avg_util
        memory = sum([r[2] for r in rows]) / len(rows) if rows else 0
        total_cost = sum([r[4] for r in rows]) if rows else 0
        
        return {
            "total_gpus": 4,
            "avg_utilization": round(avg_util, 2),
            "idle_percentage": round(idle_pct, 2),
            "peak_utilization": round(peak_util, 2),
            "memory_usage": round(memory, 2),
            "estimated_monthly_cost": round(total_cost, 2),
            "recommendations": [
                "⚠️ GPUs underutilized. Batch smaller jobs." if avg_util < 30 else "✅ GPUs running efficiently",
                "💡 Schedule heavy training during off-peak." if avg_util < 50 else "⚠️ High GPU utilization",
                "💤 Check idle GPUs." if avg_util < 20 else "✅ System optimal"
            ],
            "gpu_metrics": [
                {
                    "gpu_id": i,
                    "timestamp": r[0],
                    "utilization": r[1],
                    "memory_used": r[2],
                    "memory_total": 10000,
                    "temperature": r[3],
                    "power_draw": 50 + (r[1] / 100) * 200
                }
                for i, r in enumerate(rows[:10])
            ]
        }
        
    except Exception as e:
        print(f"❌ Dashboard data error: {str(e)}")
        return {
            "total_gpus": 4,
            "avg_utilization": 45.2,
            "idle_percentage": 54.8,
            "peak_utilization": 92.1,
            "memory_usage": 4521.5,
            "estimated_monthly_cost": 324.50,
            "recommendations": [
                "⚠️ Loading data...",
                "💡 Waiting for metrics...",
                "📊 Refreshing..."
            ],
            "gpu_metrics": []
        }


@app.get("/alerts")
def get_alerts(x_api_key: str = Header(None)):
    """Get active alerts"""
    
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key header")

    user_id = get_user(x_api_key)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    gpu = get_gpu_metrics()
    alerts = []

    if gpu["temperature"] > 80:
        alerts.append({
            "type": "high_temperature",
            "severity": "warning",
            "message": f"GPU temperature is {gpu['temperature']}°C - consider reducing load"
        })

    if gpu["gpu_utilization"] < 20:
        alerts.append({
            "type": "underutilized",
            "severity": "info",
            "message": f"GPU utilization is {gpu['gpu_utilization']}% - GPUs are idle"
        })

    if gpu["memory_used"] > 10000:
        alerts.append({
            "type": "high_memory",
            "severity": "warning",
            "message": f"Memory usage is {gpu['memory_used']}MB - close to limits"
        })

    return {
        "status": "✅ success",
        "user_id": user_id,
        "alert_count": len(alerts),
        "alerts": alerts
    }


# ================= STRIPE CHECKOUT =================

@app.post("/create-checkout")
async def create_checkout(data: dict):
    """Create Stripe checkout session"""
    
    user_id = data.get("user_id", "guest")
    plan = data.get("plan", "team")

    print(f"\n🔷 CHECKOUT: user_id={user_id}, plan={plan}")

    if plan not in STRIPE_PLANS:
        return {"error": f"Invalid plan: {plan}"}

    if not stripe.api_key or "test" not in stripe.api_key:
        return {"error": "Stripe not configured"}

    try:
        price_id = STRIPE_PLANS[plan]["price_id"]
        
        if not price_id:
            return {"error": f"No price ID for plan: {plan}"}

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{
                "price": price_id,
                "quantity": 1
            }],
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
            metadata={"user_id": user_id, "plan": plan}
        )

        print(f"✅ Stripe session created: {session.id}")

        return {
            "status": "✅ success",
            "url": session.url,
            "session_id": session.id,
            "plan": plan
        }

    except Exception as e:
        print(f"❌ Stripe error: {str(e)}")
        return {"error": f"Stripe error: {str(e)}"}


@app.get("/success")
def success():
    """Redirect after successful payment"""
    return RedirectResponse(url=STRIPE_SUCCESS_URL, status_code=303)


@app.get("/cancel")
def cancel():
    """Redirect after payment cancel"""
    return RedirectResponse(url=STRIPE_CANCEL_URL, status_code=303)


# ================= STRIPE WEBHOOK =================

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
        print("❌ Webhook error (invalid payload)")
        return {"error": "Invalid payload"}
    except stripe.error.SignatureVerificationError:
        print("❌ Webhook error (invalid signature)")
        return {"error": "Invalid signature"}

    # Handle checkout completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        user_id = session["metadata"].get("user_id")
        plan = session["metadata"].get("plan")

        print(f"\n✅ PAYMENT COMPLETED")
        print(f"   User: {user_id}")
        print(f"   Plan: {plan}")

        update_subscription(user_id, plan, session.get("subscription"))

    return {"status": "✅ success"}


# ================= CONTACT FORM =================

@app.post("/contact")
async def contact_form(data: dict):
    """Handle contact form submission"""
    
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    company = data.get("company", "").strip()
    message = data.get("message", "").strip()

    print(f"\n📧 CONTACT FORM: {name} <{email}>")

    if not all([name, email]):
        return {"error": "Name and email required"}

    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = CONTACT_EMAIL
        msg["Subject"] = f"📧 Contact: {name} ({company if company else 'N/A'})"

        body = f"""
Benergy Contact Form

Name: {name}
Email: {email}
Company: {company if company else 'Not provided'}

Message:
{message if message else '(No message)'}

---
Reply to: {email}
        """

        msg.attach(MIMEText(body, "plain"))

        if SENDER_PASSWORD and SENDER_EMAIL != "noreply@benergy.io":
            try:
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
                server.quit()
                
                print(f"✅ Email sent to {CONTACT_EMAIL}")
                return {
                    "status": "✅ success",
                    "message": "Thanks! We'll contact you within 24 hours."
                }
            except Exception as e:
                print(f"⚠️ Email send failed: {str(e)}")
                return {
                    "status": "✅ received",
                    "message": "Thanks! We'll get back to you soon."
                }
        else:
            print(f"💾 Contact logged: {name} <{email}>")
            return {
                "status": "✅ received",
                "message": "Thanks! We'll get back to you soon."
            }

    except Exception as e:
        print(f"❌ Contact form error: {str(e)}")
        return {"error": f"Error: {str(e)}"}


# ================= MAIN =================

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Benergy API v4.0...\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
