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

# ================= STATIC FILES (FIXED FOR RENDER) =================
BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")

if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static"
)

# ================= CORS =================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= DASHBOARD ROUTE (FIXED) =================

@app.get("/dashboard")
def dashboard():
    file_path = os.path.join(STATIC_DIR, "dashboard.html")

    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="text/html")

    return {
        "error": "dashboard.html not found",
        "expected_path": file_path
    }

# ================= HEALTH =================

@app.get("/health")
def health():
    return {"status": "ok", "service": "benergy-api"}

# ================= ROOT =================

@app.get("/")
def root():
    return {
        "message": "👽 Benergy GPU Monitoring API",
        "status": "RUNNING",
        "version": "4.0",
        "endpoints": {
            "dashboard": "/dashboard",
            "static_dashboard": "/static/dashboard.html",
            "health": "/health"
        }
    }

# ================= GPU MOCK (SAFE) =================

@app.get("/metrics")
def metrics():
    return {
        "gpu_utilization": random.randint(20, 80),
        "memory_used": random.randint(2000, 8000),
        "temperature": random.randint(40, 75),
        "gpu_type": "A100",
        "status": "success"
    }

# ================= WAITLIST =================

@app.post("/waitlist")
async def waitlist(data: dict):
    email = data.get("email", "").strip()

    if not email:
        return {"error": "Email required"}

    print(f"📧 WAITLIST: {email}")

    return {
        "status": "success",
        "message": "Added to waitlist",
        "email": email
    }

# ================= CONTACT =================

@app.post("/contact")
async def contact(data: dict):
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()

    if not email:
        return {"error": "Email required"}

    print(f"📧 CONTACT: {name} <{email}>")

    return {
        "status": "success",
        "message": "We will contact you soon",
        "email": email
    }

# ================= MAIN =================

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Benergy API v4.0...\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
