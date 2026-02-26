"""
Ephemeral Key Request Endpoint.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from auth.ticket_auth import TicketValidationResult, authenticate_inference_ticket
from identity import StationIdentity
from schemas.requests import KeyRequestRequest
from schemas.responses import KeyRequestResponse
from services.ephemeral_keys import EphemeralKeyManager
from storage.database.base import BaseStorage
from system.config import Settings
from system.dependencies import get_station_identity, get_storage, verify_request_key_ip


router = APIRouter()


@router.post("/request_key", response_model=KeyRequestResponse)
async def request_ephemeral_key(
    request: Request,
    _ip_check: Annotated[None, Depends(verify_request_key_ip)],
    storage: Annotated[BaseStorage, Depends(get_storage)],
    auth_result: Annotated[TicketValidationResult, Depends(authenticate_inference_ticket)],
    identity: Annotated[StationIdentity, Depends(get_station_identity)],
    request_data: KeyRequestRequest = KeyRequestRequest(),
) -> KeyRequestResponse:
    """
    Request an ephemeral API key using inference tickets.

    Ticket tiers:
    - 1 ticket => $2 credit, 60 minutes
    - 2 tickets => $3 credit, 60 minutes
    - 3 tickets => $4 credit, 60 minutes
    """
    key_created = False
    key_hash = None
    ephemeral_key_manager = None
    try:
        settings: Settings = request.app.state.settings

        if not settings.openrouter_management_key:
            raise HTTPException(
                status_code=503,
                detail="Ephemeral key service not available. Please contact administrator.",
            )

        tickets_consumed = auth_result.ticket_count
        tier_config = settings.get_tier_config_by_tickets(tickets_consumed)
        if not tier_config:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid ticket count: {tickets_consumed}. "
                    "Must provide 1, 2, or 3 tickets."
                ),
            )

        # Ticket tier decides credit/duration. Ignore user overrides.
        if request_data.credit_limit is not None or request_data.duration_limit is not None:
            logger.debug("Ignoring request body overrides for ticket-authenticated request")

        credit_limit = tier_config["credit_limit"]
        duration_minutes = tier_config["duration_minutes"]

        ephemeral_key_manager = EphemeralKeyManager(settings.openrouter_management_key)

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        tracking_name = (
            f"ephemeral-{tickets_consumed}tkts-"
            f"{secrets.token_hex(4)}-{int(datetime.now(timezone.utc).timestamp())}"
        )

        # Issue the API key last — after all validation passes — so that
        # failures before this point can safely roll back tickets without
        # leaving an orphaned key on OpenRouter.
        result = await ephemeral_key_manager.create_key(name=tracking_name, limit=credit_limit)

        # ── Point of no return ──
        # The OpenRouter key is now live. From here on, tickets must NOT be
        # rolled back regardless of subsequent failures, otherwise the same
        # tickets could be resubmitted to obtain a second key (double-spend).
        key_created = True

        api_key = result.get("key")
        key_data = result.get("data", {})
        key_hash = key_data.get("hash")

        if not api_key or not key_hash:
            raise HTTPException(
                status_code=500,
                detail="Failed to create ephemeral key: invalid response",
            )

        await storage.store_issued_key(
            key_hash=key_hash,
            key_name=tracking_name,
            expires_at=expires_at,
            credit_limit=credit_limit,
            duration_minutes=duration_minutes,
            tickets_consumed=tickets_consumed,
            auth_method="ticket",
        )

        station_id = settings.station_id
        expires_at_timestamp = int(expires_at.timestamp())
        message = f"{station_id}|{api_key}|{expires_at_timestamp}"
        station_signature = identity.sign_bytes(message.encode("utf-8")).hex()

        await auth_result.finalize()

        return KeyRequestResponse(
            key=api_key,
            key_hash=key_hash,
            tickets_consumed=tickets_consumed,
            credit_limit=credit_limit,
            duration_minutes=duration_minutes,
            expires_at=expires_at.isoformat(),
            expires_at_unix=expires_at_timestamp,
            station_id=station_id,
            station_signature=station_signature,
        )

    except HTTPException:
        if not key_created:
            await auth_result.rollback()
        elif key_hash and ephemeral_key_manager:
            await _revoke_orphaned_key(ephemeral_key_manager, key_hash)
        raise
    except Exception as e:
        if not key_created:
            await auth_result.rollback()
        elif key_hash and ephemeral_key_manager:
            await _revoke_orphaned_key(ephemeral_key_manager, key_hash)

        if isinstance(e, httpx.TimeoutException):
            error_msg = "Key issuance API timeout"
        elif isinstance(e, httpx.ConnectError):
            error_msg = "Failed to connect to key issuance API"
        elif isinstance(e, httpx.HTTPStatusError):
            error_msg = f"Key issuance API error: {e.response.status_code}"
        else:
            logger.error(f"Error creating ephemeral key: {str(e)}")
            error_msg = "Internal server error"

        raise HTTPException(
            status_code=502,
            detail=f"Failed to create ephemeral key: {error_msg}",
        )
    finally:
        if ephemeral_key_manager:
            await ephemeral_key_manager.close()


async def _revoke_orphaned_key(manager: EphemeralKeyManager, key_hash: str) -> None:
    """Best-effort revoke of an orphaned key on OpenRouter."""
    try:
        await manager.delete_key(key_hash)
        logger.warning(f"Revoked orphaned key {key_hash[:12]}... after post-creation failure")
    except Exception as revoke_err:
        logger.error(f"Failed to revoke orphaned key {key_hash[:12]}...: {revoke_err}")
