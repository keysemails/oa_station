"""
Inference tickets manager.
"""

from typing import NamedTuple, Optional, Tuple

from loguru import logger

from storage import BaseStorage, TicketStorage


def _require_privacypass():
    """Import privacypass_py lazily so the station can still boot without it."""
    try:
        import privacypass_py as pp

        return pp
    except ImportError as e:
        raise ImportError(
            "privacypass_py is required for inference ticket features. "
            "Install dependency 'privacypass-py'."
        ) from e


class TokenRedemptionResult(NamedTuple):
    """Result of token redemption attempt."""

    valid: bool
    error: Optional[str] = None
    nonce: Optional[str] = None


class TicketManager:
    """Factory for creating ticket services."""

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """Generate a new Privacy Pass keypair."""
        pp = _require_privacypass()
        issuer = pp.IssuerServer()
        public_key = issuer.create_keypair()
        private_key = issuer.get_private_key(public_key)

        logger.info("=" * 80)
        logger.info("NEW KEYPAIR GENERATED")
        logger.info(f'STATION_TOKEN_PUBLIC_KEY="{public_key}"')
        logger.info("Private key saved to ticket_keys.json (not logged for security)")
        logger.info("=" * 80)

        return public_key, private_key

    @staticmethod
    async def initialize_services(
        storage: BaseStorage,
        ticket_storage: TicketStorage,
        public_key: Optional[str] = None,
        private_key: Optional[str] = None,
    ) -> dict:
        """
        Initialize ticket services.

        Modes:
        - both keys: issuance + redemption
        - public key only: redemption only
        - no key: disabled
        """
        _require_privacypass()

        services = {}

        if private_key and public_key:
            from .issuance.service import TicketIssuanceService

            services["issuance"] = TicketIssuanceService(
                storage=storage,
                public_key=public_key,
                private_key=private_key,
            )
            logger.info("Issuance service created")

        if public_key:
            from .redemption.service import TokenRedemptionService

            services["redemption"] = TokenRedemptionService(
                storage=storage,
                ticket_storage=ticket_storage,
                public_key=public_key,
            )
            logger.info("Redemption service created")

        if public_key:
            try:
                await storage.set("inference_ticket:public_key", public_key)
            except Exception as e:
                logger.warning(f"Failed to persist ticket public key: {str(e)}")

        return services
