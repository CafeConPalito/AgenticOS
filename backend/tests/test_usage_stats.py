"""Usage aggregates, daily limits (with the scheduler) and «Cuota agotada»."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker
from test_scheduler import FakeLauncher, add_task, make_agent, make_project, status_of

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.models import (
    Agent,
    Cli,
    InboxItem,
    InboxKind,
    InboxStatus,
    Project,
    Run,
    RunStatus,
    Task,
    TaskStatus,
    WaitingReason,
)
from agentic_os.schemas.usage import UsageLimits
from agentic_os.services import tasks as task_ops
from agentic_os.services.runs.manager import RunManager
from agentic_os.services.runs.screen import ScreenState
from agentic_os.services.scheduler import Scheduler
from agentic_os.services.usage import limits, stats

TZ = timezone(timedelta(hours=2))  # Madrid in October
DAY = date(2026, 10, 12)


@pytest.fixture
def db_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    yield make_sessionmaker(engine)
    engine.dispose()


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).astimezone(UTC)


def add_run(
    db: Session,
    agent: Agent,
    project: Project,
    start: datetime,
    *,
    cli: str = "claude",
    cost: float | None = None,
    tokens: tuple[int, int, int, int] = (0, 0, 0, 0),  # in, out, cache read, cache write
    minutes: int = 10,
    status: RunStatus = RunStatus.COMPLETED,
    task: Task | None = None,
) -> Run:
    run = Run(
        workspace_id=DEFAULT_WORKSPACE,
        agent_id=agent.id,
        project_id=project.id,
        agent_name=agent.name,
        agent_color=agent.color,
        project_name=project.name,
        cli=cli,
        model="claude-haiku-5-5" if cli == "claude" else "gemini-3.7-flash",
        prompt="x",
        cwd="D:/x",
        status=status,
        started_at=start,
        ended_at=start + timedelta(minutes=minutes),
        cost_usd=cost,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        cache_read_tokens=tokens[2],
        cache_creation_tokens=tokens[3],
        task_id=task.id if task else None,
    )
    run.created_at = start
    db.add(run)
    db.flush()
    return run


@pytest.fixture
def seeded(db_factory) -> dict[str, str]:
    with db_factory() as db:
        ana = make_agent(db, "Ana")
        quique = make_agent(db, "Quique")
        quique.cli = "agy"
        tienda, blog = make_project(db, "Tienda"), make_project(db, "Blog")
        task = add_task(db, tienda, ana, "Checkout")
        # Today (local): 3 Claude runs (one failed, no cost) and one agy run. 00:30 local is
        # still the previous day in UTC, and 23:30 local of yesterday is not today.
        add_run(db, ana, tienda, local(DAY, 9), cost=1.5, tokens=(10, 100, 800, 90), task=task)
        add_run(db, ana, blog, local(DAY, 0, 30), cost=0.5, tokens=(5, 50, 0, 0))
        add_run(db, quique, tienda, local(DAY, 11), cli="agy", tokens=(1000, 200, 0, 0), minutes=30)
        add_run(db, ana, tienda, local(DAY, 12), cost=None, status=RunStatus.FAILED, minutes=0)
        # Yesterday 23:30 local (21:30 UTC): not today.
        add_run(db, ana, blog, local(DAY - timedelta(days=1), 23, 30), cost=4.0)
        # The previous 7-day period, for the change.
        add_run(db, ana, tienda, local(DAY - timedelta(days=8), 10), cost=1.0)
        db.commit()
        return {"ana": ana.id, "quique": quique.id, "tienda": tienda.id, "task": task.id}


def test_runs_count_on_their_local_day(db_factory, seeded):
    with db_factory() as db:
        today = stats.runs_between(db, DAY, DAY, tz=TZ)
        assert len(today) == 4
        assert stats.local_day(local(DAY, 0, 30), TZ) == DAY
        yesterday = DAY - timedelta(days=1)
        assert len(stats.runs_between(db, yesterday, yesterday, tz=TZ)) == 1


def test_summary(db_factory, seeded):
    now = local(DAY, 20)
    with db_factory() as db:
        summary = stats.summary(db, DAY - timedelta(days=6), DAY, tz=TZ, now=now)
    k = summary.kpis
    assert k.cost_usd == pytest.approx(6.0)  # 1.5 + 0.5 + 4.0 (agy has no cost)
    assert k.cost_change == pytest.approx(5.0)  # vs 1.0 the previous week
    assert k.sessions == 5
    assert k.success_ratio == pytest.approx(4 / 5)
    assert k.agent_hours == pytest.approx((10 + 10 + 30 + 0 + 10) / 60)
    assert k.tokens == (10 + 100 + 800 + 90) + (5 + 50) + (1000 + 200)
    assert k.cache_ratio == pytest.approx(800 / (10 + 800 + 90 + 5 + 1000))


def test_daily_breakdown_and_sessions(db_factory, seeded):
    with db_factory() as db:
        series = stats.daily(db, DAY - timedelta(days=1), DAY, "agent", tz=TZ)
        assert [p.day for p in series.days] == [DAY - timedelta(days=1), DAY]
        assert series.days[1].cost[seeded["ana"]] == pytest.approx(2.0)
        assert series.days[1].tokens[seeded["quique"]] == 1200
        assert [g.name for g in series.groups] == ["Ana", "Quique"]

        by_project = stats.breakdown(db, DAY, DAY, "project", tz=TZ)
        assert [r.name for r in by_project.rows] == ["Tienda", "Blog"]
        assert by_project.rows[0].share == pytest.approx(1.5 / 2.0)
        by_task = stats.breakdown(db, DAY, DAY, "task", tz=TZ)
        assert by_task.rows[0].name == "T-1 · Checkout"

        rows = stats.sessions(db, DAY, DAY, sort="cost", descending=True, tz=TZ)
        assert [r.cost_usd for r in rows] == [1.5, 0.5, None, None]
        rows = stats.sessions(db, DAY, DAY, sort="tokens", descending=False, tz=TZ)
        assert rows[-1].tokens == 1200
        csv_text = stats.sessions_csv(db, rows)
        assert csv_text.startswith("\ufeffinicio,fin,duracion_s,agente")
        assert csv_text.count("\r\n") == 5
        totals = stats.task_usage(db, [seeded["task"]])[seeded["task"]]
        assert totals.cost_usd == pytest.approx(1.5) and totals.cache_read_tokens == 800


# ---------------------------------------------------------------------- limits
def test_limits_block_per_cli_and_resolve_by_themselves(db_factory, seeded):
    with db_factory() as db:
        limits.save_limits(db, UsageLimits(claude_usd=2.0, agy_tokens=5000))
        assert limits.blocked(db, Cli.CLAUDE, DAY, TZ) == "limit"  # 2.0 of 2.0
        assert limits.blocked(db, Cli.AGY, DAY, TZ) is None  # 1200 of 5000
        states = {s.cli: s for s in limits.states(db, DAY, TZ)}
        assert states["claude"].reached and states["claude"].near
        assert states["agy"].ratio == pytest.approx(1200 / 5000) and not states["agy"].near

        assert limits.sync_limit_items(db, DAY, TZ) is False
        assert limits.sync_limit_items(db, DAY, TZ) is False  # one item per CLI and day
        items = db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).all()
        assert len(items) == 1 and items[0].command == "claude"
        assert "2,00 $ de 2,00 $" in items[0].detail
        db.commit()

        # The limit goes up: the item resolves and the CLI is free again.
        limits.save_limits(db, UsageLimits(claude_usd=10.0, agy_tokens=5000))
        assert limits.sync_limit_items(db, DAY, TZ) is True
        assert items[0].status == InboxStatus.RESOLVED
        # Another day: nothing spent yet.
        limits.save_limits(db, UsageLimits(claude_usd=2.0))
        assert limits.blocked(db, Cli.CLAUDE, DAY + timedelta(days=1), TZ) is None


def test_the_scheduler_skips_the_cli_over_its_limit(db_factory):
    launcher = FakeLauncher()
    scheduler = Scheduler(db_factory, launcher)
    with db_factory() as db:
        dev, gema = make_agent(db, "Dev"), make_agent(db, "Gema")
        gema.cli = "agy"
        web, blog = make_project(db, "Web"), make_project(db, "Blog")
        add_run(db, dev, web, utcnow() - timedelta(minutes=5), cost=3.0)
        add_task(db, web, dev, "Claude task")
        add_task(db, blog, gema, "agy task")
        limits.save_limits(db, UsageLimits(claude_usd=1.0))
        db.commit()
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-2"]  # agy goes on
    assert status_of(db_factory, "T-1")[0] == TaskStatus.QUEUED
    scheduler.check_limits(force=True)
    with db_factory() as db:
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).count() == 1
        limits.save_limits(db, UsageLimits(claude_usd=50.0))
        db.commit()
    scheduler.check_limits(force=True)
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-2", "T-1"]


# ---------------------------------------------------------------------- quota
def screen(cli: Cli, text: str) -> ScreenState:
    state = ScreenState(cli, 100, 20)
    state.feed(text.replace("\n", "\r\n"))
    return state


def test_quota_notice_on_screen():
    agy = screen(Cli.AGY, "Trabajando…\n\n Quota exhausted\n Refreshes in 2h 13m\n> ")
    assert agy.quota_notice() == "Quota exhausted · Refreshes in 2h 13m"
    assert screen(Cli.AGY, "AI: Out of credits").quota_notice() == "AI: Out of credits"
    claude = screen(Cli.CLAUDE, "│ Usage limit reached · resets 3pm (Europe/Madrid) │")
    assert claude.quota_notice() == "Usage limit reached · resets 3pm (Europe/Madrid)"
    weekly = screen(Cli.CLAUDE, "You've hit your weekly limit\nyour usage limit resets Mon 9am")
    assert weekly.quota_notice() is not None
    # Not quota: Claude's context and fast-mode limits, or a mention far above the bottom.
    assert screen(Cli.CLAUDE, "Context limit reached · /compact").quota_notice() is None
    assert screen(Cli.CLAUDE, "You've hit your fast limit").quota_notice() is None
    old = "Quota exhausted\n" + "\n".join(f"línea {i}" for i in range(15))
    assert screen(Cli.AGY, old).quota_notice() is None


def test_quota_blocks_the_cli_until_resumed(db_factory, tmp_path: Path):
    manager = RunManager(db_factory, Settings(_env_file=None, data_dir=tmp_path / "data"))
    with db_factory() as db:
        gema = make_agent(db, "Gema")
        gema.cli = "agy"
        web = make_project(db, "Web")
        task = add_task(db, web, gema, "Algo")
        run = add_run(db, gema, web, utcnow(), cli="agy", status=RunStatus.RUNNING, task=task)
        task_ops.mark_running(db, task, run.id)
        db.commit()
        run_id = run.id

    manager.quota_detected(run_id, "Quota exhausted · Refreshes in 2h")
    manager.quota_detected(run_id, "Quota exhausted · Refreshes in 2h")  # only one item
    with db_factory() as db:
        items = db.query(InboxItem).filter(InboxItem.kind == InboxKind.QUOTA).all()
        assert len(items) == 1
        assert items[0].command == "agy" and items[0].detail.startswith("Quota exhausted")
        assert items[0].title == "Antigravity se ha quedado sin cuota"
        assert status_of(db_factory, "T-1") == (TaskStatus.WAITING_HUMAN, WaitingReason.QUOTA)
        assert limits.blocked(db, Cli.AGY) == "quota"
        assert limits.blocked(db, Cli.CLAUDE) is None

        manager.resume_after_quota(db, items[0])
        db.commit()
        assert items[0].status == InboxStatus.RESOLVED
        assert limits.blocked(db, Cli.AGY) is None
    assert status_of(db_factory, "T-1") == (TaskStatus.RUNNING, None)
