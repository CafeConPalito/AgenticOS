"""A fake agent CLI that imitates the parts of the Claude Code / agy TUIs Agentic OS relies on.

Behaviour (keys are read raw, like the real TUIs):
- Folder-trust dialog: "No, exit" preselected; Down + Enter accepts, Enter alone exits(1).
- Answers the initial prompt and every typed line with "● RESPUESTA: <text>".
- Typing "LARGO" starts a long turn (footer "esc to interrupt", numbers every 0.1 s);
  Esc interrupts it with "Interrupted · What should Claude do instead?".
- "/exit" exits with code 0, unless --ignore-exit (then it also ignores Ctrl+C).
- Ctrl+C works like agy: the first one shows "press ctrl+c again to exit" after a short
  delay (presses in between are lost); a second Ctrl+C after the notice exits with 130.
- --deaf: keys typed during the 1.5 s after an answer are lost (Claude Code does this while
  it finishes background work after a turn).
- On a clean exit it prints the CLI's resume hint ("Resume this session with:").

Agentic OS integration, like the real CLIs (phase 04):
- **Claude mode** (`--mcp-config` in the argv): MCP server and hooks from the run files;
  hooks SessionStart, UserPromptSubmit and Stop.
- **agy mode** (no prompt in the argv): MCP server and hooks from the workspace plugin
  `.agents/plugins/agentic-os/`; like agy 1.3.3 it connects the MCP server lazily, when
  `/mcp` is typed (Esc closes that panel), and waits for the prompt to be typed; hooks
  PreInvocation and Stop with a conversationId.
  Without --dangerously-skip-permissions every MCP call shows agy's permission dialog.
- In a prompt or typed line, `;`-separated parts call the MCP tools:
  `ESTADO: x` → report_status, `MEMORIA: x` → write_project_memory, `TERMINA: x` →
  complete_task. Hooks really run (hook.cmd + curl) and MCP calls use the official client.

Usage: python fake_cli.py [--ignore-exit] [--no-trust] [--deaf] [-i] "<prompt>" [options]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

IGNORE_EXIT = "--ignore-exit" in sys.argv
NO_TRUST = "--no-trust" in sys.argv
DEAF = "--deaf" in sys.argv
SKIP_PERMISSIONS = "--dangerously-skip-permissions" in sys.argv
DEAF_AFTER_ANSWER = 1.5
deaf_until = 0.0

# Options of the real CLIs that take a value: their values are not the prompt.
VALUE_OPTIONS = {
    "--session-id",
    "--setting-sources",
    "--settings",
    "--mcp-config",
    "--append-system-prompt-file",
    "--permission-mode",
    "--model",
    "--mode",
}


def parse_argv(argv: list[str]) -> tuple[str, dict[str, list[str]]]:
    """(prompt, options) — prompt first like Claude, or after -i like the phase 03 agy."""
    options: dict[str, list[str]] = {}
    positional: list[str] = []
    current: str | None = None
    for arg in argv:
        if arg.startswith("--") or arg == "-i":
            current = arg
            options.setdefault(arg, [])
            continue
        if current in VALUE_OPTIONS and not options[current]:
            options[current].append(arg)
            current = None
        elif current == "--allowedTools":
            options[current].append(arg)
        elif current == "-i":
            positional.append(arg)
            current = None
        else:
            positional.append(arg)
    return (positional[0].strip() if positional else ""), options


PROMPT, OPTIONS = parse_argv(sys.argv[1:])
CLAUDE_MODE = "--mcp-config" in OPTIONS
PLUGIN = Path.cwd() / ".agents" / "plugins" / "agentic-os"
AGY_MODE = not CLAUDE_MODE and not PROMPT and PLUGIN.is_dir()
CONVERSATION_ID = str(uuid.uuid4())

if sys.platform == "win32":
    import msvcrt

    def key_available() -> bool:
        return msvcrt.kbhit()

    def read_key() -> str:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):  # arrows arrive as a two-char scan code
            code = msvcrt.getwch()
            return {"P": "down", "H": "up"}.get(code, "other")
        return ch

else:  # pragma: no cover - the backend's Unix PTY path
    import select
    import termios
    import tty

    _fd = sys.stdin.fileno()
    tty.setraw(_fd)
    termios.tcsetattr(_fd, termios.TCSANOW, termios.tcgetattr(_fd))

    def key_available() -> bool:
        return bool(select.select([sys.stdin], [], [], 0)[0])

    def read_key() -> str:
        ch = sys.stdin.read(1)
        if ch == "\x1b" and key_available():
            seq = sys.stdin.read(2)
            return {"[B": "down", "[A": "up"}.get(seq, "other")
        return ch


def out(text: str = "") -> None:
    sys.stdout.write(text + "\r\n")
    sys.stdout.flush()


# ---------------------------------------------------------------- Agentic OS integration
def load_config() -> tuple[str | None, dict[str, str], dict[str, str]]:
    """(MCP url, MCP headers, hook commands by event) from the run files or the plugin."""
    if CLAUDE_MODE:
        mcp = json.loads(Path(OPTIONS["--mcp-config"][0]).read_text("utf-8"))
        server = mcp["mcpServers"]["agentic-os"]
        settings = json.loads(Path(OPTIONS["--settings"][0]).read_text("utf-8"))
        hooks = {e: h[0]["hooks"][0]["command"] for e, h in settings.get("hooks", {}).items()}
        return server["url"], server.get("headers", {}), hooks
    if AGY_MODE:
        mcp = json.loads((PLUGIN / "mcp_config.json").read_text("utf-8"))
        hooks_file = json.loads((PLUGIN / "hooks.json").read_text("utf-8"))["agentic-os"]
        hooks = {e: h[0]["command"] for e, h in hooks_file.items()}
        return mcp["mcpServers"]["agentic-os"]["url"], {}, hooks
    return None, {}, {}


MCP_URL, MCP_HEADERS, HOOKS = load_config()
always_allowed: set[str] = set()


def hook(event: str) -> None:
    command = HOOKS.get(event)
    if not command:
        return
    if CLAUDE_MODE:
        payload = {"hook_event_name": event, "session_id": (OPTIONS.get("--session-id") or [""])[0]}
    else:
        payload = {"conversationId": CONVERSATION_ID, "workspacePaths": [str(Path.cwd())]}
    try:  # like the real CLIs: through the shell, JSON on stdin
        subprocess.run(command, shell=True, input=json.dumps(payload).encode(), timeout=15)
    except Exception as error:
        out(f"(hook {event} failed: {error!r})")


def mcp(tool: str | None, args: dict | None = None) -> str:
    """Calls a tool of the agentic-os MCP server (None: just connect, like agy at start)."""
    import anyio
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def go() -> str:
        async with (
            httpx2.AsyncClient(headers=MCP_HEADERS) as http,
            streamable_http_client(MCP_URL, http_client=http) as (read, write, *_),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            if tool is None:
                return "connected"
            result = await session.call_tool(tool, args or {})
            return result.content[0].text

    try:
        return anyio.run(go)
    except Exception as error:
        return f"(mcp error: {error!r})"


def agy_permission(tool_id: str) -> bool:
    """agy's dialog before an MCP call (any mode but autonomous)."""
    if SKIP_PERMISSIONS or tool_id in always_allowed:
        return True
    options = [
        "1. Yes, allow tool call",
        f"2. Yes, and always allow tool '{tool_id}' in this conversation",
        f"3. Yes, and always allow tool '{tool_id}' (Persist to settings.json)",
        "4. No, deny tool call",
    ]
    selected = 0

    def draw() -> None:
        out("MCP")
        out(tool_id)
        out("Allow calling this tool?")
        for i, option in enumerate(options):
            out(("> " if i == selected else "  ") + option)
        out("esc to cancel")

    draw()
    while True:
        key = read_key()
        if key == "down":
            selected = min(selected + 1, len(options) - 1)
            draw()
        elif key == "up":
            selected = max(selected - 1, 0)
            draw()
        elif key in ("\r", "\n"):
            sys.stdout.write("\x1b[2J\x1b[H")  # the dialog disappears, like in the real TUI
            if selected == 1:
                always_allowed.add(tool_id)
            return selected in (0, 1)
        elif key == "\x1b":
            sys.stdout.write("\x1b[2J\x1b[H")
            return False


