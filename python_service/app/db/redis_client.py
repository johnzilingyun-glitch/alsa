import redis.asyncio as redis
from typing import Optional

class RedisManager:
    _client: Optional[redis.Redis] = None

    @classmethod
    async def get_client(cls) -> redis.Redis:
        if cls._client is None:
            # Connect to local Redis for development
            cls._client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client is not None:
            await cls._client.close()
            cls._client = None

# Helper to easily get a client instance
async def get_redis() -> redis.Redis:
    return await RedisManager.get_client()
