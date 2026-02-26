"""
Storage Factory - Clean and minimal storage creation.
"""

from typing import Optional
from loguru import logger

from .base import BaseStorage
from .sqlite_storage import SQLiteStorage


class StorageFactory:
    """
    Factory to create storage backends with unified interface.
    """

    @staticmethod
    async def create_storage(
        storage_type: str = "sqlite",
        database_file: Optional[str] = None,
        **kwargs
    ) -> BaseStorage:
        """
        Create storage backend based on type.

        Args:
            storage_type: "sqlite"
            database_file: SQLite file path

        Returns:
            BaseStorage implementation
        """
        storage_type = storage_type.lower()

        if storage_type == "sqlite":
            db_file = database_file or "station.db"

            logger.info(f"Creating SQLite storage: {db_file}")
            storage = SQLiteStorage(database_file=db_file)

        else:
            raise ValueError(f"Unsupported storage type: {storage_type}. Currently supported: 'sqlite'.")

        await storage.initialize()

        logger.info(f"Storage backend initialized: {storage.__class__.__name__}")
        return storage


async def create_sqlite_storage(database_file: str = "station.db") -> BaseStorage:
    """Convenience helper for creating SQLite storage."""
    return await StorageFactory.create_storage(
        storage_type="sqlite",
        database_file=database_file,
    )
