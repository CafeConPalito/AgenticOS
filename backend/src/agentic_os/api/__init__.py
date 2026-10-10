from fastapi import APIRouter

from agentic_os.api import agents, clis, health, projects, runs

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(projects.router)
api_router.include_router(clis.router)
api_router.include_router(runs.router)