TOOLS = {"ESTADO": "report_status", "MEMORIA": "write_project_memory", "TERMINA": "complete_task"}
ARGS = {"report_status": "message", "write_project_memory": "note", "complete_task": "summary"}


def use_tools(text: str) -> None:
    for part in text.split(";"):
        keyword, _, value = part.strip().partition(":")
        tool = TOOLS.get(keyword.strip())
        if tool is None or MCP_URL is None:
            continue
        if AGY_MODE and not agy_permission(f"agentic-os_agentic-os/{tool}"):
            out(f"(denied {tool})")
            continue
        out(f"● MCP {tool}: {mcp(tool, {ARGS[tool]: value.strip()})}")


# ---------------------------------------------------------------- TUI
def trust_dialog() -> None:
    selected = 0
    options = ["No, exit", "Yes, I trust this folder"]

    def draw() -> None:
        out("Do you trust the files in this folder?")
        for i, option in enumerate(options):
            out(("❯ " if i == selected else "  ") + option)
        out("Enter to confirm · Esc to cancel")

    draw()
    while True:
        key = read_key()
        if key in ("down", "up"):
            selected = 1 - selected
            draw()
        elif key in ("\r", "\n"):
            if selected == 1:
                sys.stdout.write("\x1b[2J\x1b[H")  # the dialog goes away, like in the real TUIs
                out("Trusted.")
                return
            out("Bye.")
            sys.exit(1)


