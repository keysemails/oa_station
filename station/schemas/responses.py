"""
Response models for API endpoints.
"""

from typing import List, Tuple

from pydantic import BaseModel, Field


class TicketIssuanceResponse(BaseModel):
    """Response containing signed blinded token responses."""

    signed_responses: List[Tuple[int, str]] = Field(
        ..., description="List of (index, base64_signed_response) tuples"
    )
    expires_at: int = Field(..., description="Token expiration unix timestamp (0 means no expiry)")
    public_key: str = Field(..., description="Server public key for token verification")


class KeyRequestResponse(BaseModel):
    """Response containing the issued API key."""

    key: str = Field(..., description="The actual API key (only shown once)")
    key_hash: str = Field(..., description="Key hash identifier")
    tickets_consumed: int = Field(..., description="Number of inference tickets consumed")
    credit_limit: float = Field(..., description="USD spending limit")
    duration_minutes: int = Field(..., description="Duration in minutes")
    expires_at: str = Field(..., description="Expiration timestamp (ISO format)")
    expires_at_unix: int = Field(..., description="Expiration unix timestamp")
    station_id: str = Field(..., description="Station identifier that signed this response")
    station_signature: str = Field(
        ..., description="Ed25519 signature of '{station_id}|{key}|{expires_at_unix}'"
    )
