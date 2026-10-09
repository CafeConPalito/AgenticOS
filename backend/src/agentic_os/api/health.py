from fastapi import APIRouter
from pydantic import BaseModel

from agentic_os import APP_NAME, __version__

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    name: str
    version: str


@router.get("/health")
def health() -> Health:
    return Health(status="ok", name=APP_NAME, version=__version__)
