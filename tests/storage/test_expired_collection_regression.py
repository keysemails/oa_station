import json
from datetime import datetime, timedelta, timezone

import pytest

from storage.database.sqlite_storage import SQLiteStorage


@pytest.mark.asyncio
async def test_expired_collection_keys_do_not_resurrect(tmp_path):
    db_path = tmp_path / "storage.db"
    storage = SQLiteStorage(database_file=str(db_path))
    await storage.initialize()

    try:
        expired_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

        async with storage._db_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO kv_store (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                ("set_key", json.dumps(["old"]), expired_at),
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO kv_store (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                ("hash_key", json.dumps({"old": "1"}), expired_at),
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO kv_store (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                ("list_key_l", json.dumps(["old"]), expired_at),
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO kv_store (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                ("list_key_r", json.dumps(["old"]), expired_at),
            )
            await db.commit()

        await storage.sadd("set_key", "new")
        await storage.hset("hash_key", "new", "2")
        await storage.lpush("list_key_l", "new_l")
        await storage.rpush("list_key_r", "new_r")

        assert await storage.smembers("set_key") == {"new"}
        assert await storage.hgetall("hash_key") == {"new": "2"}
        assert await storage.lrange("list_key_l", 0, -1) == ["new_l"]
        assert await storage.lrange("list_key_r", 0, -1) == ["new_r"]
    finally:
        await storage.close()
