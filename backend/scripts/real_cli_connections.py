"""Manual check of phase 18 (plan, block 12): the REAL `claude` and `agy`, started by the app's own
adapters, use the tools of an external MCP server given through a connection.

Not a test: it uses the person's logged-in CLIs (a few cheap turns), in a throwaway data folder,
and it never touches their own CLI configuration (the script compares it before and after).

    uv run python scripts/real_cli_connections.py [claude] [agy]

For each CLI it checks that the agent calls a stdio server's tools (one of them reads a secret that
reached the server through the CLI's configuration), that the calls are recorded on the run, that
the secret is not in the run's log or files, and that the user's CLI configuration is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SERVER = ROOT / "tests" / "fixtures" / "mcp_servers" / "stdio_server.py"
SECRET = "real-cli-secret-7731"

from agentic_os.app import create_app  # noqa: E402
from agentic_os.config import Settings  # noqa: E402

HOME = Path.home()
WATCHED = [
    HOME / ".claude.json",
    HOME / ".claude" / "settings.json",
    HOME / ".gemini" / "config" / "mcp_config.json",
]


def snapshot() -> dict[str, str]:
    out = {}
    for path in WATCHED:
        out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "-"
    return out


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    wanted = [a for a in sys.argv[1:] if a in ("claude", "agy")] or ["claude", "agy"]
    data = Path(tempfile.mkdtemp(prefix="aos-real-"))
    port = free_port()
    settings = Settings(
        _env_file=None, data_dir=data / "data", port=port, check_sessions_at_startup=False
    )
    app = create_app(settings)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    )
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.2)
    http = httpx.Client(base_url=url, timeout=60)
    before = snapshot()
    failures: list[str] = []
    connection = http.post(
        "/api/connections",
        json={
            "name": "probe",
            "command": sys.executable,
            "args": [str(SERVER)],
            "env": {"PROBE_SECRET": "${secret:TOKEN}"},
            "secrets": {"TOKEN": SECRET},
            "level": {"scope": "general"},
        },
    ).json()[0]
    print("connection:", connection["name"], connection["id"])
    http.put("/api/settings/connections", json={"agy_grace": 8})
    for cli in wanted:
        folder = data / f"proyecto-{cli}"
        folder.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
        project = http.post(
            "/api/projects", json={"name": f"Real {cli}", "path": str(folder)}
        ).json()
        agent = http.post(
            "/api/agents",
            json={"name": f"Real {cli}", "cli": cli, "permission_mode": "autonomous"},
        ).json()
        prompt = (
            "Usa las herramientas del servidor MCP «probe»: llama a read_note con topic='a' y a "
            "show_env con name='PROBE_SECRET'. Después llama a complete_task del servidor "
            "agentic-os con un resumen breve que incluya lo que devolvió read_note."
        )
        run = http.post(
            "/api/runs",
            json={"agent_id": agent["id"], "project_id": project["id"], "prompt": prompt},
        )
        run.raise_for_status()
        run_id = run.json()["id"]
        print(f"[{cli}] run {run_id} launched")
        deadline = time.monotonic() + 300
        view: dict = {}
        while time.monotonic() < deadline:
            view = http.get(f"/api/runs/{run_id}/connections").json()
            done = http.get(f"/api/runs/{run_id}").json()["status"] in (
                "completed",
                "exited",
                "stopped",
                "failed",
            )
            if done:
                break
            if (
                len([c for c in view.get("calls", []) if c["ok"] is not None]) >= 2
                and time.monotonic() > deadline - 240
            ):
                time.sleep(20)  # let it finish its turn
                http.post(f"/api/runs/{run_id}/stop")
                time.sleep(10)
                break
            time.sleep(5)
        else:
            http.post(f"/api/runs/{run_id}/stop")
        view = http.get(f"/api/runs/{run_id}/connections").json()
        print(f"[{cli}] connections:", json.dumps(view["connections"], ensure_ascii=False))
        print(f"[{cli}] calls:", [(c["tool"], c["ok"], c["duration_ms"]) for c in view["calls"]])
        tools = {c["tool"] for c in view["calls"] if c["ok"]}
        if not {"read_note", "show_env"} <= tools:
            failures.append(
                f"{cli}: calls recorded {sorted(tools)} (wanted read_note and show_env)"
            )
        rows = {c["name"]: c for c in view["connections"]}
        if rows.get("probe", {}).get("status") != "connected":
            failures.append(f"{cli}: connection status {rows.get('probe', {}).get('status')}")
        log = (data / "data" / "runs" / f"{run_id}.log").read_text("utf-8", "replace")
        if SECRET in log:
            failures.append(f"{cli}: the secret is in the terminal log")
        for file in (data / "data" / "runs" / run_id).rglob("*"):
            if file.is_file() and SECRET in file.read_text("utf-8", "replace"):
                failures.append(f"{cli}: the secret is in {file.name}")
        leftover = folder / ".agents" / "plugins" / "agentic-os"
        if cli == "agy" and leftover.exists():
            failures.append("agy: the workspace plugin was not removed")
    after = snapshot()
    if after != before:
        failures.append(
            "the user's CLI configuration changed: "
            + str([p for p in before if before[p] != after[p]])
        )
    server.should_exit = True
    print("\nFAILURES:" if failures else "\nOK: all checks passed")
    for failure in failures:
        print(" -", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
