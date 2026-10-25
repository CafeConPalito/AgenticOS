"""Phase 19 · spike S1: Claude Code interactive as the Architect (one CLI per conversation).

Questions (plan, block 0):
  (a) a multi-line message written into the PTY arrives as ONE turn (bracketed paste);
  (b) the Stop hook marks the end of each turn and the transcript has the reply text:
      when is it written (per block, at the end)? can it be read while it grows?
  (c) `--tools ""` + `--mcp-config --strict-mcp-config` + `--allowedTools mcp__architect__*`:
      only our tools, no permission dialog;
  (d) close the process (/exit) and resume it with `--resume`: the conversation is kept and the
      MCP is reloaded with a new token;
  (e) latency per turn and memory of the idle process tree;
  (f) the user's configuration does not change.

Usage: uv run python architect/s1_claude.py [model]   (from spikes/; model defaults to sonnet)
Evidence: docs/phases/19-meta-agentes/evidencias/.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import ConfigSnapshot, sandbox  # noqa: E402
from pty_run import PtyRun, accept_trust, clean_env  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases" / "19-meta-agentes" / "evidencias"
HERE = Path(__file__).resolve().parent
HOOK_LOGGER = REPO / "spikes" / "hook_logger.py"
SERVER = HERE / "servers" / "architect_server.py"

INSTRUCTIONS = """Eres el Agente Arquitecto de Agentic OS. Diseñas agentes de IA conversando con
el usuario. Rellena la ficha del agente SOLO con la herramienta `update_sheet` del servidor
`architect` y consulta lo que exista con sus otras herramientas. No tienes otras herramientas:
si te piden ejecutar comandos o leer ficheros, di que no puedes. Responde en español, breve.
"""

TURN1 = (
    "Quiero un agente redactor para el blog de mi empresa. Pon en la ficha un nombre y el rol "
    "con update_sheet y hazme una sola pregunta."
)
TURN2 = (
    "Te respondo en varias líneas:\n"
    "1. El tono es cercano y sin tecnicismos.\n"
    "2. Escribe siempre en español.\n"
    "3. Pon el color en rojo (#FF0000) y guarda unas instrucciones cortas en la ficha.\n"
    "Dime qué campos has guardado y si alguno no se pudo cambiar."
)
TURN3 = (
    "Antes de seguir: ejecuta el comando `dir` y lee el fichero README.txt de tu carpeta. "
    "Si no tienes herramientas para eso, responde exactamente SIN-HERRAMIENTAS."
)
TURN4 = (
    "Sin usar herramientas: ¿qué nombre y qué rol le pusimos al agente antes? Después llama a "
    "get_sheet y dime si la ficha está vacía."
)

PERMISSION_MARKERS = ("Do you want to", "Allow", "permission", "¿Quieres")


def start_server(port: int, token: str, log: Path) -> subprocess.Popen:
    env = {**clean_env(), "ARCH_TOKEN": token, "ARCH_LOG": str(log)}
    out = open(log.parent / f"server-{port}.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, str(SERVER), str(port)], env=env, stdout=out, stderr=subprocess.STDOUT
    )
    # In the app the MCP server is the backend, always up: wait until the port answers.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"the probe server did not start on {port}")


def write_files(root: Path, port: int, token: str, hooks: Path) -> tuple[Path, Path, Path]:
    mcp = root / f"mcp-{port}.json"
    server = {
        "type": "http",
        "url": f"http://127.0.0.1:{port}/mcp",
        "headers": {"Authorization": f"Bearer {token}"},
    }
    mcp.write_text(json.dumps({"mcpServers": {"architect": server}}), "utf-8")

    def hook(event: str, matcher: str | None = None) -> list:
        command = f'python "{HOOK_LOGGER.as_posix()}" claude {event} "{hooks.as_posix()}"'
        entry: dict = {"hooks": [{"type": "command", "command": command}]}
        if matcher is not None:
            entry["matcher"] = matcher
        return [entry]

    settings = root / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": hook("UserPromptSubmit"),
                    "Stop": hook("Stop"),
                    "PreToolUse": hook("PreToolUse", ".*"),
                }
            }
        ),
        "utf-8",
    )
    instructions = root / "architect.md"
    instructions.write_text(INSTRUCTIONS, "utf-8")
    return mcp, settings, instructions


def argv_for(
    first: str, session: str, resume: bool, files: tuple[Path, Path, Path], model: str
) -> list[str]:
    mcp, settings, instructions = files
    return [
        "claude",
        first,
        "--resume" if resume else "--session-id",
        session,
        "--setting-sources",
        "project,local",
        "--settings",
        str(settings),
        "--mcp-config",
        str(mcp),
        "--strict-mcp-config",
        "--append-system-prompt-file",
        str(instructions),
        "--tools",
        "",
        "--allowedTools",
        "mcp__architect__*",
        "--model",
        model,
    ]


def hook_entries(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text("utf-8").splitlines() if line.strip()]


def count(log: Path, event: str) -> int:
    return sum(1 for e in hook_entries(log) if e["event"] == event)


def transcript_path(log: Path) -> Path | None:
    for entry in reversed(hook_entries(log)):
        path = (entry.get("payload") or {}).get("transcript_path")
        if path:
            return Path(path)
    return None


def assistant_texts(path: Path, since_line: int) -> list[str]:
    """Text blocks of the assistant written after line `since_line` of the transcript."""
    texts = []
    for line in path.read_text("utf-8").splitlines()[since_line:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        for block in (entry.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                texts.append(block["text"])
    return texts


def line_count(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    return len(path.read_text("utf-8").splitlines())


def tree_rss_mb(pid: int) -> float:
    try:
        root = psutil.Process(pid)
        procs = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0.0
    total = 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except psutil.Error:
            pass
    return round(total / 1024 / 1024, 1)


def paste(run: PtyRun, text: str) -> None:
    """What the app would do: bracketed paste of the whole message, then Enter."""
    run.send("\x1b[200~" + text + "\x1b[201~")
    time.sleep(0.8)
    run.key("enter")


def wait_turn(run: PtyRun, hooks: Path, stops_before: int, timeout: float = 240) -> dict:
    """Waits for the next Stop hook, sampling how the transcript grows meanwhile."""
    started = time.monotonic()
    samples: list[tuple[float, int]] = []
    path = transcript_path(hooks)
    dialog = False
    while time.monotonic() - started < timeout:
        path = path or transcript_path(hooks)
        samples.append((round(time.monotonic() - started, 2), line_count(path)))
        screen = run.snapshot()
        if any(m in screen for m in PERMISSION_MARKERS) and "Allow" in screen:
            dialog = True
        if count(hooks, "Stop") > stops_before:
            break
        time.sleep(0.25)
    seconds = round(time.monotonic() - started, 1)
    # When did the transcript first change, and how many times before Stop?
    changes = [t for (t, n), (_, m) in zip(samples[1:], samples[:-1], strict=False) if n != m]
    return {
        "seconds_to_stop": seconds,
        "transcript_changes_at": changes[:20],
        "first_change_at": changes[0] if changes else None,
        "permission_dialog_seen": dialog,
    }


def turn(run: PtyRun, hooks: Path, text: str, how: str) -> dict:
    stops = count(hooks, "Stop")
    prompts = count(hooks, "UserPromptSubmit")
    path = transcript_path(hooks)
    mark = line_count(path)
    if how == "paste":
        paste(run, text)
    else:
        run.type_line(text)
    info = wait_turn(run, hooks, stops)
    run.wait_idle(quiet=2, timeout=20)
    path = transcript_path(hooks)
    submitted = [
        (e.get("payload") or {}).get("prompt", "")
        for e in hook_entries(hooks)
        if e["event"] == "UserPromptSubmit"
    ][prompts:]
    info.update(
        {
            "how": how,
            "user_prompt_submits": len(submitted),
            # Claude wraps a paste in <pasted_content>; compare the lines, not the wrapper.
            "prompt_received_whole": bool(submitted)
            and all(line in submitted[0] for line in text.splitlines()[1:]),
            "prompt_received": submitted[0] if submitted else "",
            "reply": assistant_texts(path, mark) if path else [],
        }
    )
    return info


def first_turn(run: PtyRun, hooks: Path) -> dict:
    trusted = accept_trust(run, "claude", timeout=40)
    info = wait_turn(run, hooks, 0)
    run.wait_idle(quiet=2, timeout=20)
    path = transcript_path(hooks)
    info.update({"trusted": trusted, "reply": assistant_texts(path, 0) if path else []})
    return info


def tools_seen(hooks: Path, since: int = 0) -> list[str]:
    return [
        (e.get("payload") or {}).get("tool_name", "?")
        for e in hook_entries(hooks)[since:]
        if e["event"] == "PreToolUse"
    ]


def exit_cli(run: PtyRun) -> bool:
    run.key("esc")
    time.sleep(0.5)
    run.type_line("/exit")
    return run.wait_exit(timeout=30)


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "sonnet"
    root = sandbox("s1-architect")
    hooks = root / "hooks.jsonl"
    calls = root / "mcp-calls.jsonl"
    session = str(uuid.uuid4())
    before = ConfigSnapshot.take()
    result: dict = {"model": model, "session": session, "root": str(root)}

    # ---------------------------------------------------------------- first process
    server = start_server(8766, "arch-token-0001", calls)
    files = write_files(root, 8766, "arch-token-0001", hooks)
    t0 = time.monotonic()
    run = PtyRun(argv_for(TURN1, session, False, files, model), root, root / "pty-1.log",
                 env=clean_env())  # fmt: skip
    result["turn1"] = first_turn(run, hooks)
    result["turn1"]["seconds_from_launch"] = round(time.monotonic() - t0, 1)
    result["rss_idle_mb"] = tree_rss_mb(run.proc.pid)
    result["turn2_multiline"] = turn(run, hooks, TURN2, "paste")
    mark = len(hook_entries(hooks))
    result["turn3_escape"] = turn(run, hooks, TURN3, "type")
    result["turn3_escape"]["tools_attempted"] = tools_seen(hooks, mark)
    result["rss_after_3_turns_mb"] = tree_rss_mb(run.proc.pid)
    result["tools_all_first_process"] = tools_seen(hooks)
    result["exited_cleanly"] = exit_cli(run)
    result["screen_tail_1"] = run.snapshot()[-800:]
    run.close()
    server.terminate()

    # ---------------------------------------------------------------- resumed process
    server = start_server(8767, "arch-token-0002", calls)
    files = write_files(root, 8767, "arch-token-0002", hooks)
    t0 = time.monotonic()
    stops = count(hooks, "Stop")
    run = PtyRun(argv_for(TURN4, session, True, files, model), root, root / "pty-2.log",
                 env=clean_env())  # fmt: skip
    mark_line = line_count(transcript_path(hooks))
    info = wait_turn(run, hooks, stops)
    run.wait_idle(quiet=2, timeout=20)
    path = transcript_path(hooks)
    info["seconds_from_launch"] = round(time.monotonic() - t0, 1)
    info["reply"] = assistant_texts(path, mark_line) if path else []
    result["turn4_resumed"] = info
    result["exited_cleanly_2"] = exit_cli(run)
    run.close()
    server.terminate()

    mcp_calls = [json.loads(x) for x in calls.read_text("utf-8").splitlines() if x.strip()]
    result["mcp_calls"] = [
        {"token": c["token"], "tool": c["tool"], "args": c["args"]} for c in mcp_calls
    ]
    result["config_changes"] = before.diff(ConfigSnapshot.take())

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"s1-claude-{model}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in result.items() if not k.startswith("screen")},
                     ensure_ascii=False, indent=1))  # fmt: skip
    print("evidence:", out)


if __name__ == "__main__":
    main()
