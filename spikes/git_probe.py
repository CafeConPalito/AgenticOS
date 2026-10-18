"""Phase 12, spike S3: what git 2.55 offers for the app's operations, without a terminal.

Checks merge-tree/replay (integration without a work folder), GIT_SEQUENCE_EDITOR for the
interactive rebase, `exec git commit --amend -m` for reword, and credential/ssh behaviour with
no terminal. Prints one line per probe; writes nothing outside a temp folder.
"""

# ruff: noqa: E501 - long prompts and one-line probes
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
    "GIT_AUTHOR_NAME": "T",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "T",
    "GIT_COMMITTER_EMAIL": "t@t",
    "LC_ALL": "C",
}


def git(
    cwd: Path, *args: str, env: dict | None = None, check: bool = True, input: str | None = None
):
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "core.editor=true", *args],
        cwd=cwd,
        env={**ENV, **(env or {})},
        capture_output=True,
        text=True,
        input=input,
        timeout=60,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def write(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, "utf-8", newline="\n")


def commit(repo: Path, name: str, text: str, message: str) -> str:
    write(repo, name, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f" · {detail}" if detail else ""), flush=True)


def fresh(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "a.txt", "1\n2\n3\n", "base")
    return repo


def probe_merge_tree(root: Path) -> None:
    repo = fresh(root, "mt")
    git(repo, "switch", "-qc", "feat")
    commit(repo, "b.txt", "feat\n", "feat 1")
    git(repo, "switch", "-q", "main")
    commit(repo, "c.txt", "main\n", "main 1")
    clean = git(repo, "merge-tree", "--write-tree", "main", "feat", check=False)
    report(
        "merge-tree clean",
        clean.returncode == 0 and len(clean.stdout.split()) == 1,
        clean.stdout.strip(),
    )

    git(repo, "switch", "-qc", "x1", "main~1")
    commit(repo, "a.txt", "1\nX\n3\n", "x1")
    git(repo, "switch", "-q", "main")
    commit(repo, "a.txt", "1\nY\n3\n", "main edits a")
    bad = git(repo, "merge-tree", "--write-tree", "--name-only", "main", "x1", check=False)
    lines = bad.stdout.splitlines()
    report(
        "merge-tree conflict",
        bad.returncode == 1 and "a.txt" in lines,
        f"rc={bad.returncode} {lines[:4]}",
    )
    # The merge commit without touching any folder.
    tree = clean.stdout.split()[0]
    merged = git(
        repo, "commit-tree", tree, "-p", "main", "-p", "feat", "-m", "Merge T-1"
    ).stdout.strip()
    git(
        repo, "update-ref", "refs/heads/main", merged, git(repo, "rev-parse", "main").stdout.strip()
    )
    report("commit-tree + update-ref", bool(merged), merged[:8])


def probe_replay(root: Path) -> None:
    repo = fresh(root, "rp")
    git(repo, "switch", "-qc", "feat")
    commit(repo, "b.txt", "feat\n", "feat 1")
    git(repo, "switch", "-q", "main")
    commit(repo, "c.txt", "main\n", "main 1")
    before = git(repo, "rev-parse", "feat").stdout.strip()
    printed = git(repo, "replay", "--ref-action=print", "--onto", "main", "main..feat", check=False)
    report(
        "replay --ref-action=print",
        printed.returncode == 0 and printed.stdout.startswith("update "),
        printed.stdout.strip()[:100],
    )
    report("print leaves the branch alone", git(repo, "rev-parse", "feat").stdout.strip() == before)
    res = git(repo, "replay", "--onto", "main", "main..feat", check=False)
    log = git(repo, "log", "--format=%s", "-3", "feat").stdout.split("\n")
    report(
        "replay updates the branch by default",
        res.returncode == 0 and log[:2] == ["feat 1", "main 1"],
        str(log),
    )


