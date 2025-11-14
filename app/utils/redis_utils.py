import os
import redis

_redis_client = None

def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", 6379))
    db = int(os.environ.get("REDIS_DB", 0))
    _redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    return _redis_client
