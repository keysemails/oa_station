"""
OA-Station Server - Main FastAPI application.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api import ephemeral_keys_router, inference_tickets_router
from system.bootstrap import get_identity
from system.config import Settings
from system.initializer import StationInitializer

__version__ = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    """
    logger.info("Starting OpenAnonymity Station...")

    settings = Settings()
    app.state.settings = settings

    identity = get_identity()
    if not identity:
        logger.error("Identity not initialized - bootstrap_station() must be called first")
        raise RuntimeError("Identity must be initialized before server starts")

    initializer = StationInitializer(settings, identity=identity)
    await initializer.initialize()
    app.state.initializer = initializer

    logger.info("Station started successfully")
    yield

    logger.info("Shutting down Station...")
    if hasattr(app.state, "initializer"):
        await app.state.initializer.close()
        logger.info("Station initializer closed")

    logger.info("Station shut down gracefully")


app = FastAPI(
    title="Open Anonymity Station",
    description="Ephemeral API key issuance service",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS: defaults to allow all origins. Set CORS_ORIGINS env var to restrict (comma-separated).
app.add_middleware(
    CORSMiddleware,
    allow_origins=Settings().cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.include_router(ephemeral_keys_router, prefix="/api", tags=["ephemeral_keys"])
app.include_router(inference_tickets_router, prefix="/api/tickets", tags=["tickets"])

# Config UI is opt-in: set STATION_ENABLE_CONFIG_UI=true to enable
if os.getenv("STATION_ENABLE_CONFIG_UI", "false").lower() == "true":
    from api.config_ui import router as config_ui_router
    app.include_router(config_ui_router, tags=["config"])
