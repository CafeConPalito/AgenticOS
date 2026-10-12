from fastapi import APIRouter

from agentic_os.api import (
    agents,
    clis,
    health,
    inbox,
    memory,
    pipelines,
    projects,
    runs,
    tasks,
    usage,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(projects.router)
api_router.include_router(memory.router)
api_router.include_router(pipelines.router)
api_router.include_router(clis.router)
api_router.include_router(runs.router)
api_router.include_router(tasks.router)
api_router.include_router(inbox.router)
api_router.include_router(usage.router)
