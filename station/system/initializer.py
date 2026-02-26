"""
Station Initializer - Sets up station components (async phase).
"""

import json
import os
import secrets
from typing import Optional, TYPE_CHECKING

from loguru import logger

from .config import Settings, TICKET_KEYS_FILE
from .bootstrap import get_identity
from storage import TicketStorage, StorageFactory, BaseStorage
from services import EphemeralKeyCleanupWorker

if TYPE_CHECKING:
    from identity import StationIdentity


class StationInitializer:
    """
    Initializes all station components at startup.
    """

    def __init__(self, settings: Settings, identity: Optional["StationIdentity"] = None):
        self.settings = settings
        self.identity = identity or get_identity()

        self.storage: Optional[BaseStorage] = None
        self.ticket_storage: Optional[TicketStorage] = None

        self.ticket_issuance_service = None
        self.ticket_redemption_service = None
        self.ticket_request_bearer_token: Optional[str] = None

        self.ephemeral_key_cleanup_worker: Optional[EphemeralKeyCleanupWorker] = None

        logger.info(f"StationInitializer configured for {settings.storage_type.upper()} storage")

    async def initialize(self) -> None:
        """Initialize all station components."""
        try:
            if not self.identity:
                raise RuntimeError("Identity not initialized - call bootstrap_station() first")

            await self._initialize_storage()
            await self._initialize_ticket_services()
            self._initialize_ticket_request_bearer_token()
            await self._initialize_cleanup_worker()

            logger.info("Station initialization complete")

        except Exception as e:
            logger.error(f"Station initialization failed: {str(e)}")
            raise

    async def _initialize_storage(self) -> None:
        """Initialize storage backend."""
        if self.settings.storage_type.lower() != "sqlite":
            logger.warning(
                f"Unsupported storage type: {self.settings.storage_type}. Falling back to SQLite."
            )

        self.storage = await StorageFactory.create_storage(
            storage_type="sqlite",
            database_file=self.settings.database_file,
        )

        self.ticket_storage = TicketStorage(self.storage)

        logger.info(f"SQLite storage initialized: {self.settings.database_file}")

    def _load_or_generate_ticket_keys(self) -> tuple:
        """Load ticket keys from settings/file, or generate new ones."""
        public_key = self.settings.token_public_key
        private_key = self.settings.token_private_key

        if public_key or private_key:
            return public_key, private_key

        # Try loading from persisted file
        keys_file = TICKET_KEYS_FILE
        if keys_file.exists():
            try:
                data = json.loads(keys_file.read_text())
                public_key = data.get("public_key")
                private_key = data.get("private_key")
                if public_key and private_key:
                    logger.info(f"Loaded ticket keys from {keys_file}")
                    return public_key, private_key
            except Exception as e:
                logger.warning(f"Failed to load {keys_file}: {e}")

        # Generate new keys
        try:
            from inference_tickets import TicketManager
            public_key, private_key = TicketManager.generate_keypair()

            fd = os.open(str(keys_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, json.dumps({
                    "public_key": public_key,
                    "private_key": private_key,
                }, indent=2).encode())
            finally:
                os.close(fd)
            logger.info(f"Generated and saved new ticket keys to {keys_file}")
            return public_key, private_key
        except ImportError:
            return None, None

    async def _initialize_ticket_services(self) -> None:
        """Initialize inference ticket issuance/redemption services."""
        try:
            from inference_tickets import TicketManager

            public_key, private_key = self._load_or_generate_ticket_keys()

            services = await TicketManager.initialize_services(
                storage=self.storage,
                ticket_storage=self.ticket_storage,
                public_key=public_key,
                private_key=private_key,
            )

            self.ticket_issuance_service = services.get("issuance")
            self.ticket_redemption_service = services.get("redemption")

            if self.ticket_issuance_service:
                logger.info("Inference ticket issuance service ready")
            if self.ticket_redemption_service:
                logger.info("Inference ticket redemption service ready")
            if not self.ticket_issuance_service and not self.ticket_redemption_service:
                logger.warning("No inference ticket services initialized.")

        except ImportError as e:
            logger.warning(
                f"Inference ticket services unavailable: {e}. "
                "Install 'privacypass-py' to enable ticket auth."
            )
        except Exception as e:
            logger.error(f"Inference ticket services initialization failed: {str(e)}")
            logger.warning("Station will run without inference ticket auth")

    def _initialize_ticket_request_bearer_token(self) -> None:
        """
        Generate one-time bearer token for ticket issuance API access.
        """
        if not self.ticket_issuance_service:
            self.ticket_request_bearer_token = None
            logger.info("Ticket issuance bearer token not generated (issuance service unavailable)")
            return

        self.ticket_request_bearer_token = secrets.token_urlsafe(32)
        logger.info(
            "Ticket issuance bearer token generated (valid until restart, fixed to exactly 100 tickets/request)."
        )
        logger.info(f"Bearer token: {self.ticket_request_bearer_token}")
        logger.info("Also viewable via config UI at /config (if enabled)")

    async def _initialize_cleanup_worker(self) -> None:
        """Initialize expired ephemeral key cleanup worker."""
        if not self.settings.openrouter_management_key:
            logger.info("Management key not configured - key cleanup worker disabled")
            return

        self.ephemeral_key_cleanup_worker = EphemeralKeyCleanupWorker(
            storage=self.storage,
            management_key=self.settings.openrouter_management_key,
            cleanup_interval=60,
        )
        await self.ephemeral_key_cleanup_worker.start()
        logger.info("Ephemeral key cleanup worker started")

    def get_ticket_issuance_service(self):
        """Get ticket issuance service for dependency injection."""
        return self.ticket_issuance_service

    def get_ticket_redemption_service(self):
        """Get ticket redemption service for dependency injection."""
        return self.ticket_redemption_service

    async def close(self) -> None:
        """Clean up resources."""
        if self.ephemeral_key_cleanup_worker:
            await self.ephemeral_key_cleanup_worker.stop()
            logger.info("Ephemeral key cleanup worker stopped")

        if self.storage:
            await self.storage.close()
            logger.info(f"{self.settings.storage_type.upper()} storage closed")

        logger.info("Station initializer cleanup complete")
