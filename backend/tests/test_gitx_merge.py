"""Merge, rebase, cherry-pick, revert, reset, conflicts and «Deshacer» on real repositories
(phase 12, bloque 3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitrepos import commit_file, make_repo, sh, write
from test_repos import project_in
from test_scheduler import db_factory  # noqa: F401 - pytest fixture

from agentic_os.services import repos
from agentic_os.services.gitx import merge, oplog, read
from agentic_os.services.gitx.errors import GitxError
from agentic_os.services.gitx.runner import Repo


def repo_of(path: Path) -> Repo:
    return Repo(str(path))


def subjects(path: Path, ref: str = "HEAD", count: int = 10) -> list[str]:
    return sh(path, "log", "--format=%s", f"-{count}", ref).splitlines()


@pytest.fixture
def trunk(tmp_path: Path) -> Path:
    """main with a base commit, and `feature` with two commits of its own."""
    path = make_repo(tmp_path / "web", files={"a.txt": "base\n"})
    sh(path, "checkout", "-q", "-b", "feature")
    commit_file(path, "f1.txt", "1\n", message="feature 1")
    commit_file(path, "f2.txt", "2\n", message="feature 2")
    sh(path, "checkout", "-q", "main")
    return path


def conflicting(path: Path) -> None:
    """main and `clash` both change a.txt."""
    sh(path, "checkout", "-q", "-b", "clash", "main")
    commit_file(path, "a.txt", "clash\n", message="clash edit")
    sh(path, "checkout", "-q", "main")
    commit_file(path, "a.txt", "main\n", message="main edit")


# ------------------------------------------------------------------------------- merge
def test_merge_with_a_commit_fast_forward_or_squash(trunk: Path):
    repo = repo_of(trunk)
    commit_file(trunk, "m.txt", "m\n", message="main moves")  # so it is not a fast-forward

    done = merge.merge(repo, "feature", "no_ff", "Merge feature")
    assert done.status == "done"
    assert (
        subjects(trunk)[0] == "Merge feature"
        and len(sh(trunk, "rev-list", "--parents", "-1", "HEAD").split()) == 3
    )

    sh(trunk, "reset", "-q", "--hard", "HEAD~1")
    sh(trunk, "checkout", "-q", "-b", "straight", "feature~2")
    ff = merge.merge(repo, "feature", "ff")
    assert ff.status == "done" and sh(trunk, "rev-parse", "HEAD") == sh(
        trunk, "rev-parse", "feature"
    )

    sh(trunk, "checkout", "-q", "main")
    squashed = merge.merge(repo, "feature", "squash")
    assert squashed.status == "squashed"
    assert {f.path for f in read.status(repo).staged} == {"f1.txt", "f2.txt"}
    assert subjects(trunk)[0] == "main moves"  # nothing committed yet


def test_merging_what_is_already_in_says_so(trunk: Path):
    repo = repo_of(trunk)
    merge.merge(repo, "feature", "ff")
    assert merge.merge(repo, "feature", "no_ff").status == "up_to_date"


def test_a_conflict_stops_the_merge_and_can_be_resolved(trunk: Path):
    conflicting(trunk)
    repo = repo_of(trunk)

    result = merge.merge(repo, "clash", "no_ff")

    assert result.status == "conflicts" and result.conflicts == ["a.txt"]
    status = read.status(repo)
    assert status.operation == "merge" and [f.path for f in status.conflicts] == ["a.txt"]

    detail = merge.conflict(repo, "a.txt")
    assert (detail.base, detail.ours, detail.theirs) == ("base\n", "main\n", "clash\n")
    assert "<<<<<<<" in (detail.merged or "") and not detail.binary
    assert detail.ours_label == "main" and detail.theirs_label

    with pytest.raises(GitxError) as early:
        merge.proceed(repo, "continue")
    assert early.value.code == "conflicts_unresolved"

    merge.resolve(repo, "a.txt", "main\nclash\n")
    assert read.status(repo).conflicts == []
    done = merge.proceed(repo, "continue")
    assert done.status == "done" and read.status(repo).operation is None
    assert (trunk / "a.txt").read_text("utf-8") == "main\nclash\n"
    assert len(sh(trunk, "rev-list", "--parents", "-1", "HEAD").split()) == 3


def test_abort_leaves_the_repository_as_it_was(trunk: Path):
    conflicting(trunk)
    repo = repo_of(trunk)
    before = sh(trunk, "rev-parse", "HEAD")
    merge.merge(repo, "clash", "no_ff")

    merge.proceed(repo, "abort")

    assert sh(trunk, "rev-parse", "HEAD") == before and read.status(repo).clean
    with pytest.raises(GitxError) as none:
        merge.proceed(repo, "abort")
    assert none.value.code == "no_operation"


def test_a_conflict_is_settled_by_taking_a_side_or_a_deleted_file(trunk: Path):
    conflicting(trunk)
    repo = repo_of(trunk)
    merge.merge(repo, "clash", "no_ff")

    merge.take(repo, "a.txt", "theirs")

    assert (trunk / "a.txt").read_text("utf-8") == "clash\n" and read.status(repo).conflicts == []
    merge.proceed(repo, "continue")

    # One side deletes the file the other edits.
    sh(trunk, "checkout", "-q", "-b", "gone", "main")
    sh(trunk, "rm", "-q", "a.txt")
    sh(trunk, "commit", "-q", "-m", "delete a")
    sh(trunk, "checkout", "-q", "main")
    commit_file(trunk, "a.txt", "edited again\n", message="edit a")
    result = merge.merge(repo, "gone", "no_ff")
    assert result.status == "conflicts"
    detail = merge.conflict(repo, "a.txt")
    assert detail.theirs is None and detail.ours == "edited again\n"
    merge.take(repo, "a.txt", "theirs")  # theirs deleted it
    assert not (trunk / "a.txt").exists()
    assert merge.proceed(repo, "continue").status == "done"


def test_a_file_without_conflict_is_not_found(trunk: Path):
    with pytest.raises(GitxError) as error:
        merge.conflict(repo_of(trunk), "a.txt")
    assert error.value.code == "not_conflicted"


# ------------------------------------------------------------------------------- rebase
def test_rebase_replays_the_branch_on_top(trunk: Path):
    repo = repo_of(trunk)
    commit_file(trunk, "m.txt", "m\n", message="main moves")
    sh(trunk, "checkout", "-q", "feature")

    result = merge.rebase(repo, "main")

    assert result.status == "done"
    assert subjects(trunk, count=4) == ["feature 2", "feature 1", "main moves", "init"]


def test_rebase_with_a_conflict_continues_after_resolving(trunk: Path):
    conflicting(trunk)
    sh(trunk, "checkout", "-q", "clash")
    repo = repo_of(trunk)

    result = merge.rebase(repo, "main")

    assert result.status == "conflicts" and result.conflicts == ["a.txt"]
    assert read.status(repo).operation == "rebase"
    merge.resolve(repo, "a.txt", "both\n")
    assert merge.proceed(repo, "continue").status == "done"
    assert subjects(trunk, count=3) == ["clash edit", "main edit", "init"]


def test_rebase_conflicts_can_be_skipped_or_aborted(trunk: Path):
    conflicting(trunk)
    sh(trunk, "checkout", "-q", "clash")
    repo = repo_of(trunk)
    before = sh(trunk, "rev-parse", "HEAD")

    merge.rebase(repo, "main")
    merge.proceed(repo, "abort")
    assert sh(trunk, "rev-parse", "HEAD") == before and read.status(repo).operation is None

    merge.rebase(repo, "main")
    merge.proceed(repo, "skip")  # drops the commit that does not apply
    assert subjects(trunk, count=2) == ["main edit", "init"]


# ------------------------------------------------------------------------------- picks, reset
def test_cherry_pick_and_revert(trunk: Path):
    repo = repo_of(trunk)
    first = sh(trunk, "rev-parse", "feature~1")

    picked = merge.cherry_pick(repo, [first])
    assert picked.status == "done" and (trunk / "f1.txt").exists()
    assert subjects(trunk)[0] == "feature 1"

    reverted = merge.revert(repo, [sh(trunk, "rev-parse", "HEAD")])
    assert reverted.status == "done" and not (trunk / "f1.txt").exists()
    assert subjects(trunk)[0] == 'Revert "feature 1"'


def test_cherry_pick_conflict_can_be_aborted(trunk: Path):
    conflicting(trunk)
    repo = repo_of(trunk)

    result = merge.cherry_pick(repo, [sh(trunk, "rev-parse", "clash")])

    assert result.status == "conflicts" and read.status(repo).operation == "cherry-pick"
    merge.proceed(repo, "abort")
    assert read.status(repo).clean


def test_reset_modes(trunk: Path):
    repo = repo_of(trunk)
    merge.merge(repo, "feature", "ff")
    write(trunk, "f2.txt", "2\nlocal\n")

    merge.reset(repo, "HEAD~1", "soft")
    assert [f.path for f in read.status(repo).staged] == ["f2.txt"]  # still staged
    merge.reset(repo, "HEAD", "mixed")
    assert read.status(repo).staged == []
    merge.reset(repo, "HEAD~1", "hard")
    assert not (trunk / "f1.txt").exists()  # tracked, so it went with the reset
    assert [f.path for f in read.status(repo).unstaged] == ["f2.txt"]  # untracked: left alone


# ------------------------------------------------------------------------------- interactive
def three_commits(tmp_path: Path) -> tuple[Path, list[str]]:
    path = make_repo(tmp_path / "web")
    shas = [commit_file(path, f"f{i}.txt", f"{i}\n", message=f"c{i}") for i in (1, 2, 3)]
    return path, shas


def test_interactive_rebase_reorders_squashes_rewords_and_drops(tmp_path: Path):
    path, (c1, c2, c3) = three_commits(tmp_path)
    repo = repo_of(path)
    base = sh(path, "rev-list", "--max-parents=0", "HEAD")

    offered = merge.plan(repo, base)
    assert [c.subject for c in offered] == ["c1", "c2", "c3"]

    result = merge.rebase_interactive(
        repo,
        base,
        [
            merge.TodoItem("pick", c3),
            merge.TodoItem("reword", c1, "primero\n\ncon cuerpo"),
            merge.TodoItem("drop", c2),
        ],
    )

    assert result.status == "done"
    assert subjects(path, count=3) == ["primero", "c3", "init"]
    assert read.commit_detail(repo, "HEAD").body == "con cuerpo"
    assert not (path / "f2.txt").exists()  # dropped


def test_interactive_rebase_fixup_and_edit(tmp_path: Path):
    path, (c1, c2, c3) = three_commits(tmp_path)
    repo = repo_of(path)
    base = sh(path, "rev-list", "--max-parents=0", "HEAD")

    folded = merge.rebase_interactive(
        repo,
        base,
        [merge.TodoItem("pick", c1), merge.TodoItem("fixup", c2), merge.TodoItem("pick", c3)],
    )
    assert folded.status == "done" and subjects(path, count=3) == ["c3", "c1", "init"]

    # `edit` stops after the commit, so it can be split.
    path2, (d1, d2, d3) = three_commits(tmp_path / "otro")
    repo2 = repo_of(path2)
    base2 = sh(path2, "rev-list", "--max-parents=0", "HEAD")
    paused = merge.rebase_interactive(
        repo2,
        base2,
        [merge.TodoItem("pick", d1), merge.TodoItem("edit", d2), merge.TodoItem("pick", d3)],
    )
    assert paused.status == "stopped" and read.status(repo2).operation == "rebase"
    assert subjects(path2)[0] == "c2"
    assert merge.proceed(repo2, "continue").status == "done"
    assert subjects(path2, count=4) == ["c3", "c2", "c1", "init"]


def test_interactive_rebase_refuses_a_stale_list_or_merges(tmp_path: Path):
    path, (c1, c2, c3) = three_commits(tmp_path)
    repo = repo_of(path)
    base = sh(path, "rev-list", "--max-parents=0", "HEAD")

    with pytest.raises(GitxError) as stale:
        merge.rebase_interactive(
            repo, base, [merge.TodoItem("pick", c1), merge.TodoItem("pick", c2)]
        )
    assert stale.value.code == "stale_rebase"
    with pytest.raises(GitxError) as first:
        merge.rebase_interactive(
            repo,
            base,
            [merge.TodoItem("squash", c1), merge.TodoItem("pick", c2), merge.TodoItem("pick", c3)],
        )
    assert first.value.code == "bad_rebase"

    sh(path, "checkout", "-q", "-b", "side", c1)
    commit_file(path, "s.txt", "s\n", message="side")
    sh(path, "checkout", "-q", "main")
    sh(path, "merge", "-q", "--no-ff", "side", "-m", "merge side")
    with pytest.raises(GitxError) as merges:
        merge.plan(repo, base)
    assert merges.value.code == "rebase_has_merges"


# ------------------------------------------------------------------------------- undo
@pytest.fixture
def tracked(db_factory, trunk: Path):  # noqa: F811
    """A project row for the repository, to hang operations from."""
    with db_factory() as db:
        project = project_in(db, trunk)
        (row,) = repos.sync(db, project)
        db.commit()
        yield db, row, repo_of(trunk), trunk


def test_undo_a_merge_puts_the_branch_back(tracked):
    db, row, repo, path = tracked
    commit_file(path, "m.txt", "m\n", message="main moves")
    before = sh(path, "rev-parse", "main")

    operation = oplog.begin(db, row, repo, "merge", "Merge feature")
    merge.merge(repo, "feature", "no_ff")
    oplog.finish(operation, repo)
    assert sh(path, "rev-parse", "main") != before
    assert oplog.last_undoable(db, row.id) is operation

    oplog.undo(operation, repo)

    assert sh(path, "rev-parse", "main") == before and read.status(repo).clean
    assert not (path / "f1.txt").exists() and operation.undone_at is not None
    assert oplog.last_undoable(db, row.id) is None
    with pytest.raises(GitxError) as twice:
        oplog.undo(operation, repo)
    assert twice.value.code == "already_undone"


def test_undo_a_hard_reset_brings_back_the_lost_files(tracked):
    db, row, repo, path = tracked
    head = sh(path, "rev-parse", "HEAD")
    commit_file(path, "keep.txt", "k\n", message="a commit")
    write(path, "keep.txt", "k\nunsaved work\n")  # uncommitted
    write(path, "scratch.txt", "never committed\n")
    sh(path, "add", "scratch.txt")

    operation = oplog.begin(db, row, repo, "reset", "Reset duro", worktree=True)
    merge.reset(repo, head, "hard")
    oplog.finish(operation, repo)
    assert not (path / "keep.txt").exists()

    oplog.undo(operation, repo)

    assert (path / "keep.txt").read_text("utf-8") == "k\nunsaved work\n"
    assert (path / "scratch.txt").read_text("utf-8") == "never committed\n"
    assert sh(path, "log", "-1", "--format=%s") == "a commit"


def test_undo_a_deleted_branch_and_a_rebase(tracked):
    db, row, repo, path = tracked
    feature = sh(path, "rev-parse", "feature")

    deleting = oplog.begin(db, row, repo, "delete_branch", "Borrar feature")
    sh(path, "branch", "-D", "feature")
    oplog.finish(deleting, repo)
    oplog.undo(deleting, repo)
    assert sh(path, "rev-parse", "feature") == feature

    commit_file(path, "m.txt", "m\n", message="main moves")
    sh(path, "checkout", "-q", "feature")
    old_tip = sh(path, "rev-parse", "HEAD")
    rebasing = oplog.begin(db, row, repo, "rebase", "Rebase")
    merge.rebase(repo, "main")
    oplog.finish(rebasing, repo)
    assert sh(path, "rev-parse", "HEAD") != old_tip
    oplog.undo(rebasing, repo)
    assert sh(path, "rev-parse", "HEAD") == old_tip and read.status(repo).clean


def test_undo_is_refused_when_the_branch_moved_since(tracked):
    db, row, repo, path = tracked
    operation = oplog.begin(db, row, repo, "merge", "Merge")
    merge.merge(repo, "feature", "ff")
    oplog.finish(operation, repo)
    commit_file(path, "later.txt", "l\n", message="work after the merge")

    assert oplog.blocker(operation, repo) == "moved_since"
    with pytest.raises(GitxError) as refused:
        oplog.undo(operation, repo)
    assert refused.value.code == "moved_since"
    assert (path / "later.txt").exists()  # nothing was touched


def test_undo_waits_for_a_half_done_operation(tracked):
    db, row, repo, path = tracked
    conflicting(path)
    operation = oplog.begin(db, row, repo, "merge", "Merge")
    merge.merge(repo, "clash", "no_ff")
    oplog.finish(operation, repo)

    assert oplog.blocker(operation, repo) == "operation_in_progress"


def test_an_operation_that_changed_nothing_leaves_no_entry(tracked):
    db, row, repo, _path = tracked
    operation = oplog.begin(db, row, repo, "merge", "Nada")

    assert oplog.drop_if_unchanged(db, operation, repo)
    db.flush()
    assert oplog.recent(db, row.id) == []


def test_recent_operations_come_newest_first(tracked):
    db, row, repo, path = tracked
    for label in ("uno", "dos", "tres"):
        operation = oplog.begin(db, row, repo, "merge", label)
        commit_file(path, f"{label}.txt", "x\n", message=label)
        oplog.finish(operation, repo)
        db.flush()
    assert next(iter(oplog.recent(db, row.id))).label == "tres"
