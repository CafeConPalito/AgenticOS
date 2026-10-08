from fastapi import APIRouter

from agentic_os.api import health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
