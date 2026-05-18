import time
import random
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import GPUMetric, Base

# ================= DATABASE SETUP =================

DATABASE_URL = "sqlite:///./benergy.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)

# ================= GPU SIMULATOR =================

def generate_fake_gpu_metrics():
    """
    Simulates GPU data since Codespaces has no real GPU access
    """

    gpu_count = 2  # simulate 2 GPUs

    metrics = []

    for gpu_id in range(gpu_count):
        utilization = random.uniform(5, 95)
        memory_total = 8000
        memory_used = random.uniform(500, memory_total)

        metrics.append({
            "gpu_id": gpu_id,
            "utilization": round(utilization, 2),
            "memory_used": round(memory_used, 2),
            "memory_total": memory_total,
            "temperature": round(random.uniform(40, 85), 2),
            "power_draw": round(random.uniform(60, 200), 2),
        })

    return metrics

# ================= COLLECT LOOP =================

def collect_forever():
    """Continuously collect GPU metrics every 30 seconds"""

    print("🚀 GPU Collector started (SIMULATION MODE)")

    while True:
        db = None

        try:
            db = SessionLocal()

            metrics = generate_fake_gpu_metrics()

            for m in metrics:
                db_metric = GPUMetric(
                    gpu_id=m["gpu_id"],
                    timestamp=datetime.utcnow(),
                    utilization=m["utilization"],
                    memory_used=m["memory_used"],
                    memory_total=m["memory_total"],
                    temperature=m["temperature"],
                    power_draw=m["power_draw"],
                )

                db.add(db_metric)

            db.commit()

            print(f"✓ Metrics saved at {datetime.utcnow()}")

        except Exception as e:
            print(f"❌ Error: {e}")

        finally:
            if db:
                db.close()

        time.sleep(30)

# ================= MAIN =================

if __name__ == "__main__":
    collect_forever()