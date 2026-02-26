"""
Ticket storage abstraction for nonce spend tracking and redemption audit.
"""

import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from .database.base import BaseStorage


class TicketStorage:
    """Wrapper around unified storage for ticket-specific operations."""

    def __init__(self, storage: BaseStorage):
        self.storage = storage

    @asynccontextmanager
    async def _db_connection(self):
        """Use shared SQLite connection when available."""
        if hasattr(self.storage, "_db_connection"):
            async with self.storage._db_connection() as db:  # type: ignore[attr-defined]
                yield db
        else:
            raise RuntimeError("Storage backend does not expose _db_connection")

    async def mark_nonce_spent(self, nonce: str) -> bool:
        """Atomically mark nonce as spent. Returns False if already spent.
        Raises on database errors to distinguish from actual double-spend."""
        day_bucket = int(time.time()) // 86400
        return await self.storage.db_insert_if_not_exists(  # type: ignore[attr-defined]
            table="spent_nonces",
            data={"nonce": nonce, "day_bucket": day_bucket},
        )

    async def unmark_nonce_spent(self, nonce: str) -> bool:
        """Rollback spent nonce marker."""
        try:
            await self.storage.db_delete(  # type: ignore[attr-defined]
                table="spent_nonces",
                conditions={"nonce": nonce},
            )
            return True
        except Exception as e:
            logger.error(f"Failed to unmark nonce: {str(e)}")
            return False

    async def store_redeemed_ticket(self, nonce: str, ticket: str, metadata: Optional[Dict] = None) -> None:
        """Store redemption audit record."""
        hour_bucket = int(time.time()) // 3600
        ticket_data = {
            "nonce": nonce,
            "ticket": ticket,
            "redeemed_at": time.time(),
            "metadata": metadata or {},
        }
        await self.storage.db_insert(  # type: ignore[attr-defined]
            table="redeemed_tickets",
            data={
                "nonce": nonce,
                "ticket_data": json.dumps(ticket_data),
                "hour_bucket": hour_bucket,
            },
            ttl_seconds=30 * 86400,
        )

    async def get_redeemed_ticket(self, nonce: str) -> Optional[Dict[str, Any]]:
        """Get redemption record by nonce."""
        try:
            result = await self.storage.db_get(  # type: ignore[attr-defined]
                table="redeemed_tickets",
                id_column="nonce",
                id_value=nonce,
                expires_column="expires_at",
            )
            if result and result.get("ticket_data"):
                return json.loads(result["ticket_data"])
            return None
        except Exception as e:
            logger.error(f"Failed to read redeemed ticket: {str(e)}")
            return None

    async def get_recent_redemptions(self, hours: int = 24) -> List[str]:
        """Get nonces redeemed within a time window."""
        cutoff_hour = int((time.time() - (hours * 3600))) // 3600
        now = datetime.now(timezone.utc).isoformat()
        try:
            async with self._db_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT nonce
                    FROM redeemed_tickets
                    WHERE hour_bucket >= ?
                    AND (expires_at IS NULL OR expires_at > ?)
                    """,
                    (cutoff_hour, now),
                )
                return [row[0] for row in await cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to read recent redemptions: {str(e)}")
            return []

    async def get_spent_nonces_count(self, days: int = 7) -> int:
        """Get spent nonce count in last N days."""
        cutoff_day = int((time.time() - (days * 86400))) // 86400
        try:
            async with self._db_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT COUNT(*)
                    FROM spent_nonces
                    WHERE day_bucket >= ?
                    """,
                    (cutoff_day,),
                )
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to read spent nonce stats: {str(e)}")
            return 0
