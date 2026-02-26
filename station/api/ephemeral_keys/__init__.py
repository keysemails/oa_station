"""
Ephemeral Keys API - Ephemeral API key endpoints.
"""

from fastapi import APIRouter
from .request_key import router as request_key_router

# Combine routers
router = APIRouter()
router.include_router(request_key_router)

__all__ = ["router"]
