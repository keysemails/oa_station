"""
Configuration management for the station server.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field


class Settings(BaseSettings):
    """
    Application settings with environment variable support.

    Fields use STATION_ prefix by default. Fields that need non-prefixed env var
    names use AliasChoices to support both prefixed and non-prefixed variants.
    """

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "env_prefix": "STATION_",
    }

    # Application
    app_name: str = "OpenAnonymity-station"
    debug: bool = False

    # Server settings
    host: str = "0.0.0.0"
    port: int = 18888
    workers: int = 1

    # Storage settings
    storage_type: str = Field(
        default="sqlite",
        validation_alias=AliasChoices("STORAGE_TYPE", "STATION_STORAGE_TYPE"),
    )
    database_file: str = Field(
        default="station.db",
        validation_alias=AliasChoices("DATABASE_FILE", "STATION_DATABASE_FILE"),
    )

    # Logging settings
    log_level: str = "INFO"

    # Station identity for response signing
    identity_file: str = "identity.json"
    station_id: str = "station-self-hosted"

    # Ephemeral key management
    openrouter_management_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_MANAGEMENT_KEY", "STATION_OPENROUTER_MANAGEMENT_KEY"),
    )

    # Inference ticket configuration
    token_public_key: Optional[str] = None
    token_private_key: Optional[str] = None

    # Endpoint security
    request_key_allowed_ips: Optional[str] = None
    trusted_proxies: Optional[str] = None

    # CORS
    cors_origins: str = Field(
        default="*",
        validation_alias=AliasChoices("CORS_ORIGINS", "STATION_CORS_ORIGINS"),
    )

    # Config UI
    enable_config_ui: bool = False

    def get_tier_config_by_tickets(self, ticket_count: int) -> Optional[Dict[str, Any]]:
        """
        Tier configuration based on number of inference tickets consumed.
        """
        tier_configs = {
            1: {"credit_limit": 2.0, "duration_minutes": 60},
            2: {"credit_limit": 3.0, "duration_minutes": 60},
            3: {"credit_limit": 4.0, "duration_minutes": 60},
        }
        return tier_configs.get(ticket_count)


TICKET_KEYS_FILE = Path(__file__).parent.parent / "ticket_keys.json"
