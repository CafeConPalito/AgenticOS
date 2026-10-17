"""Reading a repository's state, on real repositories (phase 12, bloque 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitrepos import commit_file, make_bare, make_repo, sh, write

from agentic_os.services.gitx import read
from agentic_os.services.gitx.errors import GitxError, classify
from agentic_os.services.gitx.runner import Repo


def repo_of(path: Path) -> Repo:
    return Repo(str(path))


# ------------------------------------------------------------------------------- status
def test_a_clean_repository(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    status = read.status(repo_of(path))
    assert status.branch == "main" and not status.detached and status.clean
    assert status.head == sh(path, "rev-parse", "--short=7", "HEAD")
    assert (status.staged, status.unstaged, status.conflicts) == ([], [], [])
    assert status.upstream is None and status.ahead == status.behind == 0
    assert status.operation is None and status.stashes == 0 and not status.empty


def test_staged_unstaged_untracked_and_renamed_files(tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "uno\n", "b.txt": "dos\ntres\ncuatro\n"})
    write(path, "a.txt", "uno\nmás\n")  # modified, not staged
    write(path, "b.txt", "dos\ntres\ncuatro\ncinco\n")
    sh(path, "add", "b.txt")  # staged
    sh(path, "mv", "README.md", "LEEME.md")  # renamed, staged
    write(path, "nuevo.txt", "x\n")  # untracked
    write(path, "carpeta/dentro.txt", "y\n")  # untracked, in a new folder
    write(path, "ñandú/ü.txt", "z\n")  # non-ASCII names come out as they are

    status = read.status(repo_of(path))

    assert not status.clean
    staged = {(f.path, f.status, f.orig_path) for f in status.staged}
    assert staged == {("b.txt", "M", None), ("LEEME.md", "R", "README.md")}
    unstaged = {(f.path, f.status, f.kind) for f in status.unstaged}
    assert unstaged == {
        ("a.txt", "M", "changed"),
        ("nuevo.txt", "?", "untracked"),
        ("carpeta/dentro.txt", "?", "untracked"),
        ("ñandú/ü.txt", "?", "untracked"),
    }


def test_a_file_can_be_in_both_lists(tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "1\n"})
    write(path, "a.txt", "1\n2\n")
    sh(path, "add", "a.txt")
    write(path, "a.txt", "1\n2\n3\n")

    status = read.status(repo_of(path))

    assert [f.path for f in status.staged] == ["a.txt"]
    assert [f.path for f in status.unstaged] == ["a.txt"]


def test_a_repository_with_no_commits(tmp_path: Path):
    path = tmp_path / "vacio"
    path.mkdir()
    sh(path, "init", "-q", "-b", "main")
    write(path, "a.txt", "x\n")

    status = read.status(repo_of(path))

    assert status.empty and status.head is None and status.branch == "main"
    assert [f.path for f in status.unstaged] == ["a.txt"]
    assert read.log(repo_of(path)).commits == []  # no history is not an error


def test_ahead_and_behind_of_the_upstream_and_the_last_fetch(tmp_path: Path):
    remote = make_bare(tmp_path / "remote.git")
    path = make_repo(tmp_path / "web")
    sh(path, "remote", "add", "origin", str(remote))
    sh(path, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "otro"
    sh(tmp_path, "clone", "-q", str(remote), str(other))
    sh(other, "config", "user.name", "Otro")
    sh(other, "config", "user.email", "otro@example.com")
    commit_file(other, "remoto.txt", "r\n")
    sh(other, "push", "-q")
    commit_file(path, "local1.txt", "1\n")
    commit_file(path, "local2.txt", "2\n")
    assert read.status(repo_of(path)).last_fetch is None

    sh(path, "fetch", "-q")
    status = read.status(repo_of(path))

    assert (status.upstream, status.ahead, status.behind) == ("origin/main", 2, 1)
    assert status.last_fetch is not None


def test_detached_head_and_stashes(tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "1\n"})
    write(path, "a.txt", "2\n")
    sh(path, "stash", "push", "-q")
    sh(path, "checkout", "-q", "--detach")

    status = read.status(repo_of(path))

    assert status.detached and status.branch is None and status.head
    assert status.stashes == 1


def test_conflicts_and_the_operation_in_progress(tmp_path: Path):
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    sh(path, "checkout", "-q", "-b", "otra")
    commit_file(path, "a.txt", "otra\n")
    sh(path, "checkout", "-q", "main")
    commit_file(path, "a.txt", "main\n")
    sh(path, "merge", "otra", check=False)

    status = read.status(repo_of(path))

    assert status.operation == "merge"
    assert [(f.path, f.kind) for f in status.conflicts] == [("a.txt", "unmerged")]
    assert status.staged == [] and not status.clean


# ------------------------------------------------------------------------------- history
def test_history_pages_keep_git_order_and_say_when_there_is_more(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    for index in range(1, 8):
        commit_file(path, f"f{index}.txt", f"{index}\n", message=f"commit {index}")
    repo = repo_of(path)

    first = read.log(repo, limit=3)
    second = read.log(repo, skip=3, limit=3)
    last = read.log(repo, skip=6, limit=3)

    assert [c.subject for c in first.commits] == ["commit 7", "commit 6", "commit 5"]
    assert first.more
    assert [c.subject for c in second.commits] == ["commit 4", "commit 3", "commit 2"]
    assert [c.subject for c in last.commits] == ["commit 1", "init"] and not last.more
    expected = sh(path, "log", "--topo-order", "--format=%H").splitlines()
    everything = read.log(repo).commits
    assert [c.sha for c in everything] == expected
    top = everything[0]
    assert (top.author, top.email) == ("Test", "test@example.com")
    assert top.refs[0].startswith("HEAD -> main") and top.parents == [everything[1].sha]


def test_history_of_all_branches_leaves_out_the_apps_own_refs(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    sh(path, "checkout", "-q", "-b", "feature")
    side = commit_file(path, "f.txt", "x\n", message="en la rama")
    sh(path, "checkout", "-q", "main")
    snapshot = sh(path, "commit-tree", sh(path, "rev-parse", "HEAD^{tree}"), "-m", "snapshot")
    sh(path, "update-ref", "refs/agentic-os/runs/r1/start", snapshot)
    repo = repo_of(path)

    only_current = {c.sha for c in read.log(repo).commits}
    everything = {c.sha for c in read.log(repo, all_refs=True).commits}

    assert side not in only_current and side in everything
    assert snapshot not in everything
    assert all(
        "agentic-os" not in ref for c in read.log(repo, all_refs=True).commits for ref in c.refs
    )


def test_history_filters(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    commit_file(path, "login.py", "def login(): pass\n", message="feat: login")
    sh(
        path,
        "-c",
        "user.name=Ana",
        "-c",
        "user.email=ana@example.com",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "docs: leeme",
    )
    commit_file(path, "otro/b.py", "b = 1\n", message="fix: b")
    repo = repo_of(path)

    assert [c.subject for c in read.log(repo, grep="login").commits] == ["feat: login"]
    assert [c.subject for c in read.log(repo, author="ana").commits] == ["docs: leeme"]
    assert [c.subject for c in read.log(repo, search="def login").commits] == ["feat: login"]
    assert [c.subject for c in read.log(repo, path="otro/b.py").commits] == ["fix: b"]
    assert [c.subject for c in read.log(repo, ref="HEAD~1", limit=1).commits] == ["docs: leeme"]


def test_commit_detail_has_the_whole_message(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    sh(path, "commit", "-q", "--allow-empty", "-m", "feat: algo\n\nCuerpo largo\ncon dos líneas")
    sha = sh(path, "rev-parse", "HEAD")

    detail = read.commit_detail(repo_of(path), sha)

    assert detail.subject == "feat: algo" and detail.body == "Cuerpo largo\ncon dos líneas"
    assert read.parent_or_empty(detail) == detail.parents[0]
    root = read.commit_detail(repo_of(path), sh(path, "rev-list", "--max-parents=0", "HEAD"))
    assert read.parent_or_empty(root) == read.EMPTY_TREE


# ------------------------------------------------------------------------------- branches
def test_branches_with_their_distance_to_the_upstream_and_the_base(tmp_path: Path):
    remote = make_bare(tmp_path / "remote.git")
    path = make_repo(tmp_path / "web")
    sh(path, "remote", "add", "origin", str(remote))
    sh(path, "push", "-q", "-u", "origin", "main")
    sh(path, "checkout", "-q", "-b", "agentic/T-1")
    commit_file(path, "t1.txt", "1\n")
    commit_file(path, "t1b.txt", "2\n")
    sh(path, "checkout", "-q", "-b", "hecha")
    sh(path, "checkout", "-q", "main")
    commit_file(path, "main.txt", "m\n")  # the base moved on

    found = {b.name: b for b in read.branches(repo_of(path), "main")}

    assert set(found) == {"main", "agentic/T-1", "hecha", "origin/main"}
    assert found["main"].current and found["main"].upstream == "origin/main"
    assert (found["main"].ahead, found["main"].behind) == (1, 0)
    task = found["agentic/T-1"]
    assert (task.base_ahead, task.base_behind) == (2, 1) and not task.integrated
    assert found["origin/main"].remote and found["origin/main"].upstream is None
    assert next(iter(read.branches(repo_of(path), "main"))).name == "main"  # current first

    sh(path, "merge", "-q", "--no-ff", "agentic/T-1", "-m", "merge")
    merged = {b.name: b for b in read.branches(repo_of(path), "main")}
    assert merged["agentic/T-1"].integrated and merged["agentic/T-1"].base_ahead == 0


def test_branches_without_a_base_branch_still_list(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    for base in (None, "no-existe"):
        listed = read.branches(repo_of(path), base)
        assert [b.name for b in listed] == ["main"] and listed[0].base_ahead is None


# ------------------------------------------------------------------------------- blame
def test_blame_groups_consecutive_lines_by_commit(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    first = commit_file(path, "f.txt", "uno\ndos\ntres\n", message="primero")
    second = commit_file(path, "f.txt", "uno\nDOS\nDOS2\ntres\n", message="segundo")

    groups = read.blame(repo_of(path), "f.txt")

    assert [(g.start, g.lines, g.sha, g.summary) for g in groups] == [
        (1, 1, first, "primero"),
        (2, 2, second, "segundo"),
        (4, 1, first, "primero"),
    ]
    assert groups[1].text == ["DOS", "DOS2"] and groups[0].author == "Test"
    old = read.blame(repo_of(path), "f.txt", rev=first)
    assert [(g.start, g.lines) for g in old] == [(1, 3)]


# ------------------------------------------------------------------------------- errors
@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("fatal: Authentication failed for 'https://x'", "auth_failed"),
        (
            "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
            "auth_failed",
        ),
        ("fatal: unable to access 'https://x/': Could not resolve host: x", "network"),
        (" ! [rejected] main -> main (non-fast-forward)", "non_fast_forward"),
        ("CONFLICT (content): Merge conflict in a.txt", "conflicts"),
        (
            "error: Your local changes to the following files would be overwritten by checkout",
            "dirty_worktree",
        ),
        ("fatal: 'feature' is already checked out at 'D:/x'", "branch_checked_out"),
        ("fatal: not a git repository (or any of the parent directories): .git", "not_a_repo"),
        ("fatal: ambiguous something odd", "git_failed"),
    ],
)
def test_failures_are_classified(text: str, code: str):
    assert classify(text) == code


def test_a_failing_command_raises_a_classified_error(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    with pytest.raises(GitxError) as error:
        repo_of(path).run("checkout", "no-existe")
    assert error.value.code == "unknown_ref" and "no-existe" in error.value.output
    outside = tmp_path / "fuera"
    outside.mkdir()
    with pytest.raises(GitxError) as not_repo:
        repo_of(outside).run("status")
    assert not_repo.value.code == "not_a_repo"
    assert repo_of(path).attempt("rev-parse", "--verify", "-q", "ghost") is None
