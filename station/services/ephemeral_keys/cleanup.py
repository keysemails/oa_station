"""
Ephemeral key cleanup worker.
"""

import asyncio

import httpx
from loguru import logger

from .manager import EphemeralKeyManager
from storage.database.base import BaseStorage


class EphemeralKeyCleanupWorker:
    """Background worker that deletes expired ephemeral keys."""

    def __init__(self, storage: BaseStorage, management_key: str, cleanup_interval: int = 60):
        self.storage = storage
        self.ephemeral_key_manager = EphemeralKeyManager(management_key)
        self.cleanup_interval = cleanup_interval
        self.running = False
        self._task = None

    async def start(self):
        """Start cleanup worker."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"Ephemeral key cleanup worker started (interval: {self.cleanup_interval}s)")

    async def stop(self):
        """Stop cleanup worker."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.ephemeral_key_manager.close()
        logger.info("Ephemeral key cleanup worker stopped")

    async def _cleanup_loop(self):
        """Cleanup loop."""
        while self.running:
            try:
                deleted = await self._cleanup_expired_keys()
                if deleted > 0:
                    logger.info(f"Ephemeral key cleanup: deleted {deleted} expired keys")
                await asyncio.sleep(self.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ephemeral key cleanup error: {e}")
                await asyncio.sleep(60)

    async def _cleanup_expired_keys(self) -> int:
        """Delete keys that have expired and prune their DB records."""
        try:
            expired_keys = await self.storage.get_expired_issued_keys()
            if not expired_keys:
                return 0

            deleted_count = 0
            for key_info in expired_keys:
                key_hash = key_info["key_hash"]
                key_name = key_info.get("key_name", "unknown")

                try:
                    await self.ephemeral_key_manager.delete_key(key_hash)
                    await self.storage.delete_issued_key(key_hash)
                    deleted_count += 1
                    logger.debug(f"Deleted expired ephemeral key: {key_name} ({key_hash[:12]}...)")

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        await self.storage.delete_issued_key(key_hash)
                        deleted_count += 1
                        logger.debug(f"Removed non-existent key from tracking: {key_name}")
                    else:
                        logger.warning(f"Failed to delete key {key_name}: HTTP {e.response.status_code}")
                except Exception as e:
                    logger.error(f"Error deleting ephemeral key {key_name}: {e}")

            return deleted_count
        except Exception as e:
            logger.error(f"Ephemeral key cleanup failed: {e}")
            return 0
