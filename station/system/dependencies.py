"""
Dependency injection for station architecture.
"""

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

from .config import Settings
from storage import BaseStorage

if TYPE_CHECKING:
    from identity import StationIdentity


async def get_storage(request: Request) -> BaseStorage:
    """Get storage instance from app state."""
    if not hasattr(request.app.state, "initializer"):
        raise RuntimeError("Station not properly initialized - missing initializer")

    initializer = request.app.state.initializer
    if not hasattr(initializer, "storage"):
        raise RuntimeError("Storage not initialized")

    return initializer.storage


async def get_station_identity(request: Request) -> "StationIdentity":
    """Get station identity from initializer."""
    if not hasattr(request.app.state, "initializer"):
        raise RuntimeError("Station not properly initialized - missing initializer")

    initializer = request.app.state.initializer
    if not hasattr(initializer, "identity") or not initializer.identity:
        raise RuntimeError("Station identity not initialized")

    return initializer.identity


def get_client_ip(request: Request, trusted_proxies: set | None = None) -> str:
    """
    Get client IP address with trusted proxy validation.

    When behind trusted proxies, walks X-Forwarded-For from the right,
    skipping known proxy IPs, and returns the first untrusted (client) IP.
    This prevents attackers from spoofing their IP via the leftmost entry.
    """
    direct_ip = request.client.host if request.client else ""

    if trusted_proxies and direct_ip in trusted_proxies:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # Walk from right to left: rightmost entries are added by infra
            # we control; stop at the first IP that isn't a trusted proxy.
            parts = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
            for ip in reversed(parts):
                if ip not in trusted_proxies:
                    return ip
            # All entries are trusted proxies — fall through to direct_ip

    return direct_ip


async def verify_request_key_ip(request: Request) -> None:
    """
    Verify client IP is allowed to access request_key endpoint.
    """
    settings: Settings = request.app.state.settings
    allowed_ips = settings.request_key_allowed_ips

    if not allowed_ips:
        return

    allowed_list = [ip.strip() for ip in allowed_ips.split(",") if ip.strip()]
    if not allowed_list:
        return

    trusted_proxies_str = getattr(settings, "trusted_proxies", None)
    trusted_proxies = None
    if trusted_proxies_str:
        trusted_proxies = {ip.strip() for ip in trusted_proxies_str.split(",") if ip.strip()}

    client_ip = get_client_ip(request, trusted_proxies)

    if client_ip not in allowed_list:
        raise HTTPException(status_code=403, detail="Access denied")
