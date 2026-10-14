from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from agentic_os.services import agy_status
from agentic_os.services.clis import CliInfo
from agentic_os.services.trust import agy_settings

router = APIRouter(tags=["clis"])


@router.get("/clis")
def list_clis(request: Request, refresh: bool = False) -> list[CliInfo]:
    return request.app.state.cli_catalog.list(refresh=refresh)


class AgyQuotaState(BaseModel):
    available: bool  # agy has been run once: its settings file exists
    enabled: bool  # Agentic OS reads agy's quota (its status line is installed)
    taken: bool  # the person has a status line of their own: it is left alone
    running: bool  # an agy process is open: its settings cannot be changed now


class AgyQuotaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


def _state(request: Request) -> AgyQuotaState:
    settings = request.app.state.settings
    current = agy_status.state(settings.agy_settings_file or agy_settings())
    return AgyQuotaState(
        available=current.available,
        enabled=current.enabled,
        taken=current.taken,
        running=current.running,
    )


@router.get("/clis/agy/quota")
def get_agy_quota(request: Request) -> AgyQuotaState:
    """Whether agy's subscription quota is being read (opt-in, see `services/agy_status.py`)."""
    return _state(request)


@router.put("/clis/agy/quota")
def put_agy_quota(payload: AgyQuotaUpdate, request: Request) -> AgyQuotaState:
    settings = request.app.state.settings
    agy_status.set_enabled(
        settings.agy_settings_file or agy_settings(), settings.data_dir, payload.enabled
    )
    return _state(request)
