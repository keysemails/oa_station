"""
Private inference tickets issuance service.
"""

import time
from typing import List, Tuple

from loguru import logger

from schemas import TicketIssuanceRequest, TicketIssuanceResponse
from storage import BaseStorage
from ..ticket import _require_privacypass


class TicketIssuanceService:
    """Issue Privacy Pass tickets by signing blinded requests."""

    def __init__(self, storage: BaseStorage, public_key: str, private_key: str):
        if not public_key or not private_key:
            raise ValueError("Both public and private keys are required for issuance service")

        pp = _require_privacypass()

        self.storage = storage
        self.public_key = public_key
        self.private_key = private_key

        self.issuer = pp.IssuerServer()
        self.issuer.load_keypair(private_key)

    async def issue_tickets(self, blinded_requests: List[Tuple[int, str]]) -> TicketIssuanceResponse:
        """
        Issue tickets by signing blinded requests.

        Standalone station does not set ticket expiry. Validity is controlled by key rotation.
        """
        try:
            signed_responses = []
            for i, blinded_request in blinded_requests:
                try:
                    signed_response = self.issuer.issue_token_response(blinded_request)
                    signed_responses.append((i, signed_response))
                except Exception as e:
                    logger.error(f"Failed to sign blinded request {i}: {e}")
                    raise ValueError(f"Failed to sign token request {i}")

            # Non-expiring tickets in standalone mode. Rotation invalidates old tickets.
            expires_at = 0

            await self._log_issuance(len(signed_responses))
            logger.info(f"Signed {len(signed_responses)} ticket requests")

            return TicketIssuanceResponse(
                signed_responses=signed_responses,
                expires_at=expires_at,
                public_key=self.public_key,
            )

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Ticket signing error: {str(e)}")
            raise RuntimeError("Failed to sign tickets") from e

    async def issue_tokens(self, request: TicketIssuanceRequest) -> TicketIssuanceResponse:
        """Sign blinded token requests."""
        return await self.issue_tickets(request.blinded_requests)

    async def _log_issuance(self, count: int) -> None:
        """Track aggregate issuance counters."""
        try:
            await self.storage.incrby("inference_ticket:tokens_issued_total", count)

            today = int(time.time()) // 86400
            daily_key = f"inference_ticket:issued_daily:{today}"
            new_value = await self.storage.incrby(daily_key, count)
            if new_value == count:
                await self.storage.expire(daily_key, 86400 * 30)
        except Exception as e:
            logger.warning(f"Failed to update issuance counters: {str(e)}")

    def get_public_key_b64(self) -> str:
        """Get base64-encoded public key."""
        return self.public_key
