"""Phase 12, spike S4: cost of the reads the Git tab does all the time.

- `git status --porcelain=v2` of 20 repos, one after another and in 8 threads.
- `git log --topo-order` pages of 200 commits in a 50 000-commit repo (built with fast-import),
  the first page and one deep in the history (cursor = a sha).
"""

# ruff: noqa: E501 - long prompts and one-line probes
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LOG_FORMAT = "%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%s%x1f%D%x1e"


def git(cwd: Path, *args: str, input: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, input=input, timeout=300
    )


def make_big_repo(path: Path, commits: int) -> None:
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    stream = []
    for i in range(1, commits + 1):
        message = f"commit {i}"
        stream.append(
            f"commit refs/heads/main\nmark :{i}\ncommitter T <t@t> {1_700_000_000 + i} +0000\n"
        )
        stream.append(f"data {len(message)}\n{message}\n")
        if i > 1:
            stream.append(f"from :{i - 1}\n")
        stream.append(f"M 100644 inline f{i % 50}.txt\ndata 2\n{i % 10}\n\n")
    git(path, "fast-import", "--quiet", input="".join(stream).encode())
    git(path, "reset", "-q", "--hard")


def timed(label: str, fn) -> float:
    start = time.monotonic()
    fn()
    took = time.monotonic() - start
    print(f"{label}: {took * 1000:.0f} ms", flush=True)
    return took


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="git-perf-"))
    try:
        repos = []
        for n in range(20):
            repo = root / f"r{n}"
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            for k in range(300):
                (repo / f"f{k}.txt").write_text(f"{k}\n", "utf-8")
            git(repo, "add", "-A")
            git(repo, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-qm", "base")
            (repo / "f1.txt").write_text("changed\n", "utf-8")
            (repo / "new.txt").write_text("new\n", "utf-8")
            repos.append(repo)

        def status(repo: Path) -> None:
            git(repo, "status", "--porcelain=v2", "-z", "--branch", "--show-stash")

        timed("status x20 sequential", lambda: [status(r) for r in repos])
        with ThreadPoolExecutor(8) as pool:
            timed("status x20 in 8 threads", lambda: list(pool.map(status, repos)))

        big = root / "big"
        timed("build 50 000-commit repo", lambda: make_big_repo(big, 50_000))
        timed(
            "log page 1 (200)",
            lambda: git(big, "log", "--topo-order", "-n", "200", f"--format={LOG_FORMAT}", "main"),
        )
        sha = (
            git(big, "rev-list", "--topo-order", "-n", "1", "--skip=30000", "main")
            .stdout.decode()
            .strip()
        )
        timed(
            "log page deep (cursor at 30 000)",
            lambda: git(big, "log", "--topo-order", "-n", "200", f"--format={LOG_FORMAT}", sha),
        )
        timed(
            "log --all page 1 (excluding our refs)",
            lambda: git(
                big,
                "log",
                "--topo-order",
                "-n",
                "200",
                f"--format={LOG_FORMAT}",
                "--exclude=refs/agentic-os/*",
                "--branches",
                "--tags",
                "--remotes",
            ),
        )
        timed("rev-list --count main", lambda: git(big, "rev-list", "--count", "main"))
        timed(
            "log -S search (deep)",
            lambda: git(big, "log", "-n", "50", "--format=%H", "-S", "zzz-not-there", "main"),
        )
        timed("blame f1.txt", lambda: git(big, "blame", "--porcelain", "f1.txt"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
