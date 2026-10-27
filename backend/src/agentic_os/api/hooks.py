"""Hooks of the agent CLIs (`hook.cmd` → curl). Answers 204 always for known tokens: the
CLI never waits on us, and a hook must not fail. The one exception is the Architect's agy
guard (phase 19), which gets its decision as JSON."""

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Path, Request, Response, status
from fastapi.responses import JSONResponse

from agentic_os.errors import ApiError

router = APIRouter()


def _append(path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as file:
        file.write(line + "\n")


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
    log_file = request.app.state.settings.hook_log
    if log_file is not None:
        record = {"run_id": run_id, "event": event, "payload": payload}
        line = json.dumps(record, ensure_ascii=False)
        await asyncio.to_thread(_append, log_file, line)
    await asyncio.to_thread(manager.on_hook, run_id, event, payload)
    # The Architect's agy prints what its PreToolUse guard is told (phase 19).
    decision = manager.hook_decision(run_id, event, payload)
    if decision is not None:
        return JSONResponse(decision)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
