"""
Agrupador de routers para la versión 1 de la API (/api/v1).
"""

from fastapi import APIRouter

from app.api.v1.documents import router as documents_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(documents_router)
