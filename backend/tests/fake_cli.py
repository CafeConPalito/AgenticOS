"""A fake agent CLI that imitates the parts of the Claude Code / agy TUIs Agentic OS relies on.

Behaviour (keys are read raw, like the real TUIs):
- Folder-trust dialog: "No, exit" preselected; Down + Enter accepts, Enter alone exits(1).
- Answers the initial prompt and every typed line with "● RESPUESTA: <text>".
- Typing "LARGO" starts a long turn (footer "esc to interrupt", numbers every 0.1 s);
  Esc interrupts it with "Interrupted · What should Claude do instead?".
- "/exit" exits with code 0, unless --ignore-exit (then it also ignores Ctrl+C).
- Ctrl+C works like agy: the first one shows "press ctrl+c again to exit" after a short
  delay (presses in between are lost); a second Ctrl+C after the notice exits with 130.

Usage: python fake_cli.py [--ignore-exit] [--no-trust] [-i] "<prompt>"
"""

from __future__ import annotations

import sys
import time

IGNORE_EXIT = "--ignore-exit" in sys.argv
NO_TRUST = "--no-trust" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("-")]
PROMPT = args[0] if args else ""

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
                out("Trusted.")
                return
            out("Bye.")
            sys.exit(1)


def answer(text: str) -> None:
    out(f"> {text}")
    out(f"● RESPUESTA: {text}")
    out("? for shortcuts")


def long_turn() -> None:
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
    if PROMPT:
        answer(PROMPT)
    line = ""
    exit_armed = False
    while True:
        key = read_key()
        if key == "\x03":
            if IGNORE_EXIT:
                continue
            if exit_armed:
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
                out("Bye.")
                sys.exit(0)
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
