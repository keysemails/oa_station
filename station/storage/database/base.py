"""
Abstract Base Storage Interface.

Defines the storage contract for all backends (currently SQLite).
"""

from typing import Optional, Dict, List, Any


class BaseStorage:
    """
    Base class defining the storage interface.

    Storage implementations should inherit from this class and implement
    all methods. This ensures storage independence — application code
    doesn't know or care what database is underneath.
    """

    async def initialize(self) -> None:
        """Initialize the storage backend."""
        pass

    async def close(self) -> None:
        """Close storage connections and cleanup."""
        pass

    # ============= Generic SQL Helpers =============

    async def db_get(self, table: str, id_column: str, id_value: str, expires_column: Optional[str] = None) -> Optional[Dict]:
        """Get a row from table by ID with optional expiry filtering."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement db_get()")

    async def db_insert(self, table: str, data: Dict[str, Any], ttl_seconds: Optional[int] = None, expires_column: str = "expires_at") -> None:
        """Insert/upsert row into table with optional TTL."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement db_insert()")

    async def db_insert_if_not_exists(self, table: str, data: Dict[str, Any]) -> bool:
        """Insert row iff it does not already exist."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement db_insert_if_not_exists()")

    async def db_delete(self, table: str, conditions: Dict[str, Any]) -> int:
        """Delete rows matching conditions."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement db_delete()")

    # ============= Key-Value Operations =============

    async def get(self, key: str) -> Optional[str]:
        """Get a value by key."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement get()")

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Set a key-value pair with optional TTL in seconds."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement set()")

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement exists()")

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration time for a key. Returns True if successful."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement expire()")

    async def incrby(self, key: str, amount: int) -> int:
        """Increment a counter by amount atomically. Returns new value."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement incrby()")

    # ============= Issued Key Operations =============

    async def store_issued_key(
        self, key_hash: str, key_name: str, expires_at: Any,
        credit_limit: Optional[float], duration_minutes: int,
        tickets_consumed: int = 1, auth_method: str = "ticket"
    ) -> None:
        """Store an issued ephemeral API key."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement store_issued_key()")

    async def get_expired_issued_keys(self) -> List[Dict[str, Any]]:
        """Get all expired issued keys."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement get_expired_issued_keys()")

    async def delete_issued_key(self, key_hash: str) -> bool:
        """Delete an issued key by hash."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement delete_issued_key()")

    async def ping(self) -> bool:
        """Check if storage is responsive."""
        raise NotImplementedError(f"{self.__class__.__name__} doesn't implement ping()")
