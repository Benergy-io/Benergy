#!/usr/bin/env python3
"""
Benergy GPU Monitoring Agent
Collects GPU metrics and sends to Benergy API
"""

import subprocess
import requests
import json
import time
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# ================= SETUP LOGGING =================

LOG_DIR = Path.home() / ".benergy"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "agent.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ================= CONFIG =================

API_BASE_URL = "https://benergy.onrender.com"
METRICS_ENDPOINT = f"{API_BASE_URL}/metrics"
CONFIG_FILE = LOG_DIR / "config.json"
COLLECTION_INTERVAL = 60  # seconds

# ================= UTILITY FUNCTIONS =================

def load_config():
    """Load configuration from file"""
    if not CONFIG_FILE.exists():
        logger.error(f"Config file not found: {CONFIG_FILE}")
        return None
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return None


def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        os.chmod(CONFIG_FILE, 0o600)  # Only owner can read
        logger.info(f"Config saved to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def get_gpu_metrics():
    """
    Get GPU metrics using nvidia-smi
    Returns: dict with gpu_utilization, memory_used, temperature
    """
    try:
        # Query: utilization.gpu, memory.used, temperature.gpu
        cmd = (
            "nvidia-smi --query-gpu=utilization.gpu,memory.used,temperature.gpu "
            "--format=csv,noheader,nounits"
        )
        
        result = subprocess.check_output(
            cmd,
            shell=True,
            timeout=10,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        if not result:
            logger.warning("nvidia-smi returned empty response")
            return None
        
        parts = result.split(',')
        if len(parts) < 3:
            logger.warning(f"nvidia-smi returned unexpected format: {result}")
            return None
        
        try:
            gpu_util = int(float(parts[0].strip()))
            memory = int(float(parts[1].strip()))
            temp = int(float(parts[2].strip()))
            
            return {
                "gpu_utilization": gpu_util,
                "memory_used": memory,
                "temperature": temp
            }
        except ValueError as e:
            logger.error(f"Failed to parse nvidia-smi output: {e}")
            return None
    
    except subprocess.TimeoutExpired:
        logger.error("nvidia-smi timed out")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"nvidia-smi failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting GPU metrics: {e}")
        return None


def send_metrics(api_key, metrics):
    """
    Send metrics to Benergy API
    Returns: True if successful, False otherwise
    """
    try:
        payload = {
            "api_key": api_key,
            **metrics
        }
        
        response = requests.post(
            METRICS_ENDPOINT,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Metrics sent: util={metrics['gpu_utilization']}%, "
                       f"mem={metrics['memory_used']}MB, "
                       f"temp={metrics['temperature']}°C")
            return True
        else:
            logger.error(f"API error {response.status_code}: {response.text}")
            return False
    
    except requests.exceptions.Timeout:
        logger.error("Request to API timed out")
        return False
    except requests.exceptions.ConnectionError:
        logger.error("Failed to connect to API")
        return False
    except Exception as e:
        logger.error(f"Failed to send metrics: {e}")
        return False


def run_collection_loop(api_key):
    """
    Main collection loop - run forever
    Collects and sends metrics every COLLECTION_INTERVAL seconds
    """
    logger.info("=" * 60)
    logger.info("🚀 Benergy GPU Agent Started")
    logger.info(f"📍 API: {API_BASE_URL}")
    logger.info(f"⏱️  Interval: {COLLECTION_INTERVAL}s")
    logger.info("=" * 60)
    
    consecutive_failures = 0
    max_failures = 10  # Stop after 10 consecutive failures
    
    while True:
        try:
            # Get GPU metrics
            metrics = get_gpu_metrics()
            
            if metrics is None:
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    logger.error(f"❌ Failed {max_failures} times in a row. Stopping.")
                    sys.exit(1)
                logger.warning(f"⚠️  Failed to get metrics (attempt {consecutive_failures}/{max_failures})")
                time.sleep(COLLECTION_INTERVAL)
                continue
            
            # Reset failure counter on success
            consecutive_failures = 0
            
            # Send to API
            success = send_metrics(api_key, metrics)
            
            if not success:
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    logger.error(f"❌ Failed to send {max_failures} times. Stopping.")
                    sys.exit(1)
            
            # Wait before next collection
            time.sleep(COLLECTION_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("👋 Agent stopped by user")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error in collection loop: {e}")
            consecutive_failures += 1
            time.sleep(COLLECTION_INTERVAL)


def setup_wizard():
    """
    Interactive setup wizard for first-time configuration
    """
    logger.info("=" * 60)
    logger.info("🛠️  Benergy Agent Setup Wizard")
    logger.info("=" * 60)
    
    # Check for nvidia-smi
    logger.info("\n✓ Checking for NVIDIA GPU...")
    metrics = get_gpu_metrics()
    if metrics is None:
        logger.error("❌ No NVIDIA GPU detected!")
        logger.error("   Make sure nvidia-smi is installed and GPU is available")
        sys.exit(1)
    
    logger.info(f"✅ GPU detected!")
    logger.info(f"   Utilization: {metrics['gpu_utilization']}%")
    logger.info(f"   Memory: {metrics['memory_used']}MB")
    logger.info(f"   Temperature: {metrics['temperature']}°C")
    
    # Get API key
    logger.info("\n📝 Enter your Benergy API key")
    logger.info("   Get it here: https://benergy.onrender.com/dashboard")
    api_key = input("   API Key: ").strip()
    
    if not api_key or len(api_key) < 10:
        logger.error("❌ Invalid API key")
        sys.exit(1)
    
    # Confirm
    logger.info("\n✓ Configuration:")
    logger.info(f"  API Key: {api_key[:10]}...{api_key[-4:]}")
    logger.info(f"  Interval: {COLLECTION_INTERVAL}s")
    logger.info(f"  Log File: {LOG_FILE}")
    
    confirm = input("\n✓ Continue? (yes/no): ").strip().lower()
    if confirm != 'yes':
        logger.info("Setup cancelled")
        sys.exit(0)
    
    # Save config
    config = {
        "api_key": api_key,
        "created_at": datetime.now().isoformat()
    }
    save_config(config)
    
    logger.info("\n✅ Setup complete!")
    logger.info("   Agent will now start collecting GPU metrics")
    logger.info(f"   Logs: {LOG_FILE}")
    logger.info("\n🚀 Starting agent...\n")
    
    return api_key


def main():
    """Main entry point"""
    
    # Check if setup needed
    if not CONFIG_FILE.exists():
        api_key = setup_wizard()
    else:
        config = load_config()
        if not config or "api_key" not in config:
            logger.error("Invalid config. Running setup again...")
            api_key = setup_wizard()
        else:
            api_key = config["api_key"]
            logger.info(f"✅ Loaded config from {CONFIG_FILE}")
    
    # Start collection loop
    run_collection_loop(api_key)


if __name__ == "__main__":
    main()