def answer(text: str) -> None:
    global deaf_until
    hook("PreInvocation" if AGY_MODE else "UserPromptSubmit")
    out(f"> {text}")
    use_tools(text)
    out(f"● RESPUESTA: {text}")
    out("? for shortcuts")
    hook("Stop")
    if DEAF:
        deaf_until = time.monotonic() + DEAF_AFTER_ANSWER


def long_turn() -> None:
    """A turn that only ends when interrupted (Esc): like Claude Code, no Stop hook then."""
    hook("PreInvocation" if AGY_MODE else "UserPromptSubmit")
    out("esc to interrupt")
    for n in range(1, 10_000):
        out(str(n))
        deadline = time.monotonic() + 0.1
        while time.monotonic() < deadline:
            if key_available() and read_key() == "\x1b":
                out("Interrupted · What should Claude do instead?")
                out("? for shortcuts")
                return
            time.sleep(0.01)


CTRL_C_NOTICE_DELAY = 0.8


def main() -> None:
    if not NO_TRUST:
        trust_dialog()
    if CLAUDE_MODE:
        hook("SessionStart")
    if AGY_MODE:
        out(">")
        out("? for shortcuts")
    if PROMPT:
        answer(PROMPT)
    line = ""
    exit_armed = False
    while True:
        key = read_key()
        if time.monotonic() < deaf_until:
            continue
        if key == "\x03":
            if IGNORE_EXIT:
                continue
            if exit_armed:
                out("Resume with -c (or command below):")
                sys.exit(130)
            # Keys typed while agy arms the exit are lost, like in the real TUI.
            time.sleep(CTRL_C_NOTICE_DELAY)
            while key_available():
                read_key()
            out("press ctrl+c again to exit")
            exit_armed = True
            continue
        if key == "\x1b" or key in ("down", "up", "other"):
            continue
        if key in ("\r", "\n"):
            text, line = line.strip(), ""
            if not text:
                continue
            if text == "/exit":
                if IGNORE_EXIT:
                    out("(ignoring /exit)")
                    continue
                hook("SessionEnd")
                out("Resume this session with:")
                sys.exit(0)
            if AGY_MODE and text == "/mcp":
                out("MCP servers")
                out(f"  agentic-os  {mcp(None)}")  # agy connects lazily, here
                out("esc to close")
                continue
            if text == "LARGO":
                long_turn()
            else:
                answer(text)
        elif key == "\x7f" or key == "\b":
            line = line[:-1]
        else:
            line += key


if __name__ == "__main__":
    main()
