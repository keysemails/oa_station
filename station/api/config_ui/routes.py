"""
Config UI routes - serves configuration web interface and API endpoints.
"""

import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from system.config import TICKET_KEYS_FILE
from system.dependencies import get_client_ip

STATIC_DIR = Path(__file__).parent.parent.parent / "config_web_ui"
STATION_DIR = Path(__file__).parent.parent.parent
RESTART_MARKER = STATION_DIR / ".restart"


def _require_localhost(request: Request) -> None:
    """Restrict config UI access to localhost, with trusted proxy support."""
    settings = getattr(request.app.state, "settings", None)

    trusted_proxies = None
    if settings and getattr(settings, "trusted_proxies", None):
        trusted_proxies = {
            ip.strip() for ip in settings.trusted_proxies.split(",") if ip.strip()
        }

    client_ip = get_client_ip(request, trusted_proxies)
    if not client_ip or client_ip not in ("127.0.0.1", "::1"):
        raise HTTPException(
            status_code=403,
            detail="Config UI is only accessible from localhost",
        )


router = APIRouter(tags=["config"], dependencies=[Depends(_require_localhost)])


def _read_env_file() -> dict:
    """Parse active .env entries into a key-value dict."""
    env_path = STATION_DIR / ".env"
    if not env_path.exists():
        return {}

    values = {}
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            val = value.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1].replace('\\"', '"')
            values[key.strip()] = val
    return values


def _format_env_line(key: str, value: Any) -> str:
    """Render one env key/value line, commenting out empty values."""
    if value is None or str(value) == "":
        return f"# {key}="
    str_val = str(value)
    # Quote values that contain spaces or special characters
    if " " in str_val or "'" in str_val or '"' in str_val:
        # Escape existing double quotes and wrap in double quotes
        str_val = '"' + str_val.replace('"', '\\"') + '"'
    return f"{key}={str_val}"


def _write_env_file(values: dict) -> None:
    """Write .env file from template/current lines, preserving comments where possible."""
    env_path = STATION_DIR / ".env"
    template_path = STATION_DIR / "env.example"

    if template_path.exists():
        lines = template_path.read_text().splitlines()
    elif env_path.exists():
        lines = env_path.read_text().splitlines()
    else:
        lines = []

    output_lines = []
    written_keys = set()

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#"):
            # Strip leading '#' and whitespace to find commented-out env vars
            rest = stripped
            while rest and rest[0] in "#":
                rest = rest[1:]
            rest = rest.strip()
            if "=" in rest:
                key = rest.partition("=")[0].strip()
                if key.replace("_", "").isalnum() and key in values:
                    output_lines.append(_format_env_line(key, values[key]))
                    written_keys.add(key)
                    continue
            output_lines.append(line)
            continue

        if not stripped:
            output_lines.append(line)
            continue

        if "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in values:
                output_lines.append(_format_env_line(key, values[key]))
                written_keys.add(key)
            else:
                output_lines.append(line)
        else:
            output_lines.append(line)

    extra_keys = [k for k in values if k not in written_keys]
    if extra_keys:
        output_lines.append("")
        output_lines.append("# Additional settings")
        for key in extra_keys:
            output_lines.append(_format_env_line(key, values[key]))

    tmp_path = env_path.with_suffix(".tmp")
    tmp_path.write_text("\n".join(output_lines) + "\n")

    try:
        os.chmod(tmp_path, 0o600)
    except Exception:
        pass

    tmp_path.rename(env_path)


@router.get("/", include_in_schema=False)
async def root_redirect(request: Request):
    """Redirect root to config UI."""
    return RedirectResponse(url="/config")


@router.get("/config", response_class=HTMLResponse, include_in_schema=False)
async def serve_config_ui(request: Request):
    """Serve the configuration UI."""
    html_path = STATIC_DIR / "config.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Config UI not found")

    return HTMLResponse(content=html_path.read_text())


@router.get("/api/config")
async def get_config(request: Request, reveal: bool = False):
    """Get current .env configuration values."""

    env_values = _read_env_file()

    sensitive_keys = {
        "OPENROUTER_MANAGEMENT_KEY",
        "STATION_TOKEN_PRIVATE_KEY",
        "STATION_TOKEN_PUBLIC_KEY",
    }

    if not reveal:
        for key in sensitive_keys:
            if key in env_values and env_values[key]:
                val = env_values[key]
                if len(val) > 12:
                    env_values[key] = val[:8] + "..." + val[-4:]
                else:
                    env_values[key] = "***"

    return JSONResponse({
        "env": env_values,
        "env_file_exists": (STATION_DIR / ".env").exists(),
    })


@router.put("/api/config")
async def save_config(request: Request):
    """Save configuration to .env file and restart the server."""
    body = await request.json()
    env_values = body.get("env", {})

    # Sanitize keys and values to prevent injection
    sanitized = {}
    for key, value in env_values.items():
        # Keys must be valid env var names (alphanumeric + underscore)
        if not isinstance(key, str) or not key.replace("_", "").isalnum():
            raise HTTPException(status_code=400, detail=f"Invalid env key: {key}")
        # Values must not contain newlines (prevents injection of extra env vars)
        str_value = str(value) if value is not None else ""
        if "\n" in str_value or "\r" in str_value:
            raise HTTPException(status_code=400, detail=f"Env value for {key} contains newline characters")
        sanitized[key] = str_value

    _write_env_file(sanitized)

    RESTART_MARKER.touch()
    asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGINT)

    return JSONResponse({"status": "saved", "message": "Restarting..."})


@router.get("/api/config/runtime")
async def get_runtime_info(request: Request):
    """Get runtime-generated information (bearer token, identity, service status)."""
    initializer = getattr(request.app.state, "initializer", None)
    settings = getattr(request.app.state, "settings", None)
    identity = getattr(initializer, "identity", None) if initializer else None

    ticket_keys = {}
    if TICKET_KEYS_FILE.exists():
        try:
            ticket_keys = json.loads(TICKET_KEYS_FILE.read_text())
        except Exception:
            pass

    base_url = str(request.base_url).rstrip("/")

    runtime = {
        "base_url": base_url,
        "ticket_issuance_bearer_token": getattr(initializer, "ticket_request_bearer_token", None),
        "station_public_key": identity.public_key_hex if identity and identity.is_loaded else None,
        "station_id": settings.station_id if settings else None,
        "ticket_issuance_available": initializer.ticket_issuance_service is not None if initializer else False,
        "ticket_redemption_available": initializer.ticket_redemption_service is not None if initializer else False,
        "cleanup_worker_active": initializer.ephemeral_key_cleanup_worker is not None if initializer else False,
        "ticket_public_key": ticket_keys.get("public_key"),
    }

    if settings:
        runtime["tier_config"] = {}
        for n in [1, 2, 3]:
            tier = settings.get_tier_config_by_tickets(n)
            if tier:
                runtime["tier_config"][f"{n}_ticket{'s' if n > 1 else ''}"] = tier

    return JSONResponse(runtime)
