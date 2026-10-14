"""agy's subscription quota (phase 10, evidence S2, ADR 0014).

agy reports its quota (`quota.<bucket>`, plus `email` and `plan_tier`) in the JSON it pipes to the
script of its **status line**, and it only reads that script from `statusLine` in the global
`~/.gemini/antigravity-cli/settings.json`: neither a workspace file nor a plugin works. So showing
agy's quota needs a line in a file of the person's. Therefore it is:

- **opt-in**: the person turns it on in «CLIs y cuentas», and can turn it off again;
- **harmless outside the app**: the script does nothing unless the session was started by Agentic
  OS (it gets `AGENTIC_OS_STATUS_URL` in its environment), prints nothing, and
  `stack_with_default` keeps agy's own line on screen;
- **never overwriting**: if the person already has a status line of their own, it is left alone;
- **never concurrent with agy**: agy rewrites that file while it runs, so it is only edited when
  no agy process is open (the same rule the folder-trust cleanup follows).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from agentic_os.errors import ApiError
from agentic_os.services.hooks import short_path
from agentic_os.services.trust import _load, _write_json, process_running

ENV_URL = "AGENTIC_OS_STATUS_URL"
# 8.3-compatible: the short path agy runs it by (no spaces) keeps this name, so it is recognised.
SCRIPT = "agyquota.cmd" if sys.platform == "win32" else "agyquota.sh"


@dataclass(frozen=True)
class AgyStatusState:
    available: bool  # agy has a settings file to edit (it was run at least once)
    enabled: bool  # our status line is installed
    taken: bool  # the person has a status line of their own
    running: bool  # an agy process is open: its settings must not be touched now
    settings_file: str


def script_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / "hooks" / SCRIPT


def write_script(data_dir: Path | str) -> str:
    """Writes the status line script and returns the command agy runs (no quotes, no spaces)."""
    script = script_path(data_dir)
    script.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        script.write_text(
            "@echo off\r\n"
            f'if "%{ENV_URL}%"=="" exit /b 0\r\n'
            'curl.exe -s -m 3 -o NUL -X POST -H "Content-Type: application/json" '
            f'--data-binary @- "%{ENV_URL}%"\r\n'
            "exit /b 0\r\n",
            "ascii",
        )
    else:
        script.write_text(
            f'#!/bin/sh\n[ -z "${ENV_URL}" ] && exit 0\n'
            "curl -s -m 3 -o /dev/null -X POST -H 'Content-Type: application/json' "
            f'--data-binary @- "${ENV_URL}"\nexit 0\n',
            "ascii",
        )
        script.chmod(0o755)
    return short_path(script)


def _is_ours(block: object) -> bool:
    command = block.get("command") if isinstance(block, dict) else None
    return isinstance(command, str) and Path(command).name.lower() == SCRIPT.lower()


def state(settings_file: Path, running: bool | None = None) -> AgyStatusState:
    data = _load(settings_file)
    block = data.get("statusLine") if data else None
    ours = _is_ours(block)
    return AgyStatusState(
        available=data is not None,
        enabled=ours,
        taken=block is not None and not ours,
        running=process_running("agy.exe") if running is None else running,
        settings_file=str(settings_file),
    )


def set_enabled(settings_file: Path, data_dir: Path | str, enabled: bool) -> AgyStatusState:
    """Turns our status line on or off in agy's settings, if it is safe to."""
    current = state(settings_file)
    if not current.available:
        raise ApiError(409, "agy_not_set_up", "agy has no settings file yet: open agy once")
    if current.running:
        raise ApiError(409, "agy_running", "close agy before changing its settings")
    if enabled == current.enabled:
        return current
    data = _load(settings_file) or {}
    if enabled:
        if current.taken:
            raise ApiError(409, "status_line_taken", "agy already has a status line of its own")
        data["statusLine"] = {
            "type": "command",
            "command": write_script(data_dir),
            # Keeps agy's own line on screen: our script prints nothing.
            "stack_with_default": True,
        }
    else:
        data.pop("statusLine", None)
    _write_json(settings_file, data)
    return state(settings_file, running=False)


def environment(base_url: str, token: str) -> dict[str, str]:
    """What an agy run gets so that the script (if installed) reports to this run."""
    return {ENV_URL: f"{base_url}/r/{token}/hook/StatusLine"}
