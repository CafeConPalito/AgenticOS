"""Usage aggregates, daily limits (with the scheduler) and «Cuota agotada»."""

from __future__ import annotations

import time
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
    CliAccount,
    InboxItem,
    InboxKind,
    InboxStatus,
    Project,
    Resolution,
    Run,
    RunStatus,
    SessionState,
    Task,
    TaskStatus,
    WaitingReason,
)
from agentic_os.services import accounts, inbox
from agentic_os.services import tasks as task_ops
from agentic_os.services.runs.manager import RunManager
from agentic_os.services.runs.screen import ScreenState
from agentic_os.services.scheduler import Scheduler
from agentic_os.services.usage import limits, stats

TZ = timezone(timedelta(hours=2))  # Madrid in October
# Today: the Inbox items are stamped with the real clock, so «the day» must be the real one.
DAY = datetime.now(TZ).date()


@pytest.fixture
def db_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    yield make_sessionmaker(engine)
    engine.dispose()


def default(db: Session, cli: Cli):
    """The default account of a CLI (the system one: a database from v1.1 has just those)."""
    return accounts.default_for(db, cli)


def set_limits(db: Session, claude: float | None = None, agy: float | None = None) -> None:
    """The daily limit of each CLI's default account (USD for Claude, tokens for agy)."""
    default(db, Cli.CLAUDE).daily_limit = claude
    default(db, Cli.AGY).daily_limit = agy
    db.flush()


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
    account: CliAccount | None = None,
) -> Run:
    run = Run(
        account_id=account.id if account else None,
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
        set_limits(db, claude=2.0, agy=5000)
        assert limits.blocked(db, default(db, Cli.CLAUDE), DAY, TZ) == "limit"  # 2.0 of 2.0
        assert limits.blocked(db, default(db, Cli.AGY), DAY, TZ) is None  # 1200 of 5000
        states = {s.cli: s for s in limits.states(db, DAY, TZ)}
        assert states["claude"].reached and states["claude"].near
        assert states["agy"].ratio == pytest.approx(1200 / 5000) and not states["agy"].near

        assert limits.sync_limit_items(db, DAY, TZ) is False
        assert limits.sync_limit_items(db, DAY, TZ) is False  # one item per CLI and day
        items = db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).all()
        assert len(items) == 1 and items[0].command == default(db, Cli.CLAUDE).id
        assert "2,00 $ de 2,00 $" in items[0].detail
        db.commit()

        # The limit goes up: the item resolves and the CLI is free again.
        set_limits(db, claude=10.0, agy=5000)
        assert limits.sync_limit_items(db, DAY, TZ) is True
        assert items[0].status == InboxStatus.RESOLVED
        # Another day: nothing spent yet.
        set_limits(db, claude=2.0)
        assert limits.blocked(db, default(db, Cli.CLAUDE), DAY + timedelta(days=1), TZ) is None


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
        set_limits(db, claude=1.0)
        db.commit()
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-2"]  # agy goes on
    assert status_of(db_factory, "T-1")[0] == TaskStatus.QUEUED
    scheduler.check_limits(force=True)
    with db_factory() as db:
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).count() == 1
        set_limits(db, claude=50.0)
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
    assert screen(Cli.CLAUDE, "You've hit your limit · resets 5pm").quota_notice() is not None
    # The agent's own output about the app it works on is not the CLI's quota.
    assert screen(Cli.CLAUDE, "● You've hit your rate limit on the API").quota_notice() is None
    assert screen(Cli.AGY, "grpc error: RESOURCE_EXHAUSTED (quota)").quota_notice() is None
    assert screen(Cli.AGY, "El log dice: Quota exhausted en el servidor").quota_notice() is None
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
        assert items[0].command == default(db, Cli.AGY).id
        assert items[0].detail.startswith("Quota exhausted")
        assert items[0].title == "Antigravity se ha quedado sin cuota"
        assert status_of(db_factory, "T-1") == (TaskStatus.WAITING_HUMAN, WaitingReason.QUOTA)
        assert limits.blocked(db, default(db, Cli.AGY)) == "quota"
        assert limits.blocked(db, default(db, Cli.CLAUDE)) is None

        manager.resume_after_quota(db, items[0])
        db.commit()
        assert items[0].status == InboxStatus.RESOLVED
        assert limits.blocked(db, default(db, Cli.AGY)) is None
    assert status_of(db_factory, "T-1") == (TaskStatus.RUNNING, None)


# ---------------------------------------------------------------------- code review
def test_a_seen_limit_item_is_not_created_again_the_same_day(db_factory, seeded):
    with db_factory() as db:
        set_limits(db, claude=2.0)
        limits.sync_limit_items(db, DAY, TZ)
        item = db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).one()
        # «Descartar» in the Inbox marks it as seen (api/inbox.py).
        inbox.resolve(db, item, Resolution.REVIEWED)
        db.commit()
        limits.sync_limit_items(db, DAY, TZ)
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).count() == 1
        # Moving the limit up and down again the same day: the seen item still holds.
        set_limits(db, claude=10.0)
        limits.sync_limit_items(db, DAY, TZ)
        set_limits(db, claude=1.0)
        limits.sync_limit_items(db, DAY, TZ)
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).count() == 1


