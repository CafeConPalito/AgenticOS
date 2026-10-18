"""Phase 12, spike S1 (interactive): does agy honour the PreToolUse `allow` of the plugin hook in a
real session (PTY, default permission mode)? Headless `-p` ignored it.

Per case: start agy in a sandbox repo with the hook plugin, accept the folder trust, wait until the
commit exists or a "Run this command?" dialog shows. The evidence is the repo and the screen.

    uv run python scenarios/agy_git_hook_pty.py
"""

# ruff: noqa: E501 - long prompts and one-line probes
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import evidence  # noqa: E402
from pty_run import PtyRun, accept_trust, agy_permission_request  # noqa: E402
from scenarios.agy_git_hook import plugin  # noqa: E402
from scenarios.git_permissions import committed, repo  # noqa: E402

MODEL = "gemini-3.8-flash-low"
CASES = {
    "pty-hook-git-commit": (
        "Run exactly this shell command and nothing else: git commit --allow-empty -m probe-commit",
        committed,
    ),
    "pty-hook-non-git-write": (
        "Run exactly this shell command and nothing else: echo hi > not-git.txt",
        lambda p: (p / "not-git.txt").exists(),
    ),
}


def with_remote(path: Path) -> Path:
    """A bare repository next to the sandbox, set as `origin`."""
    import subprocess

    bare = path.parent / f"{path.name}-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", str(bare)], check=True)
    return bare


def pushed(path: Path) -> bool:
    import subprocess

    bare = path.parent / f"{path.name}-remote.git"
    return (
        subprocess.run(
            ["git", "-C", str(bare), "rev-parse", "--verify", "-q", "main"], capture_output=True
        ).returncode
        == 0
    )


def one(name: str, prompt: str, done, hook: bool = True, remote: bool = False) -> str:
    path = repo(name)
    log = path.parent / f"{path.name}-hook.log"
    if remote:
        with_remote(path)
    if hook:
        plugin(path, log)
    run = PtyRun(
        ["agy", "--model", MODEL, "-i", prompt],
        path,
        evidence(f"s1-{name}.raw.log"),
        cols=120,
        rows=40,
    )
    dialog = None
    try:
        if run.wait_screen(r"trust the contents", timeout=30):
            accept_trust(run, "agy")
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            if done(path):
                break
            request = agy_permission_request(run.snapshot())
            if request is not None:
                dialog = request
                run.key("esc")  # never approve by hand: we want to know if the hook did it
                time.sleep(3)
                break
            time.sleep(1)
        seen = log.read_text("utf-8").strip().splitlines() if log.exists() else []
        verdict = (
            "ALLOWED-WITHOUT-DIALOG"
            if done(path) and dialog is None
            else "DIALOG-SHOWN"
            if dialog
            else "NOTHING"
        )
        text = f"{verdict} {name} · dialog={dialog} · done={done(path)}\n         hook saw: {seen}"
    finally:
        run.close()
    print(text, flush=True)
    return text


def main() -> None:
    results = ["(commit / non-git write: see previous run: no dialog with or without hook)"]
    push = "Run exactly this shell command and nothing else: git push origin main"
    results.append(one("pty-control-git-push", push, pushed, hook=False, remote=True))
    results.append(one("pty-hook-git-push", push, pushed, hook=True, remote=True))
    force = "Run exactly this shell command and nothing else: git push --force origin main"
    results.append(one("pty-hook-git-push-force", force, pushed, hook=True, remote=True))
    target = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "phases"
        / "12-control-git"
        / "evidencias"
        / "s1-agy-git-hook-pty.md"
    )
    target.write_text(
        "# agy · hook PreToolUse en sesión interactiva (fase 12)\n\n```\n"
        + "\n".join(results)
        + "\n```\n",
        "utf-8",
    )
    print("evidence:", target)


if __name__ == "__main__":
    main()
