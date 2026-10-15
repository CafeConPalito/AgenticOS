"""Diffs of runs and tasks on real temporary git repositories (phase 11, ADR 0015)."""

from __future__ import annotations

import itertools
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from test_scheduler import db_factory, make_agent  # noqa: F401 - pytest fixture
from test_worktrees import make_repo, make_task, sh

from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.errors import NotFound
from agentic_os.models import Project, Run, RunStatus, Task, WorkspaceMode
from agentic_os.services import changes, snapshots
from agentic_os.services import tasks as task_ops
from agentic_os.services.worktrees import Worktrees

COUNTER = itertools.count()


def commit(folder: Path, message: str) -> str:
    sh(folder, "add", "-A")
    sh(folder, "-c", "user.name=Dev", "-c", "user.email=dev@example.com", "commit", "-m", message)
    return sh(folder, "rev-parse", "HEAD")


def write(folder: Path, name: str, text: str | bytes) -> None:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, "utf-8")


def between(repo: Path, old: str, new: str) -> changes.Range:
    return changes.Range("ok", str(repo), old, new)


def by_path(rng: changes.Range) -> dict:
    return {f.path: f for f in changes.file_list(rng)}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "mi web")


# ---------------------------------------------------------------- file lists and diffs
def test_file_list_statuses_binaries_renames_and_generated(repo: Path):
    write(repo, "src/app.py", "uno\ndos\ntres\n")
    write(repo, "lock/uv.lock", "a\n")
    write(repo, "dist/bundle.js", "x\n")
    write(repo, "logo.png", b"\x00\x01\x02")
    write(repo, "viejo.txt", "contenido largo del fichero\notra linea\n")
    old = commit(repo, "base")
    write(repo, "src/app.py", "uno\nDOS\ntres\ncuatro\n")  # 2 added, 1 deleted
    write(repo, "logo.png", b"\x00\x01\x02\x03\x04")
    (repo / "lock" / "uv.lock").unlink()
    sh(repo, "mv", "viejo.txt", "nuevo.txt")
    write(repo, "README.md", "hola\nmas\n")
    write(repo, "dist/bundle.js", "y\n")
    write(repo, "extra.txt", "nuevo\n")
    new = commit(repo, "cambios")

    files = by_path(between(repo, old, new))

    assert files["src/app.py"].status == "modified"
    assert (files["src/app.py"].additions, files["src/app.py"].deletions) == (2, 1)
    assert files["extra.txt"].status == "added" and files["extra.txt"].additions == 1
    assert files["lock/uv.lock"].status == "deleted" and files["lock/uv.lock"].generated
    assert files["lock/uv.lock"].deletions == 1
    assert files["dist/bundle.js"].generated and not files["src/app.py"].generated
    renamed = files["nuevo.txt"]
    assert renamed.status == "renamed" and renamed.old_path == "viejo.txt"
    assert (renamed.additions, renamed.deletions) == (0, 0)
    logo = files["logo.png"]
    assert logo.binary and (logo.old_size, logo.new_size) == (3, 5)
    assert logo.additions == 0


def test_a_file_that_only_changes_line_endings_is_not_a_change(repo: Path):
    sh(repo, "config", "core.autocrlf", "false")
    write(repo, "f.txt", "a\nb\nc\n")
    old = commit(repo, "base")
    write(repo, "f.txt", b"a\r\nb\r\nc\r\n")
    write(repo, "g.txt", "x\n")
    new = commit(repo, "crlf")

    assert list(by_path(between(repo, old, new))) == ["g.txt"]


def test_changes_header_totals_and_truncation(repo: Path, monkeypatch: pytest.MonkeyPatch):
    old = sh(repo, "rev-parse", "HEAD")
    for index in range(5):
        write(repo, f"f{index}.txt", "a\nb\n")
    new = commit(repo, "cinco")
    monkeypatch.setattr(changes, "MAX_FILES", 3)

    result = changes.changes(between(repo, old, new))

    assert result.state == "ok"
    assert (result.totals.files, result.totals.additions) == (5, 10)  # totals count them all
    assert len(result.files) == 3 and result.truncated_files == 2


