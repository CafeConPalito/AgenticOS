from fastapi import APIRouter

from agentic_os.api import (
    accounts,
    agents,
    changes,
    clis,
    git,
    health,
    home,
    inbox,
    maintenance,
    memory,
    pipelines,
    projects,
    repos,
    runs,
    settings,
    tasks,
    teams,
    usage,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(teams.router)
api_router.include_router(accounts.router)
api_router.include_router(projects.router)
api_router.include_router(repos.router)
api_router.include_router(git.router)
api_router.include_router(memory.router)
api_router.include_router(pipelines.router)
api_router.include_router(clis.router)
api_router.include_router(runs.router)
api_router.include_router(tasks.router)
api_router.include_router(changes.router)
api_router.include_router(inbox.router)
api_router.include_router(home.router)
api_router.include_router(usage.router)
api_router.include_router(settings.router)
api_router.include_router(maintenance.router)
