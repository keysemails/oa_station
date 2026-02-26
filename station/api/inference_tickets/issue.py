"""
Ticket issuance API.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from loguru import logger

from schemas import TicketIssuanceRequest, TicketIssuanceResponse
from inference_tickets import TicketIssuanceService


router = APIRouter(tags=["tickets"])


async def get_ticket_issuance_service(request: Request) -> TicketIssuanceService:
    """Get ticket issuance service from app state."""
    if not hasattr(request.app.state, "initializer"):
        raise HTTPException(
            status_code=503,
            detail="Station not properly initialized - missing initializer",
        )

    initializer = request.app.state.initializer
    service = initializer.get_ticket_issuance_service()

    if not service:
        raise HTTPException(
            status_code=503,
            detail=(
                "Ticket issuance not available "
                "(set STATION_TOKEN_PUBLIC_KEY and STATION_TOKEN_PRIVATE_KEY)"
            ),
        )

    return service


async def authenticate_ticket_request_bearer(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Authenticate issuance requests with startup-generated Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Use 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "", 1).strip()
    initializer = getattr(request.app.state, "initializer", None)
    expected = getattr(initializer, "ticket_request_bearer_token", None)

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ticket request bearer token is not initialized",
        )

    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/ticket_request", response_model=TicketIssuanceResponse)
@router.post("/issue", response_model=TicketIssuanceResponse, include_in_schema=False)
async def issue_tickets(
    request_data: TicketIssuanceRequest,
    issuance_service: Annotated[TicketIssuanceService, Depends(get_ticket_issuance_service)],
    _auth: Annotated[None, Depends(authenticate_ticket_request_bearer)],
):
    """
    Issue Privacy Pass tickets for blinded requests.

    Request format is alpha-register style:
    - ticket_request: request identifier
    - blinded_requests: list of (index, base64_blinded_request)

    This endpoint requires a startup-generated Bearer token and requires exactly 100 tickets per request.
    """
    try:
        response = await issuance_service.issue_tokens(request_data)
        logger.info(
            f"Issued {len(response.signed_responses)} ticket(s) for request '{request_data.ticket_request}'"
        )
        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Ticket issuance validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ticket issuance error: {str(e)}")
        raise HTTPException(status_code=500, detail="Ticket issuance failed")


@router.get("/issue/public-key")
async def get_public_key(
    issuance_service: Annotated[TicketIssuanceService, Depends(get_ticket_issuance_service)]
):
    """Get issuer public key for client-side blind request generation."""
    try:
        return {
            "public_key": issuance_service.get_public_key_b64(),
            "algorithm": "RSA-PSS",
            "issuer": "oa-station",
            "can_issue": True,
        }
    except Exception as e:
        logger.error(f"Failed to get public key: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve public key")