def test_the_summary_of_a_range_matches_the_file_list(repo: Path):
    old = sh(repo, "rev-parse", "HEAD")
    write(repo, "a.txt", "1\n2\n")
    write(repo, "logo.png", b"\x00\x01")
    write(repo, "README.md", "otro\n")
    new = commit(repo, "x")

    summary = changes.totals(str(repo), old, new)

    assert summary == changes.Totals(files=3, additions=3, deletions=1)


def test_file_diff_hunks_and_line_numbers(repo: Path):
    write(repo, "app.py", "".join(f"linea {n}\n" for n in range(1, 21)))
    old = commit(repo, "base")
    lines = [f"linea {n}\n" for n in range(1, 21)]
    lines[1] = "LINEA 2\n"
    lines.insert(15, "nueva\n")
    write(repo, "app.py", "".join(lines))
    new = commit(repo, "edit")

    diff = changes.file_diff(between(repo, old, new), "app.py")

    assert len(diff.hunks) == 2 and not diff.binary and not diff.too_large
    first = diff.hunks[0]
    kinds = [(line.kind, line.old_no, line.new_no, line.text) for line in first.lines]
    assert ("del", 2, None, "linea 2") in kinds
    assert ("add", None, 2, "LINEA 2") in kinds
    assert ("context", 1, 1, "linea 1") in kinds
    second = diff.hunks[1]
    added = [line for line in second.lines if line.kind == "add"]
    assert [line.text for line in added] == ["nueva"] and added[0].new_no == 16
    assert second.new_start <= 16 < second.new_start + second.new_lines


def test_file_diff_of_a_new_and_a_deleted_file(repo: Path):
    old = sh(repo, "rev-parse", "HEAD")
    write(repo, "nuevo.txt", "a\nb\n")
    (repo / "README.md").unlink()
    new = commit(repo, "x")
    rng = between(repo, old, new)

    added = changes.file_diff(rng, "nuevo.txt").hunks[0]
    assert (added.old_start, added.old_lines, added.new_start, added.new_lines) == (0, 0, 1, 2)
    assert [line.kind for line in added.lines] == ["add", "add"]
    deleted = changes.file_diff(rng, "README.md").hunks[0]
    assert [line.kind for line in deleted.lines] == ["del"] and deleted.lines[0].old_no == 1


def test_file_diff_of_a_rename_needs_the_old_path(repo: Path):
    write(repo, "viejo.txt", "".join(f"l{n}\n" for n in range(10)))
    old = commit(repo, "base")
    sh(repo, "mv", "viejo.txt", "nuevo.txt")
    write(repo, "nuevo.txt", "".join(f"l{n}\n" for n in range(10)) + "extra\n")
    new = commit(repo, "rename")
    rng = between(repo, old, new)

    diff = changes.file_diff(rng, "nuevo.txt", "viejo.txt")

    assert [line.text for h in diff.hunks for line in h.lines if line.kind != "context"] == [
        "extra"
    ]


def test_binary_and_too_large_diffs_have_no_content(repo: Path, monkeypatch: pytest.MonkeyPatch):
    write(repo, "logo.png", b"\x00\x01")
    write(repo, "grande.txt", "x\n")
    old = commit(repo, "base")
    write(repo, "logo.png", b"\x00\x02\x03")
    write(repo, "grande.txt", "".join(f"{n}\n" for n in range(200)))
    new = commit(repo, "x")
    rng = between(repo, old, new)

    assert changes.file_diff(rng, "logo.png").binary
    monkeypatch.setattr(changes, "MAX_DIFF_LINES", 50)
    big = changes.file_diff(rng, "grande.txt")
    assert big.too_large and big.hunks == []


