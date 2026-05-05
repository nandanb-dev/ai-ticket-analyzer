"""
MongoDB connection for FastAPI (Motor async driver).

When MONGODB_URI is set in the environment, the app lifespan opens a client
and verifies connectivity with a ping. Session services persist to MongoDB.
"""

from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import MONGODB_DB_NAME, MONGODB_URI

_motor_client: Optional[AsyncIOMotorClient] = None


def mongodb_enabled() -> bool:
    return bool(MONGODB_URI.strip())


def get_database() -> AsyncIOMotorDatabase:
    if not mongodb_enabled():
        raise RuntimeError("MongoDB is not configured (MONGODB_URI is empty).")
    if _motor_client is None:
        raise RuntimeError("MongoDB client is not initialized; check application lifespan.")
    return _motor_client[MONGODB_DB_NAME]


async def connect_mongodb() -> None:
    global _motor_client
    if not mongodb_enabled():
        return
    _motor_client = AsyncIOMotorClient(MONGODB_URI)
    await _motor_client.admin.command("ping")


async def close_mongodb() -> None:
    global _motor_client
    if _motor_client is not None:
        _motor_client.close()
        _motor_client = None
