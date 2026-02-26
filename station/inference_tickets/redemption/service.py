"""
Private inference tickets redemption service.
"""

import time
from typing import List, Optional, Tuple

from loguru import logger

from storage import BaseStorage, TicketStorage
from ..ticket import TokenRedemptionResult, _require_privacypass


class TokenRedemptionService:
    """Redeem Privacy Pass tickets with double-spending prevention."""

    def __init__(
        self,
        storage: BaseStorage,
        ticket_storage: TicketStorage,
        public_key: str,
    ):
        pp = _require_privacypass()

        self.storage = storage
        self.ticket_storage = ticket_storage
        self.public_key = public_key
        self.pp = pp

        self.origin = pp.OriginServer()
        if public_key:
            self.origin.add_trusted_issuer(public_key)

    async def validate_and_spend(self, token: str) -> TokenRedemptionResult:
        """
        Atomic mark-as-spent then verify, rollback mark if verification fails.
        """
        nonce = None
        try:
            nonce = self.pp.extract_nonce(token)

            try:
                spent = not await self.ticket_storage.mark_nonce_spent(nonce)
            except Exception as e:
                logger.error(f"Database error marking nonce spent: {e}")
                return TokenRedemptionResult(valid=False, error="Storage error, please retry", nonce=nonce)

            if spent:
                return TokenRedemptionResult(valid=False, error="Ticket already spent", nonce=nonce)

            try:
                self.origin.redeem_token(token)
            except Exception as e:
                await self.ticket_storage.unmark_nonce_spent(nonce)
                logger.warning(f"Crypto verification failed, rolled back: {e}")
                return TokenRedemptionResult(valid=False, error="Invalid ticket", nonce=nonce)

            return TokenRedemptionResult(valid=True, nonce=nonce)

        except Exception as e:
            if nonce:
                await self.ticket_storage.unmark_nonce_spent(nonce)
            logger.warning(f"Ticket validation failed: {str(e)}")
            return TokenRedemptionResult(valid=False, error="Malformed ticket", nonce=nonce)

    async def validate_and_redeem_all(
        self, tokens: List[str]
    ) -> Tuple[bool, List[TokenRedemptionResult], Optional[int]]:
        """
        Validate and redeem multiple tokens sequentially with rollback on failure.

        If any token fails, all previously committed nonces are rolled back.
        Not truly atomic — a process crash mid-loop may leave nonces in spent state.
        """
        results: List[TokenRedemptionResult] = []
        committed_nonces: List[str] = []

        for i, token in enumerate(tokens):
            result = await self.validate_and_spend(token)
            results.append(result)

            if not result.valid:
                for committed_nonce in committed_nonces:
                    await self.ticket_storage.unmark_nonce_spent(committed_nonce)
                return (False, results, i)

            committed_nonces.append(result.nonce)

        return (True, results, None)

    async def finalize_redemption(self, tokens: List[str], nonces: List[str]) -> None:
        """Store redemption audit records and aggregate counters."""
        for token, nonce in zip(tokens, nonces):
            await self.ticket_storage.store_redeemed_ticket(
                nonce=nonce,
                ticket=token,
                metadata={"redeemed_at": int(time.time()), "service": "oa-station"},
            )
        await self._log_redemption(count=len(nonces))

    async def _log_redemption(self, count: int = 1) -> None:
        try:
            await self.storage.incrby("inference_ticket:tokens_redeemed_total", count)

            current_hour = int(time.time()) // 3600
            hourly_key = f"inference_ticket:redeemed_hourly:{current_hour}"
            new_value = await self.storage.incrby(hourly_key, count)
            if new_value == count:
                await self.storage.expire(hourly_key, 3600 * 24)

        except Exception as e:
            logger.warning(f"Failed to update redemption counters: {str(e)}")
