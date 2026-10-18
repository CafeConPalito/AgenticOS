"""Phase 13 S3: git mechanics of the lanes of a forked task.

Checks, on a temporary repo, that:
  1. `agentic/T-1` and `agentic/T-1/backend` cannot coexist (a ref cannot also be a folder);
  2. `agentic/T-1-backend` can be created from the tip of `agentic/T-1` while that branch is
     checked out in the task's worktree, each lane in its own worktree;
  3. the lanes can be merged into `agentic/T-1` from the task's worktree (fast-forward for the
     first lane, `--no-ff` merge for the second), and a conflict aborts cleanly;
  4. a lane can be reopened at the new tip of the task's branch (`branch -f` once its worktree
     is gone; `merge --ff-only` while it is alive).

Usage: uv run python git_lanes_probe.py
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "phases" / "13-pipelines-ramas" / "evidencias" / "s3-git-lanes.md"
lines: list[str] = ["# Ramas de las vías en git (S3)\n"]


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-c", "user.name=spike", "-c", "user.email=spike@example.com", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and proc.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc


def note(
    title: str, proc: subprocess.CompletedProcess[str] | None, ok: bool, extra: str = ""
) -> None:
    detail = ""
    if proc is not None:
        detail = f" · rc={proc.returncode} · `{(proc.stderr or proc.stdout).strip()[:160]}`"
    lines.append(f"- {'OK' if ok else 'FALLA'} · {title}{detail}{(' · ' + extra) if extra else ''}")
    print(lines[-1])


def commit(folder: Path, name: str, text: str, message: str) -> None:
    (folder / name).write_text(text, "utf-8")
    git(folder, "add", "-A")
    git(folder, "commit", "-m", message)


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="agentic-lanes-"))
    repo = root / "proj"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    commit(repo, "base.txt", "base\n", "base")

    # 1. a ref cannot be both a branch and a folder of branches
    git(repo, "branch", "agentic/T-1")
    clash = git(repo, "branch", "agentic/T-1/backend", check=False)
    note(
        "`agentic/T-1/backend` junto a `agentic/T-1` (se espera que falle)",
        clash,
        clash.returncode != 0,
    )
    git(repo, "branch", "-D", "agentic/T-1")

    # 2. the task's worktree and one worktree per lane, from the tip of the task's branch
    work = root / "proj.wt" / "T-1"
    git(repo, "worktree", "add", "-b", "agentic/T-1", str(work), "main")
    commit(work, "req.txt", "requisitos\n", "requisitos")  # the stage before the fork
    lanes = {}
    for lane in ("backend", "frontend"):
        folder = root / "proj.wt" / f"T-1-{lane}"
        made = git(
            repo,
            "worktree",
            "add",
            "-b",
            f"agentic/T-1-{lane}",
            str(folder),
            "agentic/T-1",
            check=False,
        )
        note(
            f"worktree de la vía {lane} con la tarea activa en su carpeta",
            made,
            made.returncode == 0,
        )
        lanes[lane] = folder
    commit(lanes["backend"], "api.py", "api\n", "api")
    commit(lanes["frontend"], "ui.tsx", "ui\n", "ui")

    # 3. join: both lanes finished and released (worktrees removed, branches kept)
    for folder in lanes.values():
        git(repo, "worktree", "remove", "--force", str(folder))
    first = git(work, "merge", "--ff-only", "agentic/T-1-backend", check=False)
    note(
        "unión 1: fast-forward de la primera vía en la rama de la tarea",
        first,
        first.returncode == 0,
    )
    second = git(
        work,
        "merge",
        "--no-ff",
        "-m",
        "merge(agentic): T-1·frontend into T-1",
        "agentic/T-1-frontend",
        check=False,
    )
    note("unión 2: merge --no-ff de la segunda vía", second, second.returncode == 0)
    files = sorted(p.name for p in work.iterdir() if p.is_file())
    note(
        "la rama de la tarea contiene el trabajo de las dos vías",
        None,
        {"api.py", "ui.tsx", "req.txt"} <= set(files),
        str(files),
    )

    # conflict: both lanes edit the same file
    git(repo, "worktree", "add", "-b", "agentic/T-2", str(root / "proj.wt" / "T-2"), "main")
    work2 = root / "proj.wt" / "T-2"
    commit(work2, "shared.txt", "inicio\n", "inicio")
    for lane, text in (("a", "versión A\n"), ("b", "versión B\n")):
        folder = root / "proj.wt" / f"T-2-{lane}"
        git(repo, "worktree", "add", "-b", f"agentic/T-2-{lane}", str(folder), "agentic/T-2")
        commit(folder, "shared.txt", text, f"lane {lane}")
        git(repo, "worktree", "remove", "--force", str(folder))
    git(work2, "merge", "--ff-only", "agentic/T-2-a")
    conflict = git(work2, "merge", "--no-ff", "-m", "merge", "agentic/T-2-b", check=False)
    note("conflicto al unir vías que tocan el mismo fichero", conflict, conflict.returncode != 0)
    abort = git(work2, "merge", "--abort", check=False)
    clean = git(work2, "status", "--porcelain").stdout.strip() == ""
    note(
        "`merge --abort` deja el worktree de la tarea limpio",
        abort,
        abort.returncode == 0 and clean,
    )

    # 4. reopen a lane at the new tip of the task's branch
    tip = git(work, "rev-parse", "agentic/T-1").stdout.strip()
    moved = git(repo, "branch", "-f", "agentic/T-1-backend", tip, check=False)
    note(
        "reabrir una vía sin worktree: `branch -f` al extremo de la tarea",
        moved,
        moved.returncode == 0,
    )
    folder = root / "proj.wt" / "T-1-backend"
    git(repo, "worktree", "add", str(folder), "agentic/T-1-backend")
    commit(work, "qa.txt", "qa\n", "qa pide cambios")  # the task's branch moves on
    ff = git(folder, "merge", "--ff-only", "agentic/T-1", check=False)
    note(
        "reabrir una vía con worktree vivo: `merge --ff-only` desde la tarea",
        ff,
        ff.returncode == 0,
    )
    ahead = git(repo, "rev-list", "--count", "agentic/T-1..agentic/T-1-backend").stdout.strip()
    note(
        "la vía reabierta no tiene commits propios sobre la tarea",
        None,
        ahead == "0",
        f"adelantada {ahead}",
    )

    # naming: what a parser of branch names sees
    names = git(
        repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/agentic/"
    ).stdout.split()
    lines.append(f"\nRamas creadas: `{names}`")
    lines.append(f"\nRepo de la prueba: `{root}` (se puede borrar).")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"evidence: {OUT}")


if __name__ == "__main__":
    main()
