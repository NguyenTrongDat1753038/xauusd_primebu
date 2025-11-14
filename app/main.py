# d:\Code\XAU_Bot_Predict\app\main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from .routers import bots
import redis
import json
from .utils.redis_utils import get_redis_client

app = FastAPI(title="Trading Bot Manager")

# Define allowed origins for CORS. This tells the backend that it's safe
# to accept requests from your frontend application.
origins = [
    "http://localhost:3000",  # The address of your frontend
    "http://localhost:3001",  # Fallback port if 3000 is in use
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://192.168.0.103:3000", # Thêm IP local của máy tính (frontend port)
    "http://192.168.0.103:3001", # Thêm IP local của máy tính (frontend port)
]

# Add CORS middleware to the application
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # Allow origins listed above
    allow_credentials=True,   # Allow cookies to be included in requests
    allow_methods=["*"],      # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],      # Allow all headers
)

app.include_router(bots.router, prefix="/api/v1", tags=["Bots"])

@app.post("/api/v1/bots/register_pid")
async def register_pid(request: Request):
    """
    Endpoint for live bot processes to register their PID with the manager.
    This allows the manager to have a record of the running bot's process ID.
    """
    data = await request.json()
    bot_id = data.get("bot_id")
    pid = data.get("pid")

    if not bot_id or not pid:
        return {"status": "error", "message": "bot_id and pid are required"}

    r = get_redis_client()
    bot_state_key = f"bot_state:{bot_id}"
    r.hset(bot_state_key, "pid", pid)
    return {"status": "success", "message": f"PID {pid} for bot {bot_id} registered."}

@app.get("/")
def read_root():
    return {"message": "Welcome to Trading Bot Manager API"}
