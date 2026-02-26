"""
API layer for the station.
"""

from .ephemeral_keys import router as ephemeral_keys_router
from .inference_tickets import router as inference_tickets_router

__all__ = [
    "ephemeral_keys_router",
    "inference_tickets_router",
]


def get_config_ui_router():
    """Lazy import for config UI router (only needed when enabled)."""
    from .config_ui import router as config_ui_router
    return config_ui_router
