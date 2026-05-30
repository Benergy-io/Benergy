import os
import uuid
import stripe
import smtplib
import random
from datetime import datetime, timedelta
from typing import List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel

print("🔥 BENERGY v2.0 - PRODUCTION BACKEND")

# ================= CONFIG =================

DATABASE_URL = "sqlite:///./benergy.db"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

# STRIPE CONFIG
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "https://benergy-io.github.io/")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "https://benergy-io.github.io/")

STRIPE_PLANS = {
    "solo": {"price_id": os.getenv("STRIPE_PRO_PRICE_ID")},
    "team": {"price_id": os.getenv("STRIPE_TEAM_PRICE_ID")},
    "pro": {"price_id": os.getenv("STRIPE_PRO_PRICE_ID")},
}

# EMAIL CONFIG
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@benergy.io")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "hello@benergy.io")

print(f"✅ Stripe: {stripe.api_key[:20]}...")
print(f"✅ Plans: {list(STRIPE_PLANS.keys())}")

# ================= DATABASE =================

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
    password_hash = Column(String, nullable=True)
    api_key = Column(String, unique=True, index=True)
    tier = Column(String, default="free")
    created_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    plan = Column(String, default="free")
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


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


# ================= GPU METRICS =================

def get_gpu_metrics():
    """Generate mock GPU metrics"""
    metrics = []
    for gpu_id in range(4):
        utilization = random.uniform(15, 85)
        memory_total = 10000
        memory_used = (utilization / 100) * memory_total
        temperature = 35 + (utilization / 100) * 35
        power_draw = 50 + (utilization / 100) * 200
        
        metrics.append({
            "gpu_id": gpu_id,
            "utilization": utilization,
            "memory_used": memory_used,
            "memory_total": memory_total,
            "temperature": temperature,
            "power_draw": power_draw,
        })
    return metrics


def store_gpu_metrics(db: Session):
    """Store GPU metrics in database"""
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

def calculate_recommendations(metrics: List[GPUMetricRead], avg_utilization: float):
    """Generate recommendations"""
    recommendations = []

    if avg_utilization < 30:
        recommendations.append("⚠️ GPUs underutilized (<30%). Batch workloads together.")
    elif avg_utilization > 90:
        recommendations.append("⚠️ High GPU utilization (>90%). Watch for bottlenecks.")

    recent_metrics = [
        m for m in metrics
        if (datetime.utcnow() - m.timestamp).total_seconds() < 3600
    ]

    if recent_metrics:
        max_util = max([m.utilization for m in recent_metrics])
        if max_util < 10:
            recommendations.append("💤 GPU idle for last hour. Check running jobs.")

    recommendations.append("💡 Shift heavy workloads to off-peak hours to save costs.")

    return recommendations[:3]


def estimate_monthly_cost(metrics: List[GPUMetricRead]):
    """Estimate monthly cost"""
    if not metrics:
        return 0.0

    avg_utilization = sum([m.utilization for m in metrics]) / len(metrics)
    idle_percentage = (100 - avg_utilization) / 100
    num_gpus = len(set([m.gpu_id for m in metrics]))
    hours_per_month = 730
    cost_per_idle_hour = 0.25

    return num_gpus * hours_per_month * idle_percentage * cost_per_idle_hour


# ================= FASTAPI APP =================

app = FastAPI(title="Benergy GPU API", version="2.0")

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

# ================= ROUTES =================