def test_blocked_all_reads_today_once(db_factory, seeded, monkeypatch):
    calls = []
    real = stats.runs_between

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(limits, "runs_between", counting)
    with db_factory() as db:
        claude, agy = default(db, Cli.CLAUDE).id, default(db, Cli.AGY).id
        assert limits.blocked_all(db, DAY, TZ) == {claude: None, agy: None}
        assert calls == []  # no limit set: no need to read today's runs
        set_limits(db, claude=2.0, agy=5000)
        assert limits.blocked_all(db, DAY, TZ) == {claude: "limit", agy: None}
        assert len(calls) == 1


def test_a_throttled_limit_check_runs_once_more_later(db_factory, monkeypatch):
    import agentic_os.services.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "LIMIT_CHECK_EVERY", 0.3)
    scheduler = Scheduler(db_factory, FakeLauncher())
    scheduler.check_limits(force=True)
    with db_factory() as db:
        dev, web = make_agent(db, "Dev"), make_project(db, "Web")
        add_run(db, dev, web, utcnow(), cost=3.0)
        set_limits(db, claude=1.0)
        db.commit()
    scheduler.check_limits()  # throttled: the trailing check creates the item
    with db_factory() as db:
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).count() == 0
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with db_factory() as db:
            if db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).count() == 1:
                break
        time.sleep(0.05)
    with db_factory() as db:
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).count() == 1
    scheduler.stop()


# ---------------------------------------------------------------------- accounts (phase 10)
def two_claude_accounts(db: Session, tmp_path: Path):
    """The system account plus a second one, each with an agent and a project to work on."""
    system = default(db, Cli.CLAUDE)
    other = accounts.create(db, tmp_path, Cli.CLAUDE, "Personal")
    other.email = "marta.personal@gmail.com"
    ana, beto = make_agent(db, "Ana"), make_agent(db, "Beto")
    beto.account_id = other.id
    web, blog = make_project(db, "Web"), make_project(db, "Blog")
    return system, other, ana, beto, web, blog


def test_the_limit_is_per_account_so_another_account_of_the_cli_goes_on(db_factory, tmp_path):
    launcher = FakeLauncher()
    scheduler = Scheduler(db_factory, launcher)
    with db_factory() as db:
        system, other, ana, beto, web, blog = two_claude_accounts(db, tmp_path)
        add_run(db, ana, web, utcnow() - timedelta(minutes=5), cost=3.0, account=system)
        add_task(db, web, ana, "Con la cuenta del sistema")  # T-1
        add_task(db, blog, beto, "Con la cuenta personal")  # T-2
        system.daily_limit = 1.0
        db.commit()
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-2"]  # Beto's account is not held
    assert status_of(db_factory, "T-1")[0] == TaskStatus.QUEUED

    scheduler.check_limits(force=True)
    with db_factory() as db:
        item = db.query(InboxItem).filter(InboxItem.kind == InboxKind.LIMIT).one()
        assert item.command == default(db, Cli.CLAUDE).id
        # Two accounts of the CLI: the title says which one.
        assert (
            item.title
            == f"Límite diario de Claude Code ({accounts.display_name(system)}) alcanzado"
        )
    with db_factory() as db:
        spent = limits.used_by_account(db, DAY, TZ)
        assert spent[system.id] == pytest.approx(3.0) and spent[other.id] == 0


def test_the_usage_of_a_removed_account_counts_for_the_default_one(db_factory, tmp_path):
    with db_factory() as db:
        system, other, _ana, beto, _web, blog = two_claude_accounts(db, tmp_path)
        run = add_run(db, beto, blog, utcnow(), cost=2.0, account=other)
        beto.account_id = None
        db.commit()
        accounts.delete(db, other)
        db.commit()
        db.refresh(run)
        assert run.account_id is None
        assert limits.used_by_account(db, DAY, TZ) == {
            system.id: pytest.approx(2.0),
            default(db, Cli.AGY).id: 0.0,
        }


def test_quota_exhausted_holds_only_the_account_that_ran_out(db_factory, tmp_path):
    manager = RunManager(db_factory, Settings(_env_file=None, data_dir=tmp_path / "data"))
    with db_factory() as db:
        system, other, _ana, beto, _web, blog = two_claude_accounts(db, tmp_path)
        task = add_task(db, blog, beto, "Algo")
        run = add_run(db, beto, blog, utcnow(), status=RunStatus.RUNNING, task=task, account=other)
        task_ops.mark_running(db, task, run.id)
        db.commit()
        run_id, system_id, other_id = run.id, system.id, other.id

    manager.quota_detected(run_id, "You've hit your limit · resets 5pm")
    with db_factory() as db:
        item = db.query(InboxItem).filter(InboxItem.kind == InboxKind.QUOTA).one()
        assert item.command == other_id
        assert item.title == "Claude Code (marta.personal@gmail.com) se ha quedado sin cuota"
        gates = limits.blocked_all(db, DAY, TZ)
        assert gates[other_id] == "quota" and gates[system_id] is None


