"""Async MongoDB client factory using Motor."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from shared.logging import get_logger

logger = get_logger("mongo_client")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def get_mongo_db(
    uri: str = "mongodb://localhost:27017/clinic_db",
    database: str = "clinic_db",
) -> AsyncIOMotorDatabase:
    """Get or create a shared async MongoDB client and return the database.

    Args:
        uri: MongoDB connection URI.
        database: Database name.

    Returns:
        Motor async database instance.
    """
    global _client, _db

    if _db is None:
        _client = AsyncIOMotorClient(
            uri,
            maxPoolSize=20,
            minPoolSize=5,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
        )
        _db = _client[database]
        logger.info("mongodb_connected", database=database)

    return _db


async def close_mongo() -> None:
    """Close the MongoDB client."""
    global _client, _db

    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("mongodb_disconnected")


async def ping_mongo(db: AsyncIOMotorDatabase) -> bool:
    """Check MongoDB connectivity.

    Args:
        db: Motor database instance.

    Returns:
        True if MongoDB is reachable.
    """
    try:
        result = await db.command("ping")
        return result.get("ok") == 1.0
    except Exception as e:
        logger.error("mongodb_ping_failed", error=str(e))
        return False
