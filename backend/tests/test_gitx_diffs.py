"""The diffs of the Git tab: uncommitted changes, one commit, two refs (phase 12, bloque 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitrepos import commit_file, make_repo, sh, write

from agentic_os.errors import NotFound
from agentic_os.services import changes
from agentic_os.services.gitx import read
from agentic_os.services.gitx.runner import Repo


def by_path(rng: changes.Range) -> dict:
    return {f.path: f for f in changes.file_list(rng)}


def lines_of(diff) -> list[tuple[str, str]]:
    return [(line.kind, line.text) for hunk in diff.hunks for line in hunk.lines]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "web", files={"a.py": "uno\ndos\ntres\n", "b.py": "x\n"})


# ------------------------------------------------------------------------ uncommitted changes
def test_unstaged_changes_include_new_files_git_does_not_track(repo: Path):
    write(repo, "a.py", "uno\nDOS\ntres\ncuatro\n")  # 2 added, 1 deleted
    (repo / "b.py").unlink()
    write(repo, "nuevo.txt", "a\nb\nc\n")
    write(repo, "con espacios/ñ.txt", "z\n")
    write(repo, "logo.bin", "\0\1\2")

    files = by_path(changes.worktree_range(str(repo), staged=False))

    assert (files["a.py"].status, files["a.py"].additions, files["a.py"].deletions) == (
        "modified",
        2,
        1,
    )
    assert files["b.py"].status == "deleted" and files["b.py"].deletions == 1
    assert (files["nuevo.txt"].status, files["nuevo.txt"].additions) == ("added", 3)
    assert files["con espacios/ñ.txt"].additions == 1
    assert files["logo.bin"].binary and files["logo.bin"].new_size == 3


def test_the_diff_and_the_context_of_an_unstaged_file(repo: Path):
    write(repo, "a.py", "uno\nDOS\ntres\ncuatro\ncinco\nseis\nsiete\n")
    rng = changes.worktree_range(str(repo), staged=False)

    diff = changes.file_diff(rng, "a.py")
    assert lines_of(diff)[:4] == [
        ("context", "uno"),
        ("del", "dos"),
        ("add", "DOS"),
        ("context", "tres"),
    ]
    more = changes.file_lines(rng, "a.py", 6, 7)
    assert [(line.new_no, line.text) for line in more.lines] == [(6, "seis"), (7, "siete")]


def test_an_untracked_file_has_a_diff_and_lines_of_its_own(repo: Path):
    write(repo, "nuevo.txt", "a\nb\n")
    rng = changes.worktree_range(str(repo), staged=False)

    diff = changes.file_diff(rng, "nuevo.txt")

    assert lines_of(diff) == [("add", "a"), ("add", "b")]
    assert [line.text for line in changes.file_lines(rng, "nuevo.txt", 1, 5).lines] == ["a", "b"]
    # Files that are neither changed nor new cannot be read through the endpoint.
    for path in ("README.md", "../fuera", "no-existe"):
        with pytest.raises(NotFound):
            changes.file_diff(rng, path)
        with pytest.raises(NotFound):
            changes.file_lines(rng, path, 1, 3)


def test_staged_changes_are_head_against_the_index(repo: Path):
    write(repo, "a.py", "uno\nDOS\ntres\n")
    sh(repo, "add", "a.py")
    sh(repo, "mv", "b.py", "c.py")
    write(repo, "a.py", "uno\nDOS\nTRES\n")  # unstaged on top of the staged one

    staged = by_path(changes.worktree_range(str(repo), staged=True))
    unstaged = by_path(changes.worktree_range(str(repo), staged=False))

    assert set(staged) == {"a.py", "c.py"} and staged["c.py"].status == "renamed"
    assert (staged["a.py"].additions, staged["a.py"].deletions) == (1, 1)
    assert (unstaged["a.py"].additions, unstaged["a.py"].deletions) == (1, 1)
    staged_lines = lines_of(changes.file_diff(changes.worktree_range(str(repo), True), "a.py"))
    assert ("add", "DOS") in staged_lines and ("add", "TRES") not in staged_lines
    shown = changes.file_lines(changes.worktree_range(str(repo), True), "a.py", 1, 3)
    assert [line.text for line in shown.lines] == ["uno", "DOS", "tres"]  # the index's version


def test_a_repository_with_no_commits_stages_everything_as_added(tmp_path: Path):
    path = tmp_path / "vacio"
    path.mkdir()
    sh(path, "init", "-q", "-b", "main")
    write(path, "a.txt", "x\n")
    sh(path, "add", "a.txt")

    staged = by_path(changes.worktree_range(str(path), staged=True))

    assert staged["a.txt"].status == "added" and staged["a.txt"].additions == 1


# ------------------------------------------------------------------------ a commit, two refs
def test_the_changes_of_a_commit_and_of_a_root_commit(repo: Path):
    sha = commit_file(repo, "a.py", "uno\nDOS\ntres\n", message="cambia dos")
    commit = read.commit_detail(Repo(str(repo)), sha)

    files = by_path(changes.commit_range(str(repo), sha, read.parent_or_empty(commit)))
    assert set(files) == {"a.py"} and (files["a.py"].additions, files["a.py"].deletions) == (1, 1)

    root_sha = sh(repo, "rev-list", "--max-parents=0", "HEAD")
    root = read.commit_detail(Repo(str(repo)), root_sha)
    root_files = by_path(changes.commit_range(str(repo), root_sha, read.parent_or_empty(root)))
    assert set(root_files) == {"README.md", "a.py", "b.py"}
    assert all(f.status == "added" for f in root_files.values())


def test_a_merge_commit_is_shown_against_its_first_parent(repo: Path):
    sh(repo, "checkout", "-q", "-b", "otra")
    commit_file(repo, "otra.txt", "o\n")
    sh(repo, "checkout", "-q", "main")
    commit_file(repo, "main.txt", "m\n")
    sh(repo, "merge", "-q", "--no-ff", "otra", "-m", "merge otra")
    sha = sh(repo, "rev-parse", "HEAD")
    commit = read.commit_detail(Repo(str(repo)), sha)

    files = by_path(changes.commit_range(str(repo), sha, read.parent_or_empty(commit)))

    assert set(files) == {"otra.txt"}  # what the merge brought into main


def test_compare_two_refs_directly_or_since_they_diverged(repo: Path):
    sh(repo, "checkout", "-q", "-b", "feature")
    commit_file(repo, "feature.txt", "f\n")
    sh(repo, "checkout", "-q", "main")
    commit_file(repo, "main.txt", "m\n")  # main moved on

    direct = by_path(changes.compare_range(str(repo), "main", "feature"))
    since = by_path(changes.compare_range(str(repo), "main", "feature", merge_base=True))

    assert set(direct) == {"feature.txt", "main.txt"}  # also undoes main's own change
    assert set(since) == {"feature.txt"}  # only what the branch did
    assert since["feature.txt"].status == "added"
    unrelated = changes.compare_range(str(repo), "main", "feature", merge_base=True)
    assert unrelated.from_ref and unrelated.from_ref.kind == "ref"
