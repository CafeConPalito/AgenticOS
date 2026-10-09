"""P7 (session id / resume), P9 (hooks) and P10 (native subagents) for both CLIs, headless.

Usage: uv run python scenarios/sessions_hooks.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import config_guard, evidence, sandbox  # noqa: E402
from pty_run import clean_env  # noqa: E402
from recorder import Recorder  # noqa: E402

SPIKES = Path(__file__).resolve().parent.parent
LOGGER = SPIKES / "hook_logger.py"
PY = sys.executable
SUBAGENT_PROMPT = (
    "Lanza un subagente (con tu herramienta para delegar en subagentes) que liste los archivos "
    "de esta carpeta. Después responde con el número de archivos que encontró."
)


def run(argv: list[str], cwd: Path) -> dict:
    proc = subprocess.run(
        argv,
        cwd=cwd,
        env=clean_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    try:
        out = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        out = {"_raw": proc.stdout[-500:]}
    out["_stream"] = lines
    out["_stderr"] = proc.stderr.strip()[:300]
    return out


def hook_cmd(cli: str, event: str, log: Path) -> str:
    if cli == "agy":
        # agy runs hooks through cmd.exe and mangles quoted paths: use unquoted paths
        # (none of these contain spaces).
        return f"{PY} {LOGGER} {cli} {event} {log}"
    return f'"{PY}" "{LOGGER}" {cli} {event} "{log}"'


def events(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text("utf-8").splitlines() if line]


# --------------------------------------------------------------------------------- Claude
def claude(rec: Recorder) -> None:
    base = [
        "claude",
        "--model",
        "haiku",
        "--setting-sources",
        "project,local",
        "--strict-mcp-config",
    ]
    cwd = sandbox("claude-sessions")
    sid = str(uuid.uuid4())
    first = run(
        [
            *base,
            "--output-format",
            "json",
            "--session-id",
            sid,
            "-p",
            "Recuerda la palabra secreta MANZANA. Responde solo OK.",
        ],
        cwd,
    )
    second = run(
        [
            *base,
            "--output-format",
            "json",
            "--resume",
            sid,
            "-p",
            "¿Cuál era la palabra secreta? Responde solo la palabra.",
        ],
        cwd,
    )
    rec.step(
        "Claude P7: --session-id fijado y --resume",
        first.get("session_id") == sid and "MANZANA" in (second.get("result") or "").upper(),
        screen=False,
    )
    rec.note(
        f"session_id devuelto: {first.get('session_id')} (pedido {sid}) · "
        f"tras --resume: {second.get('result')!r} · session_id: {second.get('session_id')}"
    )

    log = evidence("p9-claude-hooks.jsonl")
    log.unlink(missing_ok=True)
    hooks = {
        name: [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": hook_cmd("claude", name, log)}],
            }
        ]
        for name in ("PreToolUse", "PostToolUse")
    }
    for name in (
        "SessionStart",
        "Stop",
        "SubagentStart",
        "SubagentStop",
        "Notification",
        "UserPromptSubmit",
        "SessionEnd",
    ):
        hooks[name] = [{"hooks": [{"type": "command", "command": hook_cmd("claude", name, log)}]}]
    settings = cwd.parent / f"{cwd.name}.settings.json"
    settings.write_text(json.dumps({"hooks": hooks}, indent=1), "utf-8")
    cwd2 = sandbox("claude-hooks")
    (cwd2 / "a.txt").write_text("a", "utf-8")
    out = run(
        [
            *base,
            "--settings",
            str(settings),
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "stream-json",
            "--verbose",
            "-p",
            SUBAGENT_PROMPT,
        ],
        cwd2,
    )
    evs = events(log)
    names = [e["event"] for e in evs]
    tools = [
        e["payload"].get("tool_name") for e in evs if e["event"] == "PreToolUse" and e["payload"]
    ]
    sub_msgs = [
        m
        for m in (json.loads(x) for x in out["_stream"] if x.startswith("{"))
        if m.get("parent_tool_use_id")
    ]
    rec.step(
        "Claude P9: hooks por sesión con --settings", bool(evs) and "Stop" in names, screen=False
    )
    rec.note(f"Eventos recibidos (en orden): {names}")
    rec.note(f"Herramientas en PreToolUse: {tools}")
    rec.step(
        "Claude P10: subagente detectado",
        any(t in ("Task", "Agent") for t in tools) or "SubagentStart" in names,
        screen=False,
    )
    rec.note(
        f"Mensajes con parent_tool_use_id en stream-json: {len(sub_msgs)} · "
        f"respuesta: {out.get('result')!r}"
    )
    start = next((e for e in evs if e["event"] == "SessionStart"), None)
    if start:
        rec.note(
            "Payload SessionStart: ```"
            + json.dumps(start["payload"], ensure_ascii=False)[:400]
            + "```"
        )


# ---------------------------------------------------------------------------- Antigravity
def agy(rec: Recorder) -> None:
    base = ["agy", "--model", "gemini-3.8-flash-low", "--output-format", "json"]
    cwd = sandbox("agy-sessions")
    first = run([*base, "-p", "Recuerda la palabra secreta MANZANA. Responde solo OK."], cwd)
    conv = first.get("conversation_id")
    second = run(
        [
            *base,
            "--conversation",
            str(conv),
            "-p",
            "¿Cuál era la palabra secreta? Responde solo la palabra.",
        ],
        cwd,
    )
    rec.step(
        "agy P7: conversation_id y --conversation",
        bool(conv) and "MANZANA" in (second.get("response") or "").upper(),
        screen=False,
    )
    rec.note(
        f"conversation_id: {conv} · tras --conversation: {second.get('response')!r} · "
        f"id: {second.get('conversation_id')}"
    )

    cwd2 = sandbox("agy-hooks")
    (cwd2 / "a.txt").write_text("a", "utf-8")
    log = evidence("p9-agy-hooks.jsonl")
    log.unlink(missing_ok=True)
    plugin = cwd2 / ".agents" / "plugins" / "agentic-os"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps({"name": "agentic-os"}), "utf-8")
    hooks = {
        "agentic-os": {
            "PreToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [{"type": "command", "command": hook_cmd("agy", "PreToolUse", log)}],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [{"type": "command", "command": hook_cmd("agy", "PostToolUse", log)}],
                }
            ],
            "PreInvocation": [
                {"type": "command", "command": hook_cmd("agy", "PreInvocation", log)}
            ],
            "PostInvocation": [
                {"type": "command", "command": hook_cmd("agy", "PostInvocation", log)}
            ],
            "Stop": [{"type": "command", "command": hook_cmd("agy", "Stop", log)}],
        }
    }
    (plugin / "hooks.json").write_text(json.dumps(hooks, indent=1), "utf-8")
    out = run(
        [
            "agy",
            "--model",
            "gemini-3.8-flash-low",
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
            "-p",
            SUBAGENT_PROMPT,
        ],
        cwd2,
    )
    evs = events(log)
    names = [e["event"] for e in evs]
    rec.step(
        "agy P9: hooks por ejecución con un plugin de workspace", "Stop" in names, screen=False
    )
    rec.note(f"Eventos recibidos (en orden): {names}")
    tool_names = sorted(
        {
            str(
                (e["payload"] or {}).get("tool_name")
                or (e["payload"] or {}).get("toolName")
                or (e["payload"] or {}).get("tool", "")
            )
            for e in evs
            if e["event"] == "PreToolUse"
        }
    )
    rec.note(f"Herramientas en PreToolUse: {tool_names}")
    steps = [json.loads(x) for x in out["_stream"] if x.startswith("{")]
    kinds = sorted({(s.get("step_update") or {}).get("step_type", "") for s in steps} - {""})
    rec.step(
        "agy P10: subagente detectado",
        any("subagent" in str(t).lower() or "agent" in str(t).lower() for t in tool_names + kinds),
        screen=False,
    )
    rec.note(
        f"Tipos de paso en stream-json: {kinds} · respuesta: "
        f"{(steps[-1].get('result') or {}).get('response') if steps else None!r}"
    )
    if evs:
        rec.note(
            "Payload del primer evento: ```"
            + json.dumps(evs[0]["payload"], ensure_ascii=False)[:500]
            + "```"
        )


def main() -> None:
    rec = Recorder("Sesiones (P7), hooks (P9) y subagentes (P10)", evidence("p7-p9-p10.md"))
    try:
        with config_guard("sessions-hooks") as changes:
            claude(rec)
            agy(rec)
        rec.note(f"Configuración global: {changes or 'SIN CAMBIOS'}")
    finally:
        rec.save()


if __name__ == "__main__":
    main()
