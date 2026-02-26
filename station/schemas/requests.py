"""
Request models for API endpoints.
"""

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class TicketIssuanceRequest(BaseModel):
    """Alpha-register style ticket issuance request."""

    ticket_request: str = Field(..., description="Ticket request identifier")
    blinded_requests: List[Tuple[int, str]] = Field(
        ..., description="List of (index, base64_blinded_request) tuples"
    )

    @field_validator("blinded_requests")
    def validate_blinded_requests(cls, value: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
        if len(value) != 100:
            raise ValueError("Exactly 100 blinded requests are required per ticket request")
        return value

    @field_validator("ticket_request")
    def validate_ticket_request(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("ticket_request must be a non-empty string")
        return value.strip()


class KeyRequestRequest(BaseModel):
    """
    Request for issuing a temporary API key.

    Ticket-authenticated requests ignore these optional overrides and use
    station tier config by ticket count.
    """

    credit_limit: Optional[float] = Field(default=None, description="Spending limit in USD")
    duration_limit: Optional[int] = Field(default=None, description="Duration in minutes")

    @field_validator("duration_limit")
    def validate_duration_limit(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value <= 0:
            raise ValueError("Duration limit must be positive")
        return value

    @field_validator("credit_limit")
    def validate_credit_limit(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value <= 0:
            raise ValueError("Credit limit must be positive")
        return value