def test_a_path_that_did_not_change_or_is_a_glob_is_not_found(repo: Path):
    write(repo, "a.txt", "1\n")
    write(repo, "intacto.txt", "secreto\n")
    old = commit(repo, "base")
    write(repo, "a.txt", "2\n")
    new = commit(repo, "x")
    rng = between(repo, old, new)

    for path in ("intacto.txt", "*.txt", ":(glob)**", "../fuera.txt", "no-existe"):
        with pytest.raises(NotFound):
            changes.file_diff(rng, path)
        with pytest.raises(NotFound):
            changes.file_lines(rng, path, 1, 5)


def test_file_lines_widen_the_context(repo: Path):
    write(repo, "app.py", "".join(f"linea {n}\n" for n in range(1, 11)))
    old = commit(repo, "base")
    write(repo, "app.py", "".join(f"linea {n}\n" for n in range(1, 11)) + "once\n")
    new = commit(repo, "x")
    rng = between(repo, old, new)

    result = changes.file_lines(rng, "app.py", 3, 5)

    assert [(line.new_no, line.text, line.kind) for line in result.lines] == [
        (3, "linea 3", "context"),
        (4, "linea 4", "context"),
        (5, "linea 5", "context"),
    ]
    assert all(line.old_no is None for line in result.lines)
    assert changes.file_lines(rng, "app.py", 11, 500).lines[0].text == "once"  # clipped to the end
    (repo / "app.py").unlink()
    gone = commit(repo, "borra")
    assert changes.file_lines(between(repo, old, gone), "app.py", 1, 5).lines == []


def test_the_diff_of_a_crlf_file_hides_the_carriage_returns(repo: Path):
    sh(repo, "config", "core.autocrlf", "false")
    write(repo, "f.txt", b"a\r\nb\r\n")
    old = commit(repo, "base")
    write(repo, "f.txt", b"a\r\nB\r\n")
    new = commit(repo, "x")

    diff = changes.file_diff(between(repo, old, new), "f.txt")

    assert all("\r" not in line.text for h in diff.hunks for line in h.lines)


# ---------------------------------------------------------------- ranges from the database
def make_run(
    db: Session,
    project: Project,
    cwd: Path,
    task: Task | None = None,
    status: str = RunStatus.EXITED,
    start: str | None = None,
    end: str | None = None,
    stage_id: str | None = None,
) -> Run:
    run = Run(
        workspace_id=DEFAULT_WORKSPACE,
        agent_name="Dev",
        agent_color="#fff",
        project_name=project.name,
        cli="claude",
        prompt="p",
        cwd=str(cwd),
        project_id=project.id,
        task_id=task.id if task else None,
        stage_id=stage_id,
        status=status,
        snapshot_start=start,
        snapshot_end=end,
        created_at=utcnow() + timedelta(seconds=next(COUNTER)),
    )
    db.add(run)
    db.flush()
    return run


def run_in(db: Session, project: Project, folder: Path, task: Task | None, steps) -> Run:
    """A finished run: snapshots around `steps(folder)`, like the RunManager takes them."""
    run = make_run(db, project, folder, task)
    start = snapshots.take(str(folder), run.id, "start")
    steps(folder)
    end = snapshots.take(str(folder), run.id, "end")
    run.snapshot_start, run.snapshot_end = start.sha, end.sha
    summary = changes.totals(str(folder), start.sha, end.sha)
    run.changes_files, run.changes_added, run.changes_deleted = (
        summary.files,
        summary.additions,
        summary.deletions,
    )
    db.flush()
    return run


def numstat(repo: Path, old: str, new: str) -> set[tuple[str, int, int]]:
    out = sh(repo, "diff", "--numstat", old, new)
    return {
        (path, int(added), int(deleted))
        for added, deleted, path in (line.split("\t") for line in out.splitlines())
    }


