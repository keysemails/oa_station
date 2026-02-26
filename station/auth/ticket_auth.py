"""
Private Inference Ticket authentication module.
"""

from dataclasses import dataclass
from typing import Annotated, Any, Dict, List, Optional

from fastapi import Header, HTTPException, Request, status
from loguru import logger


class TicketErrorCode:
    """Error codes for ticket validation."""

    ALREADY_SPENT = "TICKET_ALREADY_SPENT"
    INVALID = "TICKET_INVALID"
    EXPIRED = "TICKET_EXPIRED"
    MALFORMED = "TICKET_MALFORMED"
    NO_TICKETS = "NO_TICKETS_PROVIDED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def _map_error_to_code(error_message: str) -> str:
    """Map an error message to a machine-readable error code."""
    error_lower = error_message.lower() if error_message else ""
    if "already spent" in error_lower or "double-spending" in error_lower:
        return TicketErrorCode.ALREADY_SPENT
    if "expired" in error_lower:
        return TicketErrorCode.EXPIRED
    if "malformed" in error_lower or "format" in error_lower:
        return TicketErrorCode.MALFORMED
    if "invalid" in error_lower:
        return TicketErrorCode.INVALID
    return TicketErrorCode.INVALID


def _build_ticket_error(
    error_code: str,
    message: str,
    tickets_submitted: int = 0,
    failed_index: Optional[int] = None,
    failed_preview: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build structured ticket validation error response."""
    error: Dict[str, Any] = {
        "error_code": error_code,
        "message": message,
        "tickets_submitted": tickets_submitted,
        "tickets_consumed": 0,
    }

    if failed_index is not None:
        error["failed_ticket"] = {
            "index": failed_index,
            "preview": failed_preview or "unknown",
            "reason": reason or error_code,
        }

    return error


@dataclass
class TicketValidationResult:
    """Result of validating one or more inference tickets."""

    ticket_count: int
    nonces: List[str]
    tokens: Optional[List[str]] = None
    ticket_storage: Optional[Any] = None
    redemption_service: Optional[Any] = None

    async def rollback(self) -> None:
        """Rollback ticket redemption by unmarking nonces."""
        if self.ticket_storage and self.nonces:
            rolled_back = 0
            for nonce in self.nonces:
                try:
                    await self.ticket_storage.unmark_nonce_spent(nonce)
                    rolled_back += 1
                except Exception as e:
                    logger.error(f"Failed to rollback nonce {nonce[:8]}...: {e}")
            logger.info(f"Rolled back {rolled_back}/{len(self.nonces)} ticket(s)")

    async def finalize(self) -> None:
        """Persist redemption audit after successful operation."""
        if self.redemption_service and self.tokens and self.nonces:
            await self.redemption_service.finalize_redemption(self.tokens, self.nonces)


async def authenticate_with_ticket(request: Request, authorization: str) -> TicketValidationResult:
    """
    Authenticate using Privacy Pass inference tickets.

    Supported formats:
    - "InferenceTicket token={token}"
    - "InferenceTicket tokens={token1},{token2},{token3}"
    """
    if not (
        authorization.startswith("InferenceTicket token=")
        or authorization.startswith("InferenceTicket tokens=")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_build_ticket_error(
                error_code=TicketErrorCode.MALFORMED,
                message=(
                    "Invalid authorization format. Expected: "
                    "'InferenceTicket token={token}' or "
                    "'InferenceTicket tokens={token1},{token2}'"
                ),
            ),
            headers={"WWW-Authenticate": "InferenceTicket"},
        )

    try:
        if authorization.startswith("InferenceTicket tokens="):
            tokens_str = authorization.removeprefix("InferenceTicket tokens=").strip()
            tickets = [t.strip() for t in tokens_str.split(",") if t.strip()]
        else:
            token = authorization.removeprefix("InferenceTicket token=").strip()
            tickets = [token] if token else []

        if not tickets:
            raise ValueError("No tokens provided")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_build_ticket_error(
                error_code=TicketErrorCode.NO_TICKETS
                if "No tokens" in str(e)
                else TicketErrorCode.MALFORMED,
                message=f"Invalid Privacy Pass header format: {str(e)}",
            ),
            headers={"WWW-Authenticate": "InferenceTicket"},
        )

    if not hasattr(request.app.state, "initializer"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_build_ticket_error(
                error_code=TicketErrorCode.SERVICE_UNAVAILABLE,
                message="Authentication service not available",
                tickets_submitted=len(tickets),
            ),
        )

    initializer = request.app.state.initializer
    redemption_service = initializer.ticket_redemption_service
    if not redemption_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_build_ticket_error(
                error_code=TicketErrorCode.SERVICE_UNAVAILABLE,
                message="Ticket authentication not available (service not configured)",
                tickets_submitted=len(tickets),
            ),
        )

    try:
        success, results, failed_index = await redemption_service.validate_and_redeem_all(tickets)

        if not success:
            failed_result = results[failed_index]
            error_reason = failed_result.error or "Invalid ticket"
            error_code = _map_error_to_code(error_reason)
            failed_ticket_preview = (
                tickets[failed_index][:4] + "..."
                if len(tickets[failed_index]) > 4
                else tickets[failed_index]
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_build_ticket_error(
                    error_code=error_code,
                    message="Ticket validation failed. No tickets were consumed.",
                    tickets_submitted=len(tickets),
                    failed_index=failed_index,
                    failed_preview=failed_ticket_preview,
                    reason=error_reason,
                ),
                headers={"WWW-Authenticate": "InferenceTicket"},
            )

        validated_nonces = [r.nonce for r in results]
        return TicketValidationResult(
            ticket_count=len(validated_nonces),
            nonces=validated_nonces,
            tokens=tickets,
            ticket_storage=redemption_service.ticket_storage,
            redemption_service=redemption_service,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during ticket redemption: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_build_ticket_error(
                error_code=TicketErrorCode.INTERNAL_ERROR,
                message="Ticket authentication failed unexpectedly",
                tickets_submitted=len(tickets),
            ),
        )


async def authenticate_inference_ticket(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> TicketValidationResult:
    """
    FastAPI dependency for authenticating requests with inference tickets.

    Accepted formats:
    - "InferenceTicket token={token}"
    - "InferenceTicket tokens={token1},{token2},{token3}"
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing authorization header. Use "
                "'InferenceTicket token={token}' or "
                "'InferenceTicket tokens={t1},{t2},{t3}'"
            ),
            headers={"WWW-Authenticate": "InferenceTicket"},
        )

    return await authenticate_with_ticket(request, authorization)
