"""
SQLite Storage - Unified implementation with TTL and key-value interface.
"""

import aiosqlite
import os
import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from loguru import logger

from .base import BaseStorage


class SQLiteStorage(BaseStorage):
    """
    SQLite storage with key-value interface and safe table operations.
    """

    # Security: Whitelist of allowed tables to prevent injection
    ALLOWED_TABLES = {'kv_store', 'issued_keys', 'spent_nonces', 'redeemed_tickets'}

    def __init__(self, database_file: str = "station.db"):
        self.database_file = database_file

        # Shared connection to reduce thread churn and SQLite locking.
        self._db: Optional[aiosqlite.Connection] = None
        self._db_lock = asyncio.Lock()
        self._db_timeout = float(os.getenv("STATION_DB_TIMEOUT", "10"))
        self._db_busy_timeout_ms = int(os.getenv("STATION_DB_BUSY_TIMEOUT_MS", "5000"))

        # TTL cleanup worker
        self.cleanup_worker = TTLCleanupWorker(self, cleanup_interval=60)

        logger.info(f"SQLite storage configured: {database_file}")

    async def _open_connection(self) -> aiosqlite.Connection:
        """Open a configured SQLite connection."""
        db = await aiosqlite.connect(self.database_file, timeout=self._db_timeout)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(f"PRAGMA busy_timeout = {int(self._db_busy_timeout_ms)}")
        await db.commit()
        return db

    @asynccontextmanager
    async def _db_connection(self):
        """Provide a shared SQLite connection guarded by a lock."""
        async with self._db_lock:
            if self._db is None:
                self._db = await self._open_connection()
            yield self._db

    async def initialize(self) -> None:
        """Initialize SQLite database and create tables."""
        try:
            if not os.path.exists(self.database_file):
                logger.info(f"Creating new SQLite database: {self.database_file}")

            await self._create_tables()

            # Set restrictive file permissions on database
            try:
                os.chmod(self.database_file, 0o600)
                logger.info(f"Set restrictive permissions (0600) on {self.database_file}")

                wal_file = f"{self.database_file}-wal"
                shm_file = f"{self.database_file}-shm"
                if os.path.exists(wal_file):
                    os.chmod(wal_file, 0o600)
                if os.path.exists(shm_file):
                    os.chmod(shm_file, 0o600)
            except Exception as e:
                logger.warning(f"Could not set database file permissions: {e}")

            await self.cleanup_worker.start()

            logger.info("SQLite storage initialized successfully with TTL cleanup")

        except Exception as e:
            logger.error(f"SQLite initialization failed: {str(e)}")
            raise

    async def _create_tables(self) -> None:
        """Create all required tables."""
        async with self._db_connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS issued_keys (
                    key_hash TEXT PRIMARY KEY,
                    key_name TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    credit_limit REAL,
                    duration_minutes INTEGER NOT NULL,
                    tickets_consumed INTEGER DEFAULT 1,
                    auth_method TEXT DEFAULT 'ticket'
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS spent_nonces (
                    nonce TEXT PRIMARY KEY,
                    day_bucket INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS redeemed_tickets (
                    nonce TEXT PRIMARY KEY,
                    ticket_data TEXT NOT NULL,
                    hour_bucket INTEGER NOT NULL,
                    expires_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: Add tickets_consumed column if it doesn't exist
            cursor = await db.execute("PRAGMA table_info(issued_keys)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'tickets_consumed' not in column_names:
                logger.info("Migrating issued_keys table: adding tickets_consumed column")
                await db.execute("ALTER TABLE issued_keys ADD COLUMN tickets_consumed INTEGER DEFAULT 1")
                await db.commit()

            if 'auth_method' not in column_names:
                logger.info("Migrating issued_keys table: adding auth_method column")
                await db.execute("ALTER TABLE issued_keys ADD COLUMN auth_method TEXT DEFAULT 'ticket'")
                await db.commit()

            # Performance indexes
            await db.execute("CREATE INDEX IF NOT EXISTS idx_kv_store_expires ON kv_store(expires_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_issued_keys_expires ON issued_keys(expires_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_spent_nonces_day_bucket ON spent_nonces(day_bucket)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_redeemed_tickets_hour_bucket ON redeemed_tickets(hour_bucket)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_redeemed_tickets_expires ON redeemed_tickets(expires_at)")

            await db.commit()
            logger.info("SQLite database tables created/verified")

    # ============= Security Validation =============

    def _validate_table(self, table: str) -> str:
        """Validate table name against whitelist to prevent injection."""
        if table not in self.ALLOWED_TABLES:
            raise ValueError(f"Invalid table name: {table}. Allowed tables: {list(self.ALLOWED_TABLES)}")
        return table

    def _validate_column(self, column: str) -> str:
        """Validate column name format to prevent injection."""
        if not re.match(r'^[a-zA-Z_]\w*$', column):
            raise ValueError(f"Invalid column name: {column}. Must be alphanumeric with underscores.")
        return column

    # ============= Generic Database Operations =============

    async def db_get(self, table: str, id_column: str, id_value: str,
                     expires_column: Optional[str] = None) -> Optional[Dict]:
        """Generic get with optional expiry check."""
        table = self._validate_table(table)
        id_column = self._validate_column(id_column)
        if expires_column:
            expires_column = self._validate_column(expires_column)

        async with self._db_connection() as db:
            if expires_column:
                query = f"""
                    SELECT * FROM {table}
                    WHERE {id_column} = ?
                    AND ({expires_column} IS NULL OR {expires_column} > ?)
                """
                cursor = await db.execute(query, (id_value, datetime.now(timezone.utc).isoformat()))
            else:
                query = f"SELECT * FROM {table} WHERE {id_column} = ?"
                cursor = await db.execute(query, (id_value,))

            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

    async def db_insert(self, table: str, data: Dict[str, Any],
                        ttl_seconds: Optional[int] = None,
                        expires_column: str = "expires_at") -> None:
        """Generic insert/upsert with optional TTL."""
        table = self._validate_table(table)

        if ttl_seconds is not None and ttl_seconds > 0:
            data = data.copy()
            expires_column = self._validate_column(expires_column)
            data[expires_column] = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()

        columns = [self._validate_column(col) for col in data.keys()]
        placeholders = ["?" for _ in columns]
        query = f"""
            INSERT OR REPLACE INTO {table} ({','.join(columns)})
            VALUES ({','.join(placeholders)})
        """

        async with self._db_connection() as db:
            await db.execute(query, tuple(data.values()))
            await db.commit()

    async def db_insert_if_not_exists(self, table: str, data: Dict[str, Any]) -> bool:
        """Atomic insert-if-not-exists. Returns True if inserted."""
        table = self._validate_table(table)
        columns = [self._validate_column(col) for col in data.keys()]
        placeholders = ["?" for _ in columns]

        query = f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({','.join(placeholders)})"

        async with self._db_connection() as db:
            cursor = await db.execute(query, tuple(data.values()))
            await db.commit()
            return cursor.rowcount == 1

    async def db_delete(self, table: str, conditions: Dict[str, Any]) -> int:
        """Generic delete with conditions. Returns rows deleted."""
        table = self._validate_table(table)

        if not conditions:
            raise ValueError("Delete conditions cannot be empty (safety check)")

        where_parts = []
        values = []
        for col, val in conditions.items():
            col = self._validate_column(col)
            where_parts.append(f"{col} = ?")
            values.append(val)

        where_clause = " AND ".join(where_parts)
        query = f"DELETE FROM {table} WHERE {where_clause}"

        async with self._db_connection() as db:
            cursor = await db.execute(query, tuple(values))
            await db.commit()
            return cursor.rowcount

    # ============= Key-Value Operations with TTL =============

    async def get(self, key: str) -> Optional[str]:
        """Get value with automatic TTL check."""
        async with self._db_connection() as db:
            cursor = await db.execute("""
                SELECT value FROM kv_store
                WHERE key = ?
                AND (expires_at IS NULL OR expires_at > ?)
            """, (key, datetime.now(timezone.utc).isoformat()))

            row = await cursor.fetchone()
            return row[0] if row else None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Set key-value with optional TTL."""
        expires_at = None
        if ttl is not None and ttl > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        async with self._db_connection() as db:
            await db.execute("""
                INSERT OR REPLACE INTO kv_store (key, value, expires_at)
                VALUES (?, ?, ?)
            """, (key, value, expires_at.isoformat() if expires_at else None))
            await db.commit()

    async def exists(self, key: str) -> bool:
        """Check if key exists and not expired."""
        async with self._db_connection() as db:
            cursor = await db.execute("""
                SELECT 1 FROM kv_store
                WHERE key = ?
                AND (expires_at IS NULL OR expires_at > ?)
            """, (key, datetime.now(timezone.utc).isoformat()))

            return await cursor.fetchone() is not None

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL for existing key."""
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        async with self._db_connection() as db:
            cursor = await db.execute("""
                UPDATE kv_store SET expires_at = ? WHERE key = ?
            """, (expires_at.isoformat(), key))
            await db.commit()
            return cursor.rowcount > 0

    async def incrby(self, key: str, amount: int) -> int:
        """Increment counter by amount atomically."""
        async with self._db_connection() as db:
            now = datetime.now(timezone.utc).isoformat()
            cursor = await db.execute("""
                INSERT INTO kv_store (key, value, expires_at)
                VALUES (?, ?, NULL)
                ON CONFLICT(key) DO UPDATE SET
                    value = CASE
                        WHEN expires_at IS NULL OR expires_at > ?
                        THEN CAST((CAST(value AS INTEGER) + ?) AS TEXT)
                        ELSE ?
                    END
                RETURNING CAST(value AS INTEGER)
            """, (key, str(amount), now, amount, str(amount)))

            row = await cursor.fetchone()
            await db.commit()
            return row[0] if row else amount

    # ============= Issued Keys =============

    async def store_issued_key(
        self,
        key_hash: str,
        key_name: str,
        expires_at: datetime,
        credit_limit: Optional[float],
        duration_minutes: int,
        tickets_consumed: int = 1,
        auth_method: str = "ticket"
    ) -> None:
        """Store an issued ephemeral API key for tracking and cleanup."""
        try:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            else:
                expires_at = expires_at.astimezone(timezone.utc)

            async with self._db_connection() as db:
                await db.execute("""
                    INSERT INTO issued_keys
                    (key_hash, key_name, expires_at, credit_limit, duration_minutes, tickets_consumed, auth_method)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    key_hash,
                    key_name,
                    expires_at.isoformat(),
                    credit_limit,
                    duration_minutes,
                    tickets_consumed,
                    auth_method
                ))
                await db.commit()
                logger.debug(f"Stored issued key: {key_hash[:12]}... (auth={auth_method}, expires: {expires_at})")
        except Exception as e:
            logger.error(f"Error storing issued key: {str(e)}")
            raise

    async def get_expired_issued_keys(self) -> List[Dict[str, Any]]:
        """Get all issued keys that have expired."""
        try:
            async with self._db_connection() as db:
                db.row_factory = aiosqlite.Row
                now = datetime.now(timezone.utc).isoformat()

                cursor = await db.execute("""
                    SELECT key_hash, key_name, expires_at, credit_limit, duration_minutes
                    FROM issued_keys
                    WHERE expires_at < ?
                    ORDER BY expires_at ASC
                """, (now,))

                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting expired issued keys: {str(e)}")
            return []

    async def delete_issued_key(self, key_hash: str) -> bool:
        """Remove an issued key from tracking after deletion."""
        try:
            async with self._db_connection() as db:
                cursor = await db.execute("""
                    DELETE FROM issued_keys WHERE key_hash = ?
                """, (key_hash,))
                await db.commit()

                deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug(f"Deleted issued key from tracking: {key_hash[:12]}...")
                return deleted
        except Exception as e:
            logger.error(f"Error deleting issued key: {str(e)}")
            return False

    async def ping(self) -> bool:
        """Check if storage is responsive."""
        try:
            async with self._db_connection() as db:
                await db.execute("SELECT 1")
                return True
        except Exception:
            return False

    async def close(self) -> None:
        """Clean up database connections and stop TTL worker."""
        await self.cleanup_worker.stop()

        if self._db is not None:
            await self._db.close()
            self._db = None

        logger.info("SQLite storage cleanup complete")


class TTLCleanupWorker:
    """Background worker for cleaning up expired TTL entries."""

    def __init__(self, storage, cleanup_interval: int = 60):
        self.storage = storage
        self.cleanup_interval = cleanup_interval
        self.running = False
        self._task = None

    async def start(self):
        """Start the cleanup worker."""
        if self.running:
            return

        self.running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"TTL cleanup worker started (interval: {self.cleanup_interval}s)")

    async def stop(self):
        """Stop the cleanup worker."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TTL cleanup worker stopped")

    async def _cleanup_loop(self):
        """Main cleanup loop."""
        while self.running:
            try:
                deleted = await self._cleanup_expired()
                if deleted > 0:
                    logger.info(f"TTL cleanup: removed {deleted} expired entries")

                await asyncio.sleep(self.cleanup_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TTL cleanup error: {e}")
                await asyncio.sleep(60)

    async def _cleanup_expired(self) -> int:
        """Clean up expired entries. Returns count deleted."""
        try:
            async with self.storage._db_connection() as db:
                now = datetime.now(timezone.utc).isoformat()

                cursor = await db.execute("""
                    DELETE FROM kv_store
                    WHERE expires_at IS NOT NULL
                    AND expires_at < ?
                """, (now,))
                total_deleted = cursor.rowcount

                await db.commit()
                return total_deleted

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0