def listed(result: changes.Changes) -> set[tuple[str, int, int]]:
    return {(f.path, f.additions, f.deletions) for f in result.files}


def test_a_worktree_task_matches_git_diff_even_after_the_worktree_is_gone(
    db_factory,  # noqa: F811
    tmp_path: Path,
):
    repo = make_repo(tmp_path / "mi web")
    worktrees = Worktrees()
    with db_factory() as db:
        project, task = make_task(db, repo)
        path = Path(worktrees.prepare(db, task, project))
        base = sh(repo, "rev-parse", "main")
        assert task.base_commit == base

        def dev(folder: Path) -> None:
            write(folder, "api.py", "def login():\n    return 1\n")
            commit(folder, "feat: login")
            write(folder, "ui.py", "pendiente\n")  # left uncommitted

        run_in(db, project, path, task, dev)
        worktrees.release(db, task, project)  # commits the leftovers and removes the folder
        assert not path.exists()

        result = changes.changes(changes.task_range(db, task))

        assert result.state == "ok" and not result.live and not result.direct_folder
        assert result.from_ref.kind == "base" and result.to_ref.kind == "branch"
        assert result.to_ref.name == task.branch
        expected = numstat(repo, base, task.branch)
        assert listed(result) == expected == {("api.py", 2, 0), ("ui.py", 1, 0)}


def test_each_run_only_shows_what_it_changed(db_factory, tmp_path: Path):  # noqa: F811
    repo = make_repo(tmp_path / "mi web")
    worktrees = Worktrees()
    with db_factory() as db:
        project, task = make_task(db, repo)
        path = Path(worktrees.prepare(db, task, project))

        def first(folder: Path) -> None:
            write(folder, "a.py", "a\n")
            commit(folder, "feat: a")  # committed in the middle of the run…
            write(folder, "b.py", "b1\n")  # …and work left uncommitted

        def second(folder: Path) -> None:
            write(folder, "b.py", "b1\nb2\n")  # continues the uncommitted work
            write(folder, "c.py", "c\n")

        one = run_in(db, project, path, task, first)
        two = run_in(db, project, path, task, second)

        run1 = changes.changes(changes.run_range(db, one))
        run2 = changes.changes(changes.run_range(db, two))

        assert listed(run1) == {("a.py", 1, 0), ("b.py", 1, 0)}
        assert listed(run2) == {("b.py", 1, 0), ("c.py", 1, 0)}
        whole = changes.changes(changes.task_range(db, task))
        assert listed(whole) == {("a.py", 1, 0), ("b.py", 2, 0), ("c.py", 1, 0)}
        assert [r.attempt for r in whole.runs] == [1, 2]  # no stage: one group
        assert whole.runs[0].totals.files == 2 and whole.runs[1].totals.files == 2


def test_a_direct_folder_task_leaves_out_what_the_user_had_before(
    db_factory,  # noqa: F811
    tmp_path: Path,
):
    repo = make_repo(tmp_path / "mi web")
    write(repo, "notas.md", "mias\n")  # the user's own uncommitted work, before the agent
    with db_factory() as db:
        project = Project(
            workspace_id=DEFAULT_WORKSPACE,
            name="Web",
            path=str(repo),
            path_key=str(repo),
            workspace_mode=WorkspaceMode.DIRECT,
        )
        db.add(project)
        db.flush()
        task = task_ops.create_task(db, project, "Login", agent_id=make_agent(db).id)

        def dev(folder: Path) -> None:
            write(folder, "api.py", "x\n")
            commit(folder, "feat: api")  # this also commits the user's notas.md...
            write(folder, "ui.py", "y\n")  # ...but it was already in the starting snapshot

        run_in(db, project, repo, task, dev)

        result = changes.changes(changes.task_range(db, task))

        assert result.direct_folder and result.from_ref.kind == "task_start"
        assert listed(result) == {("api.py", 1, 0), ("ui.py", 1, 0)}  # no notas.md
        only_run = changes.changes(changes.run_range(db, db.query(Run).one()))
        assert listed(only_run) == listed(result)