def probe_sequence_editor(root: Path) -> None:
    repo = fresh(root, "seq")
    shas = [commit(repo, f"f{i}.txt", f"{i}\n", f"c{i}") for i in range(1, 5)]
    todo = root / "todo.txt"
    # reorder c3 before c2, squash c4 into c3, reword c2 via exec amend.
    todo.write_text(
        f"pick {shas[2]}\nfixup {shas[3]}\npick {shas[1]}\nexec git commit --amend -m reworded\n",
        "utf-8",
        newline="\n",
    )
    # git runs the editor through its own sh: a shell script, addressed with a POSIX path.
    script = root / "seq1.sh"
    script.write_text(f'#!/bin/sh\ncp "{todo.as_posix()}" "$1"\n', "ascii", newline="\n")
    res = git(
        repo, "rebase", "-i", shas[0], env={"GIT_SEQUENCE_EDITOR": script.as_posix()}, check=False
    )
    log = git(repo, "log", "--format=%s", "-4").stdout.split("\n")
    report(
        "rebase -i via GIT_SEQUENCE_EDITOR (sh script)",
        res.returncode == 0 and log[0] == "reworded",
        f"rc={res.returncode} {log}",
    )
    bat = root / "seq.cmd"
    bat.write_text(f'@copy /Y "{todo}" "%~1" >nul\r\n', "ascii")
    repo3 = fresh(root, "seq3")
    first = commit(repo3, "f1.txt", "1\n", "c1")
    second = commit(repo3, "f2.txt", "2\n", "c2")
    todo.write_text(f"pick {second}\n", "utf-8", newline="\n")
    res3 = git(repo3, "rebase", "-i", first, env={"GIT_SEQUENCE_EDITOR": str(bat)}, check=False)
    report(
        "(contrast) a .cmd editor path", True, "works" if res3.returncode == 0 else "does NOT work"
    )
    sh = root / "seq.sh"
    sh.write_text(f'#!/bin/sh\ncp "{todo.as_posix()}" "$1"\n', "ascii", newline="\n")
    repo2 = fresh(root, "seq2")
    shas2 = [commit(repo2, f"f{i}.txt", f"{i}\n", f"c{i}") for i in range(1, 4)]
    todo.write_text(f"pick {shas2[1]}\nedit {shas2[2]}\n", "utf-8", newline="\n")
    res2 = git(
        repo2, "rebase", "-i", shas2[0], env={"GIT_SEQUENCE_EDITOR": sh.as_posix()}, check=False
    )
    stopped = (repo2 / ".git" / "rebase-merge").is_dir()
    report("rebase -i stops at `edit`", res2.returncode == 0 and stopped, f"rc={res2.returncode}")
    git(repo2, "reset", "-q", "HEAD^")
    git(repo2, "rebase", "--continue", check=False)
    report("split then --continue", not (repo2 / ".git" / "rebase-merge").is_dir())


def probe_no_terminal(root: Path) -> None:
    repo = fresh(root, "net")
    # An https remote that needs credentials must fail fast, not wait for a prompt.
    git(
        repo,
        "remote",
        "add",
        "origin",
        "https://github.com/octocat/this-repo-does-not-exist-xyz.git",
    )
    import time

    start = time.monotonic()
    try:
        res = git(
            repo,
            "-c",
            "credential.helper=",
            "fetch",
            "origin",
            check=False,
            env={"GCM_INTERACTIVE": "never"},
        )
        took = time.monotonic() - start
        report(
            "https fetch with no credentials fails fast",
            res.returncode != 0 and took < 30,
            f"{took:.1f}s {res.stderr.strip()[:90]}",
        )
    except subprocess.TimeoutExpired:
        report("https fetch with no credentials fails fast", False, "timed out (it waited)")
    ssh = git(repo, "ls-remote", "git@github.com:octocat/nope.git", check=False)
    report(
        "ssh BatchMode never prompts",
        ssh.returncode != 0,
        ssh.stderr.strip().splitlines()[-1][:90] if ssh.stderr.strip() else "",
    )
    fill = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        env={**ENV, "GCM_INTERACTIVE": "never"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    have = "password=" in fill.stdout
    report(
        "credential fill github.com (stored token?)",
        True,
        "token stored" if have else f"none stored ({fill.stderr.strip()[:70]})",
    )


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="git-probe-"))
    try:
        for probe in (probe_merge_tree, probe_replay, probe_sequence_editor, probe_no_terminal):
            try:
                probe(root)
            except Exception as error:  # a probe that breaks is a result too
                report(probe.__name__, False, str(error)[:200])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
