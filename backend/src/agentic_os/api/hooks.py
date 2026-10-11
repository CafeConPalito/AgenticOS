"""Hooks of the agent CLIs (`hook.cmd` → curl). Answers 204 always for known tokens: the
CLI never waits on us, and a hook must not fail."""

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Path, Request, Response, status

from agentic_os.errors import ApiError

router = APIRouter()

EventName = Annotated[str, Path(pattern=r"^[A-Za-z]{1,40}$")]


@router.post("/r/{token}/hook/{event}", status_code=status.HTTP_204_NO_CONTENT)
async def receive_hook(token: str, event: EventName, request: Request) -> Response:
    manager = request.app.state.run_manager
    run_id = manager.tokens.resolve(token)
    if run_id is None:
        raise ApiError(401, "unknown_run_token", "unknown or expired run token")
    body = await request.body()
    try:
        payload = json.loads(body) if body.strip() else None
    except ValueError:
        payload = None
    await asyncio.to_thread(manager.on_hook, run_id, event, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
