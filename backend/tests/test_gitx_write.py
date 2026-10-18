"""Changing a repository from the Git tab: staging by file, hunk and line, commits, branches
(phase 12, bloque 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitrepos import commit_file, make_repo, sh, write

from agentic_os.services.gitx import read
from agentic_os.services.gitx import write as ops
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo
from agentic_os.services.gitx.write import LineRef

TEN = "".join(f"l{i}\n" for i in range(1, 31))  # three hunks apart: lines 2, 15 and 29


def edited() -> str:
    lines = TEN.splitlines(keepends=True)
    lines[1] = "L2\n"
    lines[14] = "L15\n"
    lines[28] = "L29\n"
    return "".join(lines)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "web", files={"f.txt": TEN, "g.txt": "g\n"})


def cached(path: Path, name: str = "f.txt") -> str:
    return sh(path, "diff", "--cached", "--unified=0", "--", name)


def worktree(path: Path, name: str = "f.txt") -> str:
    return sh(path, "diff", "--unified=0", "--", name)


def changed_lines(diff: str) -> list[str]:
    return [
        line for line in diff.splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---")
    ]


# ------------------------------------------------------------------------------- by file
def test_stage_and_unstage_whole_files(path: Path):
    write(path, "f.txt", edited())
    write(path, "nuevo.txt", "n\n")
    (path / "g.txt").unlink()
    repo = Repo(str(path))

    ops.stage(repo, ["f.txt", "nuevo.txt", "g.txt"])
    status = read.status(repo)
    assert {(f.path, f.status) for f in status.staged} == {
        ("f.txt", "M"),
        ("nuevo.txt", "A"),
        ("g.txt", "D"),
    }
    assert status.unstaged == []

    ops.unstage(repo, ["nuevo.txt", "g.txt"])
    status = read.status(repo)
    assert [f.path for f in status.staged] == ["f.txt"]
    assert {(f.path, f.status) for f in status.unstaged} == {("nuevo.txt", "?"), ("g.txt", "D")}


def test_paths_are_literal_never_globs(path: Path):
    write(path, "a.txt", "1\n")
    write(path, "b.txt", "2\n")
    repo = Repo(str(path))

    with pytest.raises(GitxError) as error:  # no file is called "*.txt": it is not a pattern
        ops.stage(repo, ["*.txt"])

    assert error.value.code == "unknown_ref" and read.status(repo).staged == []


def test_discard_restores_tracked_files_and_removes_untracked_ones(path: Path):
    write(path, "f.txt", edited())
    write(path, "nuevo.txt", "n\n")
    sh(path, "add", "f.txt")
    repo = Repo(str(path))

    ops.discard(repo, ["f.txt"], ["nuevo.txt"])

    assert read.status(repo).clean
    assert (path / "f.txt").read_text("utf-8") == TEN and not (path / "nuevo.txt").exists()


# ------------------------------------------------------------------------------- by hunk
def hunk_starts(path: Path, cached_side: bool = False) -> list[tuple[int, int]]:
    args = ["diff", "-U3", "--no-color"] + (["--cached"] if cached_side else []) + ["--", "f.txt"]
    raw = Repo(str(path)).run_raw(*args)
    return [(h.old_start, h.new_start) for h in ops.split_diff(raw)[1]]


def test_stage_only_one_hunk(path: Path):
    write(path, "f.txt", edited())
    starts = hunk_starts(path)
    assert len(starts) == 3

    ops.apply_selection(Repo(str(path)), "stage", "f.txt", [starts[1]], [])

    assert changed_lines(cached(path)) == ["-l15", "+L15"]
    assert changed_lines(worktree(path)) == ["-l2", "+L2", "-l29", "+L29"]


def test_unstage_only_one_hunk(path: Path):
    write(path, "f.txt", edited())
    sh(path, "add", "f.txt")
    starts = hunk_starts(path, cached_side=True)

    ops.apply_selection(Repo(str(path)), "unstage", "f.txt", [starts[0], starts[2]], [])

    assert changed_lines(cached(path)) == ["-l15", "+L15"]
    assert changed_lines(worktree(path)) == ["-l2", "+L2", "-l29", "+L29"]


def test_discard_only_one_hunk(path: Path):
    write(path, "f.txt", edited())
    starts = hunk_starts(path)

    ops.apply_selection(Repo(str(path)), "discard", "f.txt", [starts[2]], [])

    content = (path / "f.txt").read_text("utf-8")
    assert "L2\n" in content and "L15\n" in content and "L29" not in content and "l29\n" in content


# ------------------------------------------------------------------------------- by line
def test_stage_single_lines_of_a_hunk(path: Path):
    write(path, "f.txt", "l1\nL2\nl3\nnueva\nl4\n" + "".join(f"l{i}\n" for i in range(5, 31)))
    # l2 → L2 (a deletion and an addition) and one added line "nueva" after l3.
    repo = Repo(str(path))

    ops.apply_selection(repo, "stage", "f.txt", [], [LineRef("add", 4)])  # only "nueva"

    assert changed_lines(cached(path)) == ["+nueva"]
    assert changed_lines(worktree(path)) == ["-l2", "+L2"]

    ops.apply_selection(repo, "stage", "f.txt", [], [LineRef("del", 2), LineRef("add", 2)])
    assert changed_lines(cached(path)) == ["-l2", "+L2", "+nueva"]
    assert worktree(path) == ""


def test_unstage_and_discard_single_lines(path: Path):
    write(path, "f.txt", "l1\nL2\nl3\nnueva\nl4\n" + "".join(f"l{i}\n" for i in range(5, 31)))
    sh(path, "add", "f.txt")
    repo = Repo(str(path))

    ops.apply_selection(repo, "unstage", "f.txt", [], [LineRef("add", 4)])
    assert changed_lines(cached(path)) == ["-l2", "+L2"]
    assert changed_lines(worktree(path)) == ["+nueva"]

    ops.apply_selection(repo, "discard", "f.txt", [], [LineRef("add", 4)])
    assert worktree(path) == ""
    assert "nueva" not in (path / "f.txt").read_text("utf-8")
    assert changed_lines(cached(path)) == ["-l2", "+L2"]  # the staged part is untouched


def test_picking_lines_keeps_crlf_line_endings(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    sh(path, "config", "core.autocrlf", "false")
    (path / "w.txt").write_bytes(b"a\r\nb\r\nc\r\n")
    sh(path, "add", "w.txt")
    sh(path, "commit", "-q", "-m", "crlf")
    (path / "w.txt").write_bytes(b"a\r\nB\r\nc\r\nd\r\n")

    ops.apply_selection(Repo(str(path)), "stage", "w.txt", [], [LineRef("add", 4)])

    staged = Repo(str(path)).run_raw("show", ":w.txt")
    assert staged == b"a\r\nb\r\nc\r\nd\r\n"


def test_lines_at_the_end_of_a_file_without_a_final_newline(tmp_path: Path):
    path = make_repo(tmp_path / "web")
    (path / "n.txt").write_bytes(b"uno\ndos")
    sh(path, "add", "n.txt")
    sh(path, "commit", "-q", "-m", "sin salto")
    (path / "n.txt").write_bytes(b"uno\ndos\ntres")

    repo = Repo(str(path))
    _, hunks = ops.split_diff(repo.run_raw("diff", "-U3", "--", "n.txt"))
    added = [n for _l, kind, n in ops.numbered(hunks[0]) if kind == "add"]

    # A single line would leave a patch that contradicts itself: refused, nothing applied.
    with pytest.raises(GitxError) as partial:
        ops.apply_selection(repo, "stage", "n.txt", [], [LineRef("add", added[-1])])
    assert partial.value.code == "selection_unsupported" and cached(path, "n.txt") == ""

    # The whole hunk is fine.
    ops.apply_selection(repo, "stage", "n.txt", [(hunks[0].old_start, hunks[0].new_start)], [])
    assert repo.run_raw("show", ":n.txt") == b"uno\ndos\ntres"


def test_a_stale_selection_applies_nothing(path: Path):
    write(path, "f.txt", edited())
    repo = Repo(str(path))
    shown = hunk_starts(path)
    write(path, "f.txt", TEN)  # someone reverted the file after it was shown

    with pytest.raises(GitxError) as gone:
        ops.apply_selection(repo, "stage", "f.txt", [shown[0]], [])
    assert gone.value.code == "stale_diff"

    write(path, "f.txt", edited())
    with pytest.raises(GitxError) as moved:  # a line number that is not in the diff
        ops.apply_selection(repo, "stage", "f.txt", [], [LineRef("add", 99)])
    assert moved.value.code == "stale_diff"
    assert cached(path) == ""


def test_picking_inside_new_deleted_renamed_and_binary_files_is_refused(path: Path):
    repo = Repo(str(path))
    write(path, "nuevo.txt", "n\n")
    (path / "g.txt").unlink()
    sh(path, "mv", "f.txt", "h.txt")
    (path / "logo.png").write_bytes(b"\0\1\2")
    sh(path, "add", "logo.png")
    sh(path, "commit", "-q", "-m", "png")
    (path / "logo.png").write_bytes(b"\0\1\2\3")

    for name in ("nuevo.txt", "g.txt", "logo.png"):
        with pytest.raises(GitxError) as error:
            ops.apply_selection(repo, "stage", name, [(1, 1)], [])
        assert error.value.code in ("selection_unsupported", "stale_diff"), name
    with pytest.raises(GitxError) as nothing:
        write(path, "f2.txt", "x\n")
        ops.apply_selection(repo, "stage", "README.md", [], [])
    assert nothing.value.code == "stale_diff"  # README has no changes of that kind


# ------------------------------------------------------------------------------- commit
def test_commit_keeps_the_body_and_returns_the_sha(path: Path):
    repo = Repo(str(path))
    write(path, "g.txt", "g2\n")
    ops.stage(repo, ["g.txt"])

    sha = ops.commit(repo, "feat: algo\n\nCuerpo\ncon dos líneas")

    assert sha == sh(path, "rev-parse", "HEAD")
    detail = read.commit_detail(repo, sha)
    assert detail.subject == "feat: algo" and detail.body == "Cuerpo\ncon dos líneas"
    assert read.status(repo).clean


def test_amend_changes_the_message_or_keeps_it(path: Path):
    repo = Repo(str(path))
    write(path, "g.txt", "g2\n")
    ops.stage(repo, ["g.txt"])
    first = ops.commit(repo, "primero")

    write(path, "g.txt", "g3\n")
    ops.stage(repo, ["g.txt"])
    kept = ops.commit(repo, "", amend=True)
    assert read.commit_detail(repo, kept).subject == "primero" and kept != first

    reworded = ops.commit(repo, "segundo", amend=True)
    assert read.commit_detail(repo, reworded).subject == "segundo"
    assert sh(path, "rev-list", "--count", "HEAD") == "2"  # still one commit above the first


def test_commit_errors(path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = Repo(str(path))
    with pytest.raises(GitxError) as empty:
        ops.commit(repo, "   ")
    assert empty.value.code == "empty_message"
    with pytest.raises(GitxError) as nothing:
        ops.commit(repo, "nada")
    assert nothing.value.code == "nothing_to_commit"

    # A hook that refuses the commit, and the way past it.
    write(path, "g.txt", "g2\n")
    ops.stage(repo, ["g.txt"])
    hook = path / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'no se puede' >&2\nexit 1\n", "utf-8", newline="\n")
    with pytest.raises(GitxError) as refused:
        ops.commit(repo, "con hook")
    assert refused.value.code == "hook_failed" and "no se puede" in refused.value.output
    assert ops.commit(repo, "sin hook", no_verify=True)

    # No identity anywhere.
    empty_config = tmp_path / "gitconfig"
    empty_config.write_text("", "utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    anon = make_repo(tmp_path / "anon")
    sh(anon, "config", "--unset", "user.name")
    sh(anon, "config", "--unset", "user.email")
    write(anon, "x.txt", "x\n")
    ops.stage(Repo(str(anon)), ["x.txt"])
    with pytest.raises(GitxError) as who:
        ops.commit(Repo(str(anon)), "quién soy")
    assert who.value.code == "identity_missing"


# ------------------------------------------------------------------------------- branches
def test_create_switch_rename_and_delete_branches(path: Path):
    repo = Repo(str(path))

    ops.create_branch(repo, "feature/x")
    ops.create_branch(repo, "otra", start="main", switch=True)
    assert read.status(repo).branch == "otra"
    ops.switch_branch(repo, "main")
    assert read.status(repo).branch == "main"
    ops.rename_branch(repo, "otra", "tercera")
    assert {b.name for b in read.branches(repo)} == {"main", "feature/x", "tercera"}
    ops.delete_branch(repo, "tercera")
    assert "tercera" not in {b.name for b in read.branches(repo)}


def test_branch_errors_are_classified(path: Path):
    repo = Repo(str(path))
    with pytest.raises(GitxError) as bad:
        ops.create_branch(repo, "con espacios y ..")
    assert bad.value.code == "invalid_ref"
    ops.create_branch(repo, "dup")
    with pytest.raises(GitxError) as dup:
        ops.create_branch(repo, "dup")
    assert dup.value.code == "branch_exists"
    with pytest.raises(GitxError) as ghost:
        ops.switch_branch(repo, "no-existe")
    assert ghost.value.code == "unknown_ref"

    sh(path, "checkout", "-q", "dup")
    commit_file(path, "d.txt", "d\n")
    sh(path, "checkout", "-q", "main")
    with pytest.raises(GitxError) as unmerged:
        ops.delete_branch(repo, "dup")
    assert unmerged.value.code == "not_merged"
    ops.delete_branch(repo, "dup", force=True)  # the caller confirmed


def test_switching_with_changes_that_would_be_lost_is_refused(path: Path):
    repo = Repo(str(path))
    sh(path, "checkout", "-q", "-b", "otra")
    commit_file(path, "f.txt", "otra\n")
    sh(path, "checkout", "-q", "main")
    write(path, "f.txt", "cambio local\n")

    with pytest.raises(GitxError) as refused:
        ops.switch_branch(repo, "otra")

    assert refused.value.code == "dirty_worktree"
    assert (path / "f.txt").read_text("utf-8") == "cambio local\n"  # nothing was lost


def test_a_remote_branch_gets_a_local_one_that_follows_it(tmp_path: Path):
    from gitrepos import make_bare

    remote = make_bare(tmp_path / "remote.git")
    first = make_repo(tmp_path / "first")
    sh(first, "remote", "add", "origin", str(remote))
    sh(first, "push", "-q", "-u", "origin", "main")
    sh(first, "checkout", "-q", "-b", "compartida")
    commit_file(first, "c.txt", "c\n")
    sh(first, "push", "-q", "-u", "origin", "compartida")
    second = tmp_path / "second"
    sh(tmp_path, "clone", "-q", str(remote), str(second))
    repo = Repo(str(second))

    ops.switch_branch(repo, "origin/compartida")

    status = read.status(repo)
    assert (status.branch, status.upstream) == ("compartida", "origin/compartida")
    ops.set_upstream(repo, "compartida", None)
    assert read.status(repo).upstream is None
    ops.set_upstream(repo, "compartida", "origin/main")
    assert read.status(repo).upstream == "origin/main"
