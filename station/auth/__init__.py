"""
Authentication module exports.
"""

from .ticket_auth import authenticate_inference_ticket, authenticate_with_ticket, TicketValidationResult

__all__ = [
    "authenticate_inference_ticket",
    "authenticate_with_ticket",
    "TicketValidationResult",
]
