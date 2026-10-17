"""Phase 12, spike S1 (linked repos): can agy work in a second repo outside its folder with
`--add-dir`? Interactive session (PTY), default permission mode.

Two cases, each with a `git -C <other repo> commit` as the action:
  - with `--add-dir <other>`
  - without it (control): does agy ask, refuse, or just do it?

    uv run python scenarios/agy_add_dir.py
"""

# ruff: noqa: E501 - long prompts and one-line probes
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import evidence  # noqa: E402
from pty_run import PtyRun, accept_trust, agy_permission_request  # noqa: E402
from scenarios.git_permissions import committed, repo  # noqa: E402

MODEL = "gemini-3.8-flash-low"


def one(name: str, use_add_dir: bool) -> str:
    main, other = repo(f"{name}-main"), repo(f"{name}-other")
    prompt = f'Run exactly this shell command and nothing else: git -C "{other}" commit --allow-empty -m probe-commit'
    argv = [
        "agy",
        "--model",
        MODEL,
        *(["--add-dir", str(other)] if use_add_dir else []),
        "-i",
        prompt,
    ]
    run = PtyRun(argv, main, evidence(f"s1-{name}.raw.log"), cols=120, rows=40)
    dialog, screen = None, ""
    try:
        if run.wait_screen(r"trust the contents", timeout=30):
            accept_trust(run, "agy")
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            if committed(other):
                break
            request = agy_permission_request(run.snapshot())
            if request is not None:
                dialog = request
                run.key("esc")
                time.sleep(3)
                break
            time.sleep(1)
        screen = run.snapshot()
    finally:
        run.close()
    tail = " | ".join(line.strip() for line in screen.splitlines() if line.strip())[-300:]
    text = f"{name}: committed_in_other_repo={committed(other)} · dialog={dialog}\n         screen: {tail}"
    print(text, flush=True)
    return text


def main() -> None:
    results = [one("add-dir", True), one("no-add-dir-control", False)]
    target = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phases"
        / "12-control-git"
        / "evidencias"
        / "s1-agy-add-dir.md"
    )
    target.write_text(
        "# agy · --add-dir con un repo vinculado (fase 12)\n\n```\n"
        + "\n".join(results)
        + "\n```\n",
        "utf-8",
    )
    print("evidence:", target)


if __name__ == "__main__":
    main()
