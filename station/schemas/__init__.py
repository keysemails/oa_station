"""
Shared schemas for the station.
"""

from .requests import KeyRequestRequest, TicketIssuanceRequest
from .responses import (
    KeyRequestResponse,
    TicketIssuanceResponse,
)

__all__ = [
    "KeyRequestRequest",
    "TicketIssuanceRequest",
    "TicketIssuanceResponse",
    "KeyRequestResponse",
]
