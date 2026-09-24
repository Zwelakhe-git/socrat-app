import os
import json
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    print("✅ Connected to Redis")
except Exception as e:
    print(f"⚠️ Redis unavailable: {e}")
    redis_client = None


def cache_set(key: str, value, ttl: int = 3600):
    if not redis_client:
        return
    try:
        redis_client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except Exception as e:
        print(f"Redis SET error: {e}")


def cache_get(key: str):
    if not redis_client:
        return None
    try:
        data = redis_client.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        print(f"Redis GET error: {e}")
        return None


def cache_delete(key: str):
    if not redis_client:
        return
    try:
        redis_client.delete(key)
    except Exception as e:
        print(f"Redis DEL error: {e}")


def get_cached_history(session_id: int):
    """Get cached chat history for a session."""
    return cache_get(f"history:{session_id}")