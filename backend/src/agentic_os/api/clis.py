import uuid

from fastapi import APIRouter, Request, WebSocket, status
from pydantic import BaseModel, ConfigDict

from agentic_os.api.terminal import serve_terminal
from agentic_os.models import Cli
from agentic_os.services import agy_status
from agentic_os.services.clis import CliInfo
from agentic_os.services.trust import agy_settings

router = APIRouter(tags=["clis"])


@router.get("/clis")
def list_clis(request: Request, refresh: bool = False) -> list[CliInfo]:
    return request.app.state.cli_catalog.list(refresh=refresh)


# ---------------------------------------------------------------------- install (phase 23)
@router.post("/clis/{cli}/install", status_code=status.HTTP_202_ACCEPTED)
def install_cli(cli: Cli, request: Request) -> None:
    """Runs the CLI's official installer in a terminal (see `/clis/{cli}/install/terminal`).
    When it ends the CLIs are probed again, so the new one shows as installed."""
    request.app.state.installs.start(cli)


@router.websocket("/clis/{cli}/install/terminal")
async def install_terminal(websocket: WebSocket, cli: str, client_id: str = "") -> None:
    await websocket.accept()
    session = websocket.app.state.installs.get(cli)
    if session is not None and not session.alive:  # it ended: what it printed, and how
        snapshot, _ = session.attach("ended")
        session.detach("ended")
        await websocket.send_json({"type": "snapshot", "data": snapshot})
    if session is None or not session.alive:
        code = session.exit_code if session is not None else None
        await websocket.send_json({"type": "exit", "code": code, "status": "exited"})
        await websocket.close()
        return
    await serve_terminal(websocket, session, client_id or uuid.uuid4().hex)


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
