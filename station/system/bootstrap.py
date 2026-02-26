"""
Station bootstrap for pre-server initialization.

This module handles synchronous initialization that MUST complete before
uvicorn starts:
1. Ed25519 identity creation/loading
"""

from typing import Optional, TYPE_CHECKING

from loguru import logger

from .config import Settings

if TYPE_CHECKING:
    from identity import StationIdentity


_identity: Optional["StationIdentity"] = None


def get_identity() -> Optional["StationIdentity"]:
    """Get the initialized identity instance."""
    return _identity


def bootstrap_identity(settings: Settings) -> "StationIdentity":
    """
    Initialize Ed25519 identity for station signing.
    """
    global _identity

    from identity import StationIdentity

    logger.info("=" * 60)
    logger.info("Initializing Station Identity (Ed25519)...")
    logger.info("=" * 60)

    identity = StationIdentity(settings.identity_file)
    public_key = identity.load_or_create()

    logger.info("Station Identity ready")
    logger.info(f"Public Key: {public_key[:16]}...{public_key[-8:]}")
    logger.info(f"Station ID: {settings.station_id}")
    logger.info("=" * 60)

    _identity = identity
    return identity


def bootstrap_station(settings: Optional[Settings] = None) -> "StationIdentity":
    """
    Main bootstrap entrypoint.
    """
    if settings is None:
        settings = Settings()

    return bootstrap_identity(settings)