def test_a_live_run_shows_the_folder_as_it_is_now(db_factory, tmp_path: Path):  # noqa: F811
    repo = make_repo(tmp_path / "mi web")
    with db_factory() as db:
        project, _task = make_task(db, repo)
        start = snapshots.take(str(repo), "r1", "start")
        run = make_run(db, project, repo, status=RunStatus.RUNNING, start=start.sha)
        write(repo, "ahora.txt", "sin commitear\n")

        result = changes.changes(changes.run_range(db, run))

        assert result.live and result.to_ref.kind == "now"
        assert listed(result) == {("ahora.txt", 1, 0)}


def test_an_interrupted_run_is_marked_partial(db_factory, tmp_path: Path):  # noqa: F811
    repo = make_repo(tmp_path / "mi web")
    with db_factory() as db:
        project, _task = make_task(db, repo)
        start = snapshots.take(str(repo), "r1", "start")
        end = snapshots.take(str(repo), "r1", "end")
        run = make_run(
            db, project, repo, status=RunStatus.INTERRUPTED, start=start.sha, end=end.sha
        )

        assert changes.run_range(db, run).partial


def test_states_without_data(db_factory, tmp_path: Path):  # noqa: F811
    repo = make_repo(tmp_path / "mi web")
    plain = tmp_path / "sin git"
    plain.mkdir()
    with db_factory() as db:
        project, task = make_task(db, repo)
        plain_project = Project(
            workspace_id=DEFAULT_WORKSPACE,
            name="Plano",
            path=str(plain),
            path_key=str(plain),
            workspace_mode=WorkspaceMode.DIRECT,
        )
        db.add(plain_project)
        db.flush()

        old_run = make_run(db, project, repo)  # from before the phase: no snapshots
        assert changes.run_range(db, old_run).state == "no_snapshots"
        no_git = make_run(db, plain_project, plain)
        assert changes.run_range(db, no_git).state == "no_git"

        gone = make_run(db, project, repo, start="1" * 40, end="2" * 40)  # purged or re-cloned
        assert changes.run_range(db, gone).state == "snapshot_missing"
        assert changes.changes(changes.run_range(db, gone)).files == []

        # a direct task with runs from before the phase
        assert changes.task_range(db, task).state in {"no_snapshots", "snapshot_missing", "ok"}


def test_a_task_from_before_the_phase_uses_the_merge_base(db_factory, tmp_path: Path):  # noqa: F811
    repo = make_repo(tmp_path / "mi web")
    with db_factory() as db:
        _project, task = make_task(db, repo)
        sh(repo, "checkout", "-q", "-b", "agentic/T-1")
        write(repo, "api.py", "x\n")
        commit(repo, "feat")
        sh(repo, "checkout", "-q", "main")
        write(repo, "otro.txt", "main avanza\n")  # the base moved on meanwhile
        commit(repo, "main")
        task.branch, task.base_commit = "agentic/T-1", None

        result = changes.changes(changes.task_range(db, task))

        assert result.state == "ok"
        assert listed(result) == {("api.py", 1, 0)}  # not otro.txt


def test_task_totals_for_the_inbox(db_factory, tmp_path: Path):  # noqa: F811
    repo = make_repo(tmp_path / "mi web")
    worktrees = Worktrees()
    with db_factory() as db:
        project, task = make_task(db, repo)
        assert changes.task_totals(db, task) is None  # no worktree yet
        path = Path(worktrees.prepare(db, task, project))
        run_in(db, project, path, task, lambda folder: write(folder, "a.py", "1\n2\n"))

        totals = changes.task_totals(db, task)

        assert totals is not None
        assert (totals.files, totals.additions, totals.deletions) == (1, 2, 0)
