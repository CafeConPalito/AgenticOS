from fastapi import APIRouter, Request

from agentic_os.services.clis import CliInfo

router = APIRouter(tags=["clis"])


@router.get("/clis")
def list_clis(request: Request, refresh: bool = False) -> list[CliInfo]:
    return request.app.state.cli_catalog.list(refresh=refresh)
