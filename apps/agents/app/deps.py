from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis
from starlette.requests import HTTPConnection


# HTTPConnection, not Request, so these also work in WebSocket routes
def get_db(conn: HTTPConnection) -> AsyncDatabase:
    return conn.app.state.db


def get_redis(conn: HTTPConnection) -> Redis:
    return conn.app.state.redis


def get_prefix() -> str:
    """Redis key prefix for queues; tests override it with a throwaway one."""
    return "bull"
