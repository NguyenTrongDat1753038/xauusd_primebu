# d:\Code\XAU_Bot_Predict\app\routers\bots.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from tasks.bot_tasks import start_bot_task, stop_bot_task, BOT_ID_TO_CONFIG
import redis
import json
import os

router = APIRouter()

# Initialize Redis connection
redis_client = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, db=0, decode_responses=True)

def get_bot_redis_key(bot_id: str):
    """Generates the Redis key for storing a bot's state."""
    return f"bot:state:{bot_id}"

class BotControlRequest(BaseModel):
    bot_id: str

@router.post("/bots/start")
async def start_bot_api(request: BotControlRequest):
    """API endpoint to start a bot via a Celery task. Fallback to local run if broker unavailable."""
    print(f"Received request to START bot: {request.bot_id}")
    try:
        task = start_bot_task.delay(request.bot_id)
        return {"message": f"Start request for bot '{request.bot_id}' sent via Celery.", "task_id": getattr(task, 'id', None)}
    except Exception as e:
        try:
            result = start_bot_task.run(request.bot_id)
            return {"message": "Celery unavailable. Started locally.", "result": result}
        except Exception as inner:
            raise HTTPException(status_code=500, detail=f"Failed to start bot: {inner}")

@router.post("/bots/stop")
async def stop_bot_api(request: BotControlRequest):
    """API endpoint to stop a bot via a Celery task. Fallback to local run if broker unavailable."""
    print(f"Received request to STOP bot: {request.bot_id}")
    try:
        task = stop_bot_task.delay(request.bot_id)
        return {"message": f"Stop request for bot '{request.bot_id}' sent via Celery.", "task_id": getattr(task, 'id', None)}
    except Exception as e:
        try:
            result = stop_bot_task.run(request.bot_id)
            return {"message": "Celery unavailable. Stopped locally.", "result": result}
        except Exception as inner:
            raise HTTPException(status_code=500, detail=f"Failed to stop bot: {inner}")


@router.get("/bots")
async def get_all_bots_status():
    """API endpoint to get the status of all configured bots from Redis."""
    print("Received request to get all bots status from Redis.")
    
    all_statuses = {}
    
    # Iterate over all known bot configurations
    for bot_id in BOT_ID_TO_CONFIG.keys():
        redis_key = get_bot_redis_key(bot_id)
        state_json = redis_client.get(redis_key)
        
        if state_json:
            state = json.loads(state_json)
            # If status is running, we can add more info like PID
            if state.get("status") == "running":
                all_statuses[bot_id] = {
                    "status": "running",
                    "pid": state.get("pid"),
                    "config_name": state.get("config_name")
                }
            else:
                 all_statuses[bot_id] = {"status": state.get("status", "stopped")}
        else:
            # If no state in Redis, assume it's stopped
            all_statuses[bot_id] = {"status": "stopped"}
            
    return all_statuses
