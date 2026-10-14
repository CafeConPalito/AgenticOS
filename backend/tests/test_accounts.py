"""CLI accounts (phase 10): the system accounts, their folders, the session probe and the
subscription windows read from the status line of both CLIs."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from agentic_os.config import Settings
from agentic_os.db.base import DEFAULT_WORKSPACE, utcnow
from agentic_os.db.migrate import upgrade_to_head
from agentic_os.db.session import create_db_engine, database_url, make_sessionmaker
from agentic_os.errors import ApiError
from agentic_os.models import (
    Agent,
    Cli,
    CliAccount,
    InboxItem,
    InboxKind,
    InboxStatus,
    Run,
    RunStatus,
    SessionState,
)
from agentic_os.services import accounts
from agentic_os.services.hooks import STATUS_LINE, interpret
from agentic_os.services.quota import QuotaWindow, windows_from_status_line

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"
NOW = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)


@pytest.fixture
def db_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    Path(settings.data_dir).mkdir(parents=True)
    engine = create_db_engine(database_url(settings))
    upgrade_to_head(engine)
    yield make_sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def db(db_factory) -> Iterator[Session]:
    with db_factory() as session:
        yield session


def add_agent(db: Session, cli: Cli = Cli.CLAUDE, account_id: str | None = None) -> Agent:
    agent = Agent(workspace_id=DEFAULT_WORKSPACE, name="Dev", cli=cli.value, account_id=account_id)
    db.add(agent)
    db.flush()
    return agent


def add_run(db: Session, account: CliAccount, status: RunStatus) -> Run:
    run = Run(
        workspace_id=DEFAULT_WORKSPACE,
        agent_name="Dev",
        agent_color="#fff",
        project_name="p",
        cli=account.cli,
        prompt="hola",
        cwd="C:/p",
        status=status.value,
        account_id=account.id,
    )
    db.add(run)
    db.flush()
    return run


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


# ---------------------------------------------------------------- system accounts
def test_every_cli_has_a_default_system_account(db: Session):
    for cli in Cli:
        account = accounts.default_for(db, cli)
        assert account.config_dir is None and account.is_default and account.is_system
        assert accounts.env_for(account) == {}  # the CLI keeps its own configuration


def test_an_agent_uses_its_account_or_the_default_of_its_cli(db: Session, tmp_path: Path):
    second = accounts.create(db, tmp_path, Cli.CLAUDE)
    plain = add_agent(db)
    chosen = add_agent(db, account_id=second.id)
    wrong_cli = add_agent(db, Cli.AGY, account_id=second.id)  # an account of another CLI
    assert accounts.of_agent(db, plain) is accounts.default_for(db, Cli.CLAUDE)
    assert accounts.of_agent(db, chosen) is second
    assert accounts.of_agent(db, wrong_cli).cli == Cli.AGY
    index = accounts.AccountIndex(db)
    assert index.of(chosen) is second and index.of(plain).is_system  # type: ignore[union-attr]


def test_a_database_without_system_account_makes_one(db: Session):
    for account in accounts.list_accounts(db):
        db.delete(account)
    db.flush()
    account = accounts.default_for(db, Cli.AGY)
    assert account.is_system and account.is_default


# ---------------------------------------------------------------- create / default / delete
def test_create_makes_a_folder_and_points_the_cli_to_it(db: Session, tmp_path: Path):
    account = accounts.create(db, tmp_path, Cli.CLAUDE, "  Personal ")
    folder = tmp_path / "accounts" / account.id
    assert folder.is_dir() and account.config_dir == str(folder)
    assert account.label == "Personal" and not account.is_default and not account.is_system
    assert accounts.env_for(account) == {"CLAUDE_CONFIG_DIR": str(folder)}


def test_agy_keeps_a_single_login(db: Session, tmp_path: Path):
    with pytest.raises(ApiError) as error:
        accounts.create(db, tmp_path, Cli.AGY)
    assert error.value.status == 409 and error.value.code == "accounts_unsupported"


def test_there_is_one_default_per_cli_even_for_the_database(db: Session, tmp_path: Path):
    second = accounts.create(db, tmp_path, Cli.CLAUDE)
    accounts.set_default(db, second)
    defaults = [a for a in accounts.list_accounts(db, Cli.CLAUDE) if a.is_default]
    assert defaults == [second]
    assert accounts.default_for(db, Cli.AGY).is_default  # the other CLI is untouched

    other = accounts.create(db, tmp_path, Cli.CLAUDE)
    other.is_default = True  # bypassing set_default: the partial unique index refuses it
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_delete_removes_the_folder_and_hands_the_default_back(db: Session, tmp_path: Path):
    account = accounts.create(db, tmp_path, Cli.CLAUDE)
    accounts.set_default(db, account)
    pending = InboxItem(
        workspace_id=DEFAULT_WORKSPACE,
        kind=InboxKind.ACCOUNT.value,
        status=InboxStatus.PENDING.value,
        title="Sesión cerrada",
        command=account.id,
    )
    db.add(pending)
    db.flush()
    folder = Path(account.config_dir)  # type: ignore[arg-type]

    accounts.delete(db, account)
    assert not folder.exists() and accounts.get(db, account.id) is None
    assert accounts.default_for(db, Cli.CLAUDE).is_system
    assert pending.status == InboxStatus.RESOLVED.value  # nothing left asking about it


def test_the_system_account_agents_and_live_runs_block_the_removal(db: Session, tmp_path: Path):
    system = accounts.default_for(db, Cli.CLAUDE)
    with pytest.raises(ApiError) as error:
        accounts.delete(db, system)
    assert error.value.code == "system_account"

    used = accounts.create(db, tmp_path, Cli.CLAUDE)
    agent = add_agent(db, account_id=used.id)
    with pytest.raises(ApiError) as error:
        accounts.delete(db, used)
    assert error.value.code == "account_in_use"

    agent.account_id = None
    run = add_run(db, used, RunStatus.RUNNING)
    with pytest.raises(ApiError) as error:
        accounts.delete(db, used)
    assert error.value.code == "account_busy"
    run.status = RunStatus.COMPLETED.value  # a finished run only keeps its label
    accounts.delete(db, used)
    db.refresh(run)  # the database nulled the link (ON DELETE SET NULL)
    assert run.account_id is None


# ---------------------------------------------------------------- session probe
CLAUDE_OUT = json.dumps({"loggedIn": True, "email": "marta@estudio.es", "subscriptionType": "max"})


def test_probe_reads_claude_auth_status(db: Session, tmp_path: Path):
    account = accounts.create(db, tmp_path, Cli.CLAUDE)
    seen: list[dict] = []

    def run(argv, timeout, cwd=None, env=None):
        seen.append({"argv": argv, "env": env})
        return completed(CLAUDE_OUT)

    accounts.probe(db, account, {"claude": ["claude"]}, run)
    assert account.session_state == SessionState.OK
    assert (account.email, account.plan) == ("marta@estudio.es", "max")
    assert account.session_checked_at is not None
    assert seen[0]["argv"] == ["claude", "auth", "status"]
    assert seen[0]["env"]["CLAUDE_CONFIG_DIR"] == account.config_dir  # asked in its own folder


def test_probe_reads_the_json_when_claude_exits_with_1(db: Session):
    """`claude auth status` exits 1 without a session: the JSON decides, not the exit code."""
    account = accounts.default_for(db, Cli.CLAUDE)
    out = json.dumps({"loggedIn": False, "authMethod": "none"})
    accounts.probe(db, account, {"claude": ["claude"]}, lambda *a, **k: completed(out, 1))
    assert account.session_state == SessionState.DOWN
    assert account.email == ""


def test_probe_does_not_guess_when_the_cli_cannot_tell(db: Session):
    account = accounts.default_for(db, Cli.CLAUDE)
    account.session_state = SessionState.OK.value

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("claude", 20)

    accounts.probe(db, account, {"claude": ["claude"]}, boom)
    assert account.session_state == SessionState.UNKNOWN
    accounts.probe(db, account, {"claude": ["claude"]}, lambda *a, **k: completed("not json"))
    assert account.session_state == SessionState.UNKNOWN


def test_probe_of_agy_lists_its_models(db: Session):
    account = accounts.default_for(db, Cli.AGY)
    models = "gemini-3.8-flash-high\tGemini 3.8 Flash (High)\n"
    accounts.probe(db, account, {"agy": ["agy"]}, lambda *a, **k: completed(models))
    assert account.session_state == SessionState.OK
    accounts.probe(db, account, {"agy": ["agy"]}, lambda *a, **k: completed("", 1))
    assert account.session_state == SessionState.DOWN


def test_probe_of_a_cli_that_is_not_installed_changes_nothing(db: Session, monkeypatch):
    from agentic_os.services.runs import launcher

    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    account = accounts.default_for(db, Cli.CLAUDE)
    accounts.probe(db, account, {}, lambda *a, **k: pytest.fail("must not run"))
    assert account.session_state == SessionState.UNKNOWN and account.session_checked_at is None


def test_a_recent_probe_is_fresh(db: Session):
    account = accounts.default_for(db, Cli.CLAUDE)
    assert not accounts.session_is_fresh(account)
    account.session_checked_at = utcnow() - timedelta(minutes=2)
    assert accounts.session_is_fresh(account)
    account.session_checked_at = utcnow() - timedelta(minutes=30)
    assert not accounts.session_is_fresh(account)


# ---------------------------------------------------------------- the CLIs' status lines
def test_claude_status_line_windows_match_the_real_capture():
    payload = json.loads(
        (FIXTURES / "claude-2.1.299-statusline-rate-limits.json").read_text("utf-8")
    )
    windows = {w.id: w for w in windows_from_status_line(Cli.CLAUDE, payload)}
    assert set(windows) == {"five_hour", "seven_day"}
    assert windows["five_hour"].used_pct == 11
    assert windows["five_hour"].resets_at == datetime.fromtimestamp(1792003200, UTC)
    assert windows["seven_day"].used_pct == 75


def test_agy_status_line_windows_match_the_real_capture():
    payload = json.loads((FIXTURES / "agy-1.3.5-statusline-quota.json").read_text("utf-8"))
    windows = {w.id: w for w in windows_from_status_line(Cli.AGY, payload)}
    assert set(windows) == {"gemini-5h", "gemini-weekly", "3p-5h", "3p-weekly"}
    # The CLI reports what is left: 0.982825 left is 1.7 % used.
    assert windows["gemini-5h"].used_pct == pytest.approx(1.7175)
    assert windows["3p-weekly"].used_pct == 0
    assert windows["gemini-5h"].resets_at == datetime(2026, 10, 14, 16, 46, 59, tzinfo=UTC)


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"rate_limits": []}, {"rate_limits": {"five_hour": 3}}]
)
def test_a_status_line_without_quota_gives_no_windows(payload):
    assert windows_from_status_line(Cli.CLAUDE, payload) == []
    assert windows_from_status_line(Cli.AGY, payload) == []


def test_malformed_windows_are_skipped_and_percentages_clamped():
    payload = {
        "rate_limits": {
            "five_hour": {"used_percentage": 140, "resets_at": 1792003200},
            "seven_day": {"used_percentage": "75", "resets_at": 1792249200},
        }
    }
    windows = windows_from_status_line(Cli.CLAUDE, payload)
    assert [(w.id, w.used_pct) for w in windows] == [("five_hour", 100)]
    agy = {
        "quota": {
            "x": {"remaining_fraction": 1.5, "reset_time": "2026-10-14T16:00:00Z"},
            "y": {"remaining_fraction": 0.5, "reset_time": "yesterday"},
        }
    }
    assert [(w.id, w.used_pct) for w in windows_from_status_line(Cli.AGY, agy)] == [("x", 0)]


def test_interpret_keeps_the_cost_and_adds_quota_and_identity():
    claude = json.loads(
        (FIXTURES / "claude-2.1.299-statusline-rate-limits.json").read_text("utf-8")
    )
    effect = interpret(Cli.CLAUDE, STATUS_LINE, claude)
    assert effect.cost_usd == pytest.approx(0.0471656) and effect.cli_version == "2.1.299"
    assert {w.id for w in effect.quota} == {"five_hour", "seven_day"}
    assert effect.email is None  # Claude's status line does not name the account

    agy = json.loads((FIXTURES / "agy-1.3.5-statusline-quota.json").read_text("utf-8"))
    effect = interpret(Cli.AGY, STATUS_LINE, agy)
    assert (effect.email, effect.plan) == ("user@example.com", "Google AI Pro")
    assert effect.transcript_path == "C:\\transcript.jsonl" and len(effect.quota) == 4
    assert interpret(Cli.CLAUDE, STATUS_LINE, {"cost": {"total_cost_usd": 1}}).quota == ()


# ---------------------------------------------------------------- recording and expiry
def window(window_id: str, used: float, resets: datetime) -> QuotaWindow:
    return QuotaWindow(window_id, used, resets)


def test_record_quota_keeps_the_last_value_and_says_when_it_changed(db: Session):
    account = accounts.default_for(db, Cli.CLAUDE)
    resets = NOW + timedelta(hours=2)
    assert accounts.record_quota(account, [window("five_hour", 11, resets)], NOW) is True
    # The same figures a few seconds later: nothing to tell, the stored read time stays.
    assert (
        accounts.record_quota(
            account, [window("five_hour", 11, resets)], NOW + timedelta(seconds=5)
        )
        is False
    )
    assert account.quota["five_hour"]["read_at"] == NOW.isoformat()
    # …but a minute later the read time is refreshed (without announcing a change).
    later = NOW + timedelta(minutes=2)
    assert accounts.record_quota(account, [window("five_hour", 11, resets)], later) is False
    assert account.quota["five_hour"]["read_at"] == later.isoformat()
    # A new figure is a change; a window the CLI omits is kept.
    assert accounts.record_quota(account, [window("seven_day", 75, resets)], later) is True
    assert accounts.record_quota(account, [window("seven_day", 76, resets)], later) is True
    assert set(account.quota) == {"five_hour", "seven_day"}
    assert accounts.record_quota(account, [], later) is False


def test_quota_persists_through_the_database(db_factory):
    resets = NOW + timedelta(hours=2)
    with db_factory() as db:
        account = accounts.default_for(db, Cli.CLAUDE)
        accounts.record_quota(account, [window("five_hour", 42.5, resets)], NOW)
        db.commit()
        account_id = account.id
    with db_factory() as db:
        saved = db.scalar(select(CliAccount).where(CliAccount.id == account_id))
        assert saved is not None and saved.quota["five_hour"]["used_pct"] == 42.5


def test_a_window_past_its_reset_shows_as_reset(db: Session):
    account = accounts.default_for(db, Cli.CLAUDE)
    accounts.record_quota(
        account,
        [
            window("five_hour", 96, NOW + timedelta(hours=1)),
            window("seven_day", 40, NOW + timedelta(days=3)),
        ],
        NOW,
    )
    before = {v.id: v for v in accounts.quota_view(account, NOW + timedelta(minutes=30))}
    assert before["five_hour"].used_pct == 96 and not before["five_hour"].expired
    assert accounts.highest_quota(account, NOW + timedelta(minutes=30)).id == "five_hour"  # type: ignore[union-attr]

    after = {v.id: v for v in accounts.quota_view(account, NOW + timedelta(hours=2))}
    assert after["five_hour"].expired and after["five_hour"].used_pct == 0
    assert after["seven_day"].used_pct == 40  # the weekly window goes on
    assert accounts.highest_quota(account, NOW + timedelta(hours=2)).id == "seven_day"  # type: ignore[union-attr]
    assert accounts.highest_quota(account, NOW + timedelta(days=4)) is None  # all of them reset


def test_a_corrupt_window_is_ignored(db: Session):
    account = accounts.default_for(db, Cli.CLAUDE)
    account.quota = {
        "five_hour": {"used_pct": "?"},
        "ok": {
            "used_pct": 5,
            "resets_at": (NOW + timedelta(hours=1)).isoformat(),
            "read_at": NOW.isoformat(),
        },
    }
    assert [v.id for v in accounts.quota_view(account, NOW)] == ["ok"]