def test_a_logged_out_account_holds_its_agents_and_asks_to_reconnect(db_factory, tmp_path):
    launcher = FakeLauncher()
    scheduler = Scheduler(db_factory, launcher)
    probed: list[str] = []

    def probe(db, account):
        probed.append(account.id)

    scheduler.probe_account = probe
    with db_factory() as db:
        system, other, ana, beto, web, blog = two_claude_accounts(db, tmp_path)
        add_task(db, web, ana, "Cuenta del sistema")  # T-1
        add_task(db, blog, beto, "Cuenta personal")  # T-2
        other.session_state = SessionState.DOWN.value
        other.session_checked_at = utcnow()  # fresh: the scheduler does not ask again
        system.session_checked_at = utcnow()
        db.commit()
        other_id = other.id

    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-1"]
    assert probed == []
    with db_factory() as db:
        assert limits.blocked_all(db)[other_id] == "session"
        assert limits.sync_session_items(db) is False
        assert limits.sync_session_items(db) is False  # one item, however many checks
        item = db.query(InboxItem).filter(InboxItem.kind == InboxKind.ACCOUNT).one()
        assert item.command == other_id and "marta.personal@gmail.com" in item.title
        db.commit()

        # She logs in again: the item resolves and the scheduler is told to look again.
        db.get(CliAccount, other_id).session_state = SessionState.OK.value  # type: ignore[union-attr]
        assert limits.sync_session_items(db) is True
        assert item.status == InboxStatus.RESOLVED
        db.commit()
    scheduler.step()
    assert [code for code, _ in launcher.launched] == ["T-1", "T-2"]


def test_only_the_accounts_in_use_are_worth_a_session_notice(db_factory, tmp_path):
    with db_factory() as db:
        system, other, *_ = two_claude_accounts(db, tmp_path)
        unused = accounts.create(db, tmp_path, Cli.CLAUDE)
        unused.session_state = SessionState.DOWN.value
        default(db, Cli.AGY).session_state = SessionState.DOWN.value  # agy: no agent uses it
        db.flush()
        assert limits.accounts_in_use(db) == {system.id, other.id}
        limits.sync_session_items(db)
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.ACCOUNT).count() == 0


def test_the_scheduler_asks_the_cli_again_off_its_own_thread(db_factory, tmp_path):
    """An old session check is redone before launching, but never on the scheduler thread (the
    CLIs take seconds): the tick goes on with what is known, a logout holds the next one."""
    import threading

    launcher = FakeLauncher()
    scheduler = Scheduler(db_factory, launcher)
    probing_thread: list[str] = []
    done = threading.Event()

    def probe(db, account):  # the person logged out since the last check
        probing_thread.append(threading.current_thread().name)
        account.session_state = SessionState.DOWN.value
        account.session_checked_at = utcnow()
        done.set()

    scheduler.probe_account = probe
    with db_factory() as db:
        system, _other, ana, _beto, web, blog = two_claude_accounts(db, tmp_path)
        add_task(db, web, ana, "Primera")  # T-1
        system.session_state = SessionState.OK.value
        system.session_checked_at = utcnow() - timedelta(hours=1)  # old: asked again
        db.commit()
    scheduler.step()
    assert done.wait(10)
    assert probing_thread == ["session-probe"]  # not the scheduler's thread
    scheduler.step()  # the logout is known now: nothing starts, and one notice asks to reconnect
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with db_factory() as db:
            if db.query(InboxItem).filter(InboxItem.kind == InboxKind.ACCOUNT).count() == 1:
                break
        time.sleep(0.05)
    with db_factory() as db:
        assert db.query(InboxItem).filter(InboxItem.kind == InboxKind.ACCOUNT).count() == 1
        add_task(db, blog, ana, "Segunda")  # T-2, same agent
        db.commit()
    scheduler.step()
    assert "T-2" not in [code for code, _ in launcher.launched]


def test_only_a_held_task_says_by_which_account(db_factory, tmp_path):
    """`blocked_by` names the account of a held task, and is empty for one that is not held."""
    from agentic_os.api.tasks import read_tasks

    with db_factory() as db:
        _system, other, ana, beto, web, blog = two_claude_accounts(db, tmp_path)
        free, held = add_task(db, web, ana, "Libre"), add_task(db, blog, beto, "Retenida")
        other.session_state = SessionState.DOWN.value
        db.flush()
        reads = {t.title: t for t in read_tasks(db, [free, held])}
        assert (reads["Libre"].blocked, reads["Libre"].blocked_by) == (None, None)
        assert (reads["Retenida"].blocked, reads["Retenida"].blocked_by) == (
            "session",
            accounts.display_name(other),
        )