@app.get("/")
def root():
    return {
        "message": "👽 Benergy GPU Monitoring API v2.0",
        "status": "✅ RUNNING",
        "endpoints": {
            "dashboard": "/dashboard",
            "metrics": "/metrics/gpu/{id}",
            "alerts": "/alerts",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
def health():
    return {"status": "✅ ok", "service": "benergy-api"}


@app.post("/collect-metrics")
def collect_metrics(db: Session = Depends(get_db)):
    """Trigger GPU metric collection"""
    store_gpu_metrics(db)
    return {"status": "✅ success", "message": "Metrics collected", "count": 4}


@app.get("/dashboard")
def get_dashboard(hours: int = 24, db: Session = Depends(get_db)):
    """Get dashboard data with GPU metrics"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)

    metrics = db.query(GPUMetric).filter(GPUMetric.timestamp >= cutoff_time).all()

    if not metrics:
        # Return mock data if no metrics yet
        return DashboardData(
            total_gpus=4,
            avg_utilization=45.2,
            idle_percentage=54.8,
            peak_utilization=92.1,
            memory_usage=4521.5,
            estimated_monthly_cost=324.50,
            recommendations=[
                "⚠️ GPUs underutilized. Batch smaller jobs.",
                "💡 Schedule heavy training during off-peak.",
                "💤 GPU idle. Check running jobs."
            ],
            gpu_metrics=[],
        )

    gpu_metrics_read = [GPUMetricRead.model_validate(m) for m in metrics]
    utilizations = [m.utilization for m in gpu_metrics_read]
    avg_utilization = sum(utilizations) / len(utilizations)
    peak_utilization = max(utilizations)
    idle_percentage = 100 - avg_utilization
    memory_usage = sum([m.memory_used for m in gpu_metrics_read]) / len(gpu_metrics_read)
    total_gpus = len(set([m.gpu_id for m in gpu_metrics_read]))
    estimated_cost = estimate_monthly_cost(gpu_metrics_read)
    recommendations = calculate_recommendations(gpu_metrics_read, avg_utilization)

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
def get_single_gpu_metrics(gpu_id: int, hours: int = 24, db: Session = Depends(get_db)):
    """Get metrics for specific GPU"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    metrics = db.query(GPUMetric).filter(
        GPUMetric.gpu_id == gpu_id,
        GPUMetric.timestamp >= cutoff_time,
    ).all()
    return [GPUMetricRead.model_validate(m) for m in metrics]


@app.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    """Get active alerts"""
    cutoff_time = datetime.utcnow() - timedelta(hours=1)
    metrics = db.query(GPUMetric).filter(GPUMetric.timestamp >= cutoff_time).all()

    alerts = []
    if not metrics:
        return {"alerts": []}

    for metric in metrics:
        if metric.temperature > 80:
            alerts.append({
                "type": "high_temperature",
                "gpu_id": metric.gpu_id,
                "value": metric.temperature,
                "severity": "warning",
            })

    avg_utilization = sum([m.utilization for m in metrics]) / len(metrics)
    if avg_utilization < 20:
        alerts.append({
            "type": "underutilized",
            "avg_utilization": round(avg_utilization, 2),
            "severity": "info",
        })

    return {"alerts": alerts}


# ================= STRIPE CHECKOUT =================

@app.post("/create-checkout")
async def create_checkout(data: dict):
    """Create Stripe checkout session"""
    user_id = data.get("user_id", "guest")
    plan = data.get("plan", "team")

    print(f"\n🔷 CHECKOUT: user_id={user_id}, plan={plan}")

    if plan not in STRIPE_PLANS:
        return {"error": f"❌ Invalid plan: {plan}"}

    if not stripe.api_key:
        return {"error": "❌ Stripe not configured"}

    try:
        price_id = STRIPE_PLANS[plan]["price_id"]
        
        if not price_id:
            return {"error": f"❌ No price ID for plan: {plan}"}

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
        print(f"🔗 Checkout URL: {session.url}")

        return {
            "status": "✅ success",
            "url": session.url,
            "session_id": session.id,
            "plan": plan
        }

    except Exception as e:
        print(f"❌ Stripe error: {str(e)}")
        return {"error": f"❌ Stripe error: {str(e)}"}


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
    except ValueError as e:
        print(f"❌ Webhook error (invalid payload): {str(e)}")
        return {"error": "Invalid payload"}
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Webhook error (invalid signature): {str(e)}")
        return {"error": "Invalid signature"}

    # Handle checkout completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"].get("user_id", "unknown")
        plan = session["metadata"].get("plan", "unknown")
        
        print(f"\n✅ PAYMENT COMPLETED")
        print(f"   User: {user_id}")
        print(f"   Plan: {plan}")
        print(f"   Session: {session.get('subscription')}")

        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(
                Subscription.user_id == user_id
            ).first()
            
            if subscription:
                subscription.plan = plan
                subscription.stripe_subscription_id = session.get("subscription")
                subscription.updated_at = datetime.utcnow()
            else:
                subscription = Subscription(
                    user_id=user_id,
                    plan=plan,
                    stripe_subscription_id=session.get("subscription")
                )
                db.add(subscription)
            db.commit()
            print(f"✅ Subscription saved to DB")
        finally:
            db.close()

    return {"status": "✅ success"}


# ================= CONTACT FORM =================

@app.post("/contact")
async def contact_form(data: dict):
    """Handle contact form submission"""
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    company = data.get("company", "").strip()
    message = data.get("message", "").strip()

    print(f"\n📧 CONTACT FORM")
    print(f"   Name: {name}")
    print(f"   Email: {email}")
    print(f"   Company: {company}")

    if not all([name, email]):
        return {"error": "❌ Name and email required"}

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
                print(f"💾 Contact info logged: {name} <{email}>")
                return {
                    "status": "✅ received",
                    "message": "Thanks! We'll get back to you soon."
                }
        else:
            print(f"💾 Contact logged (email not configured):")
            print(body)
            return {
                "status": "✅ received",
                "message": "Thanks! We'll get back to you soon."
            }

    except Exception as e:
        print(f"❌ Contact form error: {str(e)}")
        return {"error": f"❌ Error: {str(e)}"}


# ================= USER ENDPOINTS =================

@app.get("/create-user")
def create_user(email: str = "user@example.com"):
    """Create a test user"""
    user_id = str(uuid.uuid4())
    api_key = str(uuid.uuid4())
    
    db = SessionLocal()
    try:
        user = User(email=email, api_key=api_key)
        subscription = Subscription(user_id=user_id, plan="free")
        
        db.add(user)
        db.add(subscription)
        db.commit()
        
        print(f"✅ User created: {user_id}")
        
        return {
            "status": "✅ success",
            "user_id": user_id,
            "api_key": api_key,
            "email": email,
            "plan": "free"
        }
    except Exception as e:
        print(f"❌ User creation error: {str(e)}")
        return {"error": f"❌ Error: {str(e)}"}
    finally:
        db.close()


# ================= MAIN =================

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Benergy API...\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
