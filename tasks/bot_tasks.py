# d:\Code\XAU_Bot_Predict\tasks/bot_tasks.py
# -*- coding: utf-8 -*-
import subprocess
import os
import signal
import sys
import json
import redis
from pathlib import Path
from .celery_worker import celery_app

# Initialize Redis connection
# This assumes Redis is running on localhost:6379
# Celery already uses Redis as a broker, so the connection should be available.
redis_client = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, db=0, decode_responses=True)


# Mapping từ bot_id (frontend) tới config file name
BOT_ID_TO_CONFIG = {
    'xauusd': 'xauusd_prod',
    'btcusd': 'btcusd_prod',
    'eurgbp': 'eurgbp_prod',  # Conservative/Low risk
    'eurgbp_high_risk': 'eurgbp_prod_high_risk'  # High risk
}

# Get project path dynamically
PROJECT_PATH = str(Path(__file__).parent.parent.absolute())
print(f"[bot_tasks.py] Project path: {PROJECT_PATH}")

# Detect if running on Windows host or Docker container
IS_DOCKER = os.path.exists('/.dockerenv')
IS_WINDOWS = sys.platform == 'win32'

print(f"[bot_tasks.py] IS_DOCKER={IS_DOCKER}, IS_WINDOWS={IS_WINDOWS}")

def get_bot_redis_key(bot_id: str):
    """Generates the Redis key for storing a bot's state."""
    return f"bot:state:{bot_id}"

def is_wsl_host():
    """Check if we're in Docker with access to Windows host."""
    # In Docker on Windows (WSL2), we might be able to call host PowerShell
    return IS_DOCKER and os.path.exists('/run/WSL')

def call_host_powershell(bot_config):
    """
    Call PowerShell script on Windows host from Docker.
    Works only with Docker Desktop on Windows + WSL2.
    """
    try:
        # Map bot_config back to bot_id
        bot_id = next((k for k, v in BOT_ID_TO_CONFIG.items() if v == bot_config), None)
        if not bot_id:
            bot_id = bot_config  # Fallback to config name
        
        # Try to call host via wsl command
        ps_script = r'\\wsl.localhost\docker-desktop\mnt\d\Code\XAU_Bot_Predict\start_bot_directly.ps1'
        cmd = f'powershell.exe -Command "& {ps_script} -BotName {bot_config}"'
        
        print(f"[call_host_powershell] Calling: {cmd}")
        process = subprocess.Popen(cmd, shell=True)
        return process
    except Exception as e:
        print(f"[call_host_powershell] Error: {e}")
        raise

@celery_app.task
def start_bot_task(bot_id: str):
    """
    Celery task to launch a bot process and store its state in Redis.
    
    ⚠️ IMPORTANT: MT5 runs only on Windows!
    - If on Windows host: Launch bot directly.
    - If in Docker: Call PowerShell script on the Windows host (via WSL2).
    """
    config_name = BOT_ID_TO_CONFIG.get(bot_id)
    if not config_name:
        msg = f"❌ Unknown bot_id '{bot_id}'. Available: {list(BOT_ID_TO_CONFIG.keys())}"
        print(msg)
        return {"error": msg}

    # Check if bot is already running
    redis_key = get_bot_redis_key(bot_id)
    existing_state_json = redis_client.get(redis_key)
    if existing_state_json:
        existing_state = json.loads(existing_state_json)
        if existing_state.get("status") == "running":
            msg = f"⚠️ Bot '{bot_id}' is already marked as running with PID {existing_state.get('pid')}."
            print(msg)
            return {"status": "already_running", "message": msg}

    print(f"\n[start_bot_task] Starting bot: {bot_id} → {config_name}")
    print(f"[start_bot_task] Context: Docker={IS_DOCKER}, Windows={IS_WINDOWS}")
    
    try:
        if IS_DOCKER:
            print("[start_bot_task] Attempting to call bot on Windows host...")
            process = call_host_powershell(config_name)
        else:
            script_path = os.path.join(PROJECT_PATH, "production", "run_live.py")
            python_exe = sys.executable
            
            command = [python_exe, script_path, config_name]
            print(f"[start_bot_task] Direct command: {' '.join(command)}")
            
            if IS_WINDOWS:
                process = subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                process = subprocess.Popen(command, preexec_fn=os.setsid)
        
        # Store bot state in Redis
        bot_state = {
            'pid': process.pid,
            'config_name': config_name,
            'status': 'running',
            'bot_id': bot_id
        }
        redis_client.set(redis_key, json.dumps(bot_state))
        
        msg = f"✅ Bot '{bot_id}' started with PID {process.pid}. State saved to Redis."
        print(msg)
        return {
            "bot_id": bot_id,
            "config_name": config_name,
            "pid": process.pid,
            "status": "running",
            "message": msg
        }
    except Exception as e:
        msg = f"❌ Error starting bot '{bot_id}': {str(e)}"
        print(msg)
        # Ensure no stale state is left in Redis
        redis_client.delete(redis_key)
        return {"error": str(e), "bot_id": bot_id, "message": msg}

@celery_app.task
def stop_bot_task(bot_id: str):
    """Celery task to stop a bot process using state from Redis."""
    redis_key = get_bot_redis_key(bot_id)
    bot_state_json = redis_client.get(redis_key)
    
    if not bot_state_json:
        msg = f"⚠️ Bot '{bot_id}' not found in Redis. Cannot stop."
        print(msg)
        return {"error": "Bot not found or already stopped", "message": msg}
    
    bot_state = json.loads(bot_state_json)
    pid = bot_state.get('pid')
    
    if not pid:
        msg = f"❌ No PID found for bot '{bot_id}' in Redis."
        print(msg)
        redis_client.delete(redis_key) # Clean up invalid state
        return {"error": "PID not found in state", "message": msg}
    
    try:
        # This logic assumes the process (PID) is accessible from the Celery worker.
        # This will work if the worker and bot process are on the same OS (e.g., both on Windows).
        # It will FAIL if the worker is in Docker and the bot is on the Windows host.
        # A proper solution for the Docker case requires a more complex IPC mechanism.
        print(f"🛑 Attempting to stop bot '{bot_id}' (PID: {pid})")
        if IS_WINDOWS and not IS_DOCKER:
            # Use CTRL_BREAK_EVENT for a graceful shutdown on Windows
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            # Use SIGTERM for Unix-like systems or when inside Docker
            # This might not work for processes on the host from Docker
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        
        msg = f"✅ Stop signal sent to bot '{bot_id}' (PID: {pid})."
        print(msg)
        
        # Update state in Redis to 'stopped'
        bot_state['status'] = 'stopped'
        bot_state['pid'] = None
        redis_client.set(redis_key, json.dumps(bot_state))
        
        return {"bot_id": bot_id, "status": "stopped", "message": msg}
    except ProcessLookupError:
        msg = f"⚠️ Process {pid} for bot '{bot_id}' not found (already stopped)."
        print(msg)
        # Clean up state in Redis
        redis_client.delete(redis_key)
        return {"error": "Process not found", "bot_id": bot_id, "message": msg}
    except Exception as e:
        msg = f"❌ Error stopping bot '{bot_id}': {str(e)}"
        print(msg)
        # Don't delete the key, so we can inspect the failed state
        bot_state['status'] = 'error_stopping'
        redis_client.set(redis_key, json.dumps(bot_state))
        return {"error": str(e), "bot_id": bot_id, "message": msg}
