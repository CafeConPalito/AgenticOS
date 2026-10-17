"""Snapshots of a folder on real temporary git repositories (phase 11, ADR 0015)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_worktrees import make_repo, sh

from agentic_os.services import git, snapshots


def tree_files(repo: Path, sha: str) -> list[str]:
    return sh(repo, "ls-tree", "-r", "--name-only", sha).splitlines()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "mi web")


def test_a_snapshot_holds_committed_modified_and_new_files(repo: Path, tmp_path: Path):
    (repo / "README.md").write_text("cambiado\n", "utf-8")
    (repo / "nuevo.txt").write_text("nuevo\n", "utf-8")
    (repo / ".gitignore").write_text("*.log\n", "utf-8")
    (repo / "debug.log").write_text("ruido\n", "utf-8")

    snap = snapshots.take(str(repo), "run1", "start", tmp_path / "scratch")

    assert snap is not None
    files = tree_files(repo, snap.sha)
    assert {"README.md", "nuevo.txt", ".gitignore"} <= set(files)
    assert "debug.log" not in files  # ignored files stay out
    assert sh(repo, "show", f"{snap.sha}:README.md") == "cambiado"


def test_it_never_touches_the_index_head_or_files(repo: Path, tmp_path: Path):
    (repo / "README.md").write_text("cambiado\n", "utf-8")
    (repo / "nuevo.txt").write_text("nuevo\n", "utf-8")
    sh(repo, "add", "README.md")  # a staged change that must stay staged
    before = (
        sh(repo, "status", "--porcelain"),
        sh(repo, "rev-parse", "HEAD"),
        sh(repo, "branch", "--list"),
        sh(repo, "write-tree"),
    )

    assert snapshots.take(str(repo), "run1", "start", tmp_path / "scratch") is not None

    after = (
        sh(repo, "status", "--porcelain"),
        sh(repo, "rev-parse", "HEAD"),
        sh(repo, "branch", "--list"),
        sh(repo, "write-tree"),
    )
    assert after == before
    assert (repo / "nuevo.txt").read_text("utf-8") == "nuevo\n"
    assert not list((tmp_path / "scratch").iterdir())  # the temporary index is gone


def test_the_refs_keep_the_commits_after_gc(repo: Path, tmp_path: Path):
    (repo / "nuevo.txt").write_text("nuevo\n", "utf-8")
    snap = snapshots.take(str(repo), "run1", "end", tmp_path)
    assert snap is not None
    assert sh(repo, "rev-parse", snapshots.ref_name("run1", "end")) == snap.sha

    sh(repo, "reflog", "expire", "--expire=now", "--all")
    sh(repo, "gc", "--prune=now", "-q")

    assert snapshots.exists(str(repo), snap.sha)
    assert "agentic" not in sh(repo, "branch", "--list", "--all")  # not a branch
    assert sh(repo, "tag", "--list") == ""


def test_without_head_and_without_identity(tmp_path: Path):
    folder = tmp_path / "vacio"
    folder.mkdir()
    sh(folder, "init", "-b", "main")
    (folder / "a.txt").write_text("a\n", "utf-8")

    snap = snapshots.take(str(folder), "run1", "start", tmp_path / "s")

    assert snap is not None and tree_files(folder, snap.sha) == ["a.txt"]
    assert sh(folder, "log", "-1", "--format=%P", snap.sha) == ""  # no parent


def test_the_agent_plugin_excluded_by_info_exclude_stays_out(repo: Path, tmp_path: Path):
    exclude = repo / ".git" / "info" / "exclude"
    exclude.write_text(".agents/plugins/agentic-os/\n", "utf-8")
    plugin = repo / ".agents" / "plugins" / "agentic-os"
    plugin.mkdir(parents=True)
    (plugin / "mcp.json").write_text('{"token": "secreto"}', "utf-8")

    snap = snapshots.take(str(repo), "run1", "start", tmp_path)

    assert snap is not None
    assert not any(".agents" in name for name in tree_files(repo, snap.sha))


def test_it_works_in_a_worktree_and_the_refs_outlive_it(repo: Path, tmp_path: Path):
    worktree = tmp_path / "mi web.wt" / "T-1"
    sh(repo, "worktree", "add", "-b", "agentic/T-1", str(worktree), "main")
    (worktree / "feature.py").write_text("print(1)\n", "utf-8")

    snap = snapshots.take(str(worktree), "run1", "end", tmp_path / "s")
    assert snap is not None
    sh(repo, "worktree", "remove", "--force", str(worktree))

    assert snapshots.exists(str(repo), snap.sha)
    assert "feature.py" in tree_files(repo, snap.sha)
    assert sh(repo, "rev-parse", snapshots.ref_name("run1", "end")) == snap.sha


def test_new_files_over_the_limit_are_left_out(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(snapshots, "MAX_NEW_FILE", 100)
    (repo / "pequeno.txt").write_text("x" * 50, "utf-8")
    (repo / "grande.bin").write_bytes(b"x" * 500)
    (repo / "README.md").write_text("y" * 500, "utf-8")  # tracked: always included

    snap = snapshots.take(str(repo), "run1", "start", tmp_path)

    assert snap is not None and snap.skipped_large == 1
    files = tree_files(repo, snap.sha)
    assert "pequeno.txt" in files and "README.md" in files and "grande.bin" not in files


def test_a_folder_without_git_or_a_failure_gives_none(tmp_path: Path, repo: Path):
    plain = tmp_path / "sin git"
    plain.mkdir()
    assert snapshots.take_checked(str(plain)) == (None, None)
    assert snapshots.take_checked(str(tmp_path / "no existe")) == (None, None)

    # a broken repository counts as "no git": no snapshot and nothing raised
    (repo / ".git" / "HEAD").write_text("basura", "utf-8")
    assert snapshots.take_checked(str(repo), "run1", "start", tmp_path) == (None, None)


def test_a_slow_snapshot_is_dropped(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(snapshots, "BUDGET", -1)
    snap, error = snapshots.take_checked(str(repo), "run1", "start", tmp_path)
    assert snap is None and error and "out of time" in error


def refs_of(repo: Path) -> list[str]:
    out = sh(repo, "for-each-ref", "--format=%(refname)", "refs/agentic-os/")
    return sorted(out.splitlines())


def test_delete_the_refs_of_some_runs_only(repo: Path, tmp_path: Path):
    for run in ("a", "b", "c"):
        snapshots.take(str(repo), run, "start", tmp_path)
        snapshots.take(str(repo), run, "end", tmp_path)
    assert len(refs_of(repo)) == 6

    assert snapshots.delete_runs(str(repo), ["a", "zzz"]) == 2  # unknown runs are ignored
    assert refs_of(repo) == [
        snapshots.ref_name(run, label) for run in ("b", "c") for label in ("end", "start")
    ]
    assert snapshots.delete_runs(str(repo), ["b", "c"]) == 4
    assert refs_of(repo) == []
    assert snapshots.delete_runs(str(tmp_path), ["a"]) == 0  # not a repository


def test_exists_is_false_for_unknown_shas(repo: Path):
    assert not snapshots.exists(str(repo), None)
    assert not snapshots.exists(str(repo), "0" * 40)
    assert snapshots.exists(str(repo), sh(repo, "rev-parse", "HEAD"))
    with pytest.raises(git.GitError):
        git.run(str(repo), "cat-file", "-e", "0" * 40)
