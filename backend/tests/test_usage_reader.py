"""UsageService: live and final reads, Claude's status line, agy subagents, backfill."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.models import Run, RunStatus, UsageStatus
from agentic_os.services.usage.paths import claude_transcript
from agentic_os.services.usage.reader import UsageService

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"


@pytest.fixture
def db_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    yield make_sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def published() -> list[dict]:
    return []


@pytest.fixture
def service(db_factory, published, tmp_path: Path) -> UsageService:
    return UsageService(
        db_factory,
        publish=lambda run_id, message: published.append(message),
        claude_config_dir=tmp_path / "claude",
        home=tmp_path / "home",
    )


def make_run(db_factory, cli: str = "claude", **values) -> str:
    with db_factory() as db:
        run = Run(
            workspace_id=DEFAULT_WORKSPACE,
            agent_name="Dev",
            agent_color="#43D392",
            project_name="Web",
            cli=cli,
            prompt="hola",
            cwd=r"C:\proyectos\web",
            status=RunStatus.RUNNING,
            started_at=utcnow(),
            **values,
        )
        db.add(run)
        db.commit()
        return run.id


def get(db_factory, run_id: str) -> Run:
    with db_factory() as db:
        run = db.get(Run, run_id)
        db.expunge(run)
        return run


def without_cost_state(source: Path, target: Path) -> Path:
    rows = source.read_text("utf-8").splitlines()
    target.write_text("\n".join(r for r in rows if '"cost-state"' not in r) + "\n", "utf-8")
    return target


def test_claude_live_rows_then_status_line_then_exact_on_close(
    db_factory, service, published, tmp_path: Path
):
    transcript = without_cost_state(
        FIXTURES / "claude-2.1.296-two-turns.jsonl", tmp_path / "s.jsonl"
    )
    run_id = make_run(db_factory, transcript_path=str(transcript))

    service.request(run_id)  # end of a turn
    run = get(db_factory, run_id)
    assert run.usage_status == UsageStatus.PARTIAL
    assert run.usage_source == "assistant-rows"
    assert (run.output_tokens, run.cache_read_tokens, run.cost_usd) == (8, 62310, None)
    assert published[-1]["type"] == "usage"

    service.status_line(run_id, 0.0042495, "2.1.296")
    run = get(db_factory, run_id)
    assert run.cost_usd == pytest.approx(0.0042495)
    assert run.cli_version == "2.1.296"
    assert published[-1]["usage"]["cost_usd"] == pytest.approx(0.0042495)

    # The session closes: Claude writes its cost-state.
    rows = (FIXTURES / "claude-2.1.296-two-turns.jsonl").read_text("utf-8").splitlines()
    with transcript.open("a", encoding="utf-8") as file:
        file.write(next(r for r in rows if '"cost-state"' in r) + "\n")
    service.request(run_id, final=True)
    run = get(db_factory, run_id)
    assert run.usage_status == UsageStatus.FINAL
    assert run.usage_source == "cost-state"
    assert run.cost_usd == pytest.approx(0.00506875)
    assert run.input_tokens == 1678
    # A late status line does not undo the exact figures.
    service.status_line(run_id, 0.001, None)
    assert get(db_factory, run_id).cost_usd == pytest.approx(0.00506875)


def test_claude_closed_abruptly_keeps_the_status_line_cost(db_factory, service, tmp_path: Path):
    transcript = without_cost_state(
        FIXTURES / "claude-2.1.296-two-turns.jsonl", tmp_path / "s.jsonl"
    )
    run_id = make_run(db_factory, transcript_path=str(transcript))
    service.status_line(run_id, 0.0042495, "2.1.296")
    service.request(run_id, final=True)  # misses cost-state twice (retry included)
    run = get(db_factory, run_id)
    assert run.usage_status == UsageStatus.FINAL
    assert run.usage_source == "assistant-rows"
    assert run.cost_usd == pytest.approx(0.0042495)


def test_computed_claude_path_without_hooks(db_factory, service, tmp_path: Path):
    run_id = make_run(db_factory, cli_session_id="abc")
    path = claude_transcript(r"C:\proyectos\web", "abc", tmp_path / "claude")
    path.parent.mkdir(parents=True)
    shutil.copy(FIXTURES / "claude-2.1.296-two-turns.jsonl", path)
    service.request(run_id, final=True)
    run = get(db_factory, run_id)
    assert run.usage_source == "cost-state" and run.input_tokens == 1678


def test_agy_with_a_native_subagent(db_factory, service, tmp_path: Path):
    run_id = make_run(db_factory, cli="agy", cli_session_id="conv")
    service.note_transcript(run_id, str(FIXTURES / "agy-1.3.3-subagent-main.jsonl"), own=True)
    service.note_transcript(run_id, str(FIXTURES / "agy-1.3.3-subagent-child.jsonl"), own=False)
    service.note_transcript(run_id, str(FIXTURES / "agy-1.3.3-subagent-child.jsonl"), own=False)
    assert len(get(db_factory, run_id).extra_transcripts) == 1
    service.request(run_id, final=True)
    run = get(db_factory, run_id)
    assert run.usage_status == UsageStatus.FINAL
    assert (run.input_tokens, run.output_tokens, run.cost_usd) == (123455, 4142, None)


def test_nothing_to_read(db_factory, service, tmp_path: Path):
    run_id = make_run(db_factory, cli="agy", transcript_path=str(tmp_path / "missing.jsonl"))
    service.request(run_id)
    assert get(db_factory, run_id).usage_status == UsageStatus.PENDING
    service.request(run_id, final=True)
    assert get(db_factory, run_id).usage_status == UsageStatus.UNAVAILABLE
    assert service.refresh("no-such-run") is False


def test_backfill_reads_finished_runs_never_read(db_factory, service):
    finished = make_run(
        db_factory, cli="agy", transcript_path=str(FIXTURES / "agy-1.3.3-subagent-main.jsonl")
    )
    live = make_run(
        db_factory, cli="agy", transcript_path=str(FIXTURES / "agy-1.3.3-subagent-main.jsonl")
    )
    with db_factory() as db:
        db.get(Run, finished).status = RunStatus.COMPLETED
        db.commit()
    assert service.backfill() == 1
    assert get(db_factory, finished).usage_status == UsageStatus.FINAL
    assert get(db_factory, live).usage_status == UsageStatus.PENDING


def test_the_worker_thread(db_factory, service):
    run_id = make_run(
        db_factory, cli="agy", transcript_path=str(FIXTURES / "agy-1.3.3-subagent-main.jsonl")
    )
    service.start()
    try:
        service.request(run_id, final=True)
        assert service.wait_idle()
    finally:
        service.stop()
    assert get(db_factory, run_id).input_tokens == 90094


def test_the_retry_waits_without_blocking_the_worker(db_factory, service, tmp_path: Path):
    """A final Claude read without cost-state is retried 2 s later by a timer: meanwhile the
    worker reads other runs."""
    source = (FIXTURES / "claude-2.1.296-two-turns.jsonl").read_text("utf-8").splitlines()
    transcript = without_cost_state(
        FIXTURES / "claude-2.1.296-two-turns.jsonl", tmp_path / "s.jsonl"
    )
    claude = make_run(db_factory, transcript_path=str(transcript))
    agy = make_run(
        db_factory, cli="agy", transcript_path=str(FIXTURES / "agy-1.3.3-subagent-main.jsonl")
    )
    service.start()
    try:
        service.request(claude, final=True)
        service.request(agy, final=True)
        deadline = time.monotonic() + 1.5
        while get(db_factory, agy).usage_status != UsageStatus.FINAL:
            assert time.monotonic() < deadline, "the worker was blocked by the retry"
            time.sleep(0.05)
        assert get(db_factory, claude).usage_status == UsageStatus.PARTIAL
        with transcript.open("a", encoding="utf-8") as file:  # Claude finishes closing
            file.write(next(r for r in source if '"cost-state"' in r) + "\n")
        assert service.wait_idle()
    finally:
        service.stop()
    run = get(db_factory, claude)
    assert (run.usage_status, run.usage_source) == (UsageStatus.FINAL, "cost-state")


def test_stopping_leaves_the_backfill_for_the_next_start(db_factory, service):
    ids = []
    for _ in range(3):
        run_id = make_run(
            db_factory, cli="agy", transcript_path=str(FIXTURES / "agy-1.3.3-subagent-main.jsonl")
        )
        with db_factory() as db:
            db.get(Run, run_id).status = RunStatus.COMPLETED
            db.commit()
        ids.append(run_id)
    service._stopping.set()  # as if stop() had begun before the worker got to them
    service.start()
    service.backfill()
    service.stop()
    assert {get(db_factory, i).usage_status for i in ids} == {UsageStatus.PENDING}
