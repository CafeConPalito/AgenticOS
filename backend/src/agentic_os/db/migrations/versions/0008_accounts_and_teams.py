"""accounts and teams

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14 17:30:40.628733

Phase 10. Every CLI gets a **system account** (its own configuration, the login the person
already had) as its default one, so nothing changes until a second account is added:
- the daily limits move from `app_state['usage_limits']` to the system accounts;
- the existing runs point to the system account of their CLI;
- the pending «Límite diario» / «Cuota agotada» items name the account instead of the CLI.
"""

import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# Alembic does not compare CHECK constraints: the new Inbox kind is added by hand.
OLD_INBOX_KINDS = (
    "'approval', 'question', 'blocker', 'review', 'stalled', 'delivery', 'attention',"
    " 'limit', 'quota'"
)
NEW_INBOX_KINDS = OLD_INBOX_KINDS + ", 'account'"

CLIS = ("claude", "agy")
SYSTEM_LABEL = "Cuenta del sistema"
LIMIT_KEYS = {"claude": "claude_usd", "agy": "agy_tokens"}
USAGE_LIMITS = "usage_limits"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def upgrade() -> None:
    op.create_table(
        "cli_accounts",
        sa.Column("cli", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("plan", sa.String(length=80), nullable=False),
        sa.Column("config_dir", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("session_state", sa.String(length=8), nullable=False),
        sa.Column("session_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("daily_limit", sa.Float(), nullable=True),
        sa.Column("quota", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cli IN ('claude', 'agy')", name=op.f("ck_cli_accounts_cli")),
        sa.CheckConstraint(
            "session_state IN ('ok', 'down', 'unknown')",
            name=op.f("ck_cli_accounts_session_state"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cli_accounts")),
    )
    with op.batch_alter_table("cli_accounts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_cli_accounts_workspace_id"), ["workspace_id"], unique=False
        )
        batch_op.create_index(
            "uq_cli_accounts_default_per_cli",
            ["cli"],
            unique=True,
            sqlite_where=sa.text("is_default = 1"),
            postgresql_where=sa.text("is_default"),
        )

    op.create_table(
        "teams",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_teams_workspace_id"), ["workspace_id"], unique=False)

    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("team_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("account_id", sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f("ix_agents_account_id"), ["account_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_agents_team_id"), ["team_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_agents_account_id_cli_accounts"),
            "cli_accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_agents_team_id_teams"), "teams", ["team_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("account_id", sa.String(length=36), nullable=True))
        # Existing rows get the default; the model sets it for new rows.
        batch_op.add_column(
            sa.Column("account_label", sa.String(length=120), nullable=False, server_default="")
        )
        batch_op.create_index(batch_op.f("ix_runs_account_id"), ["account_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_runs_account_id_cli_accounts"),
            "cli_accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({NEW_INBOX_KINDS})"
        )

    _move_data_to_system_accounts()


def _move_data_to_system_accounts() -> None:
    conn = op.get_bind()
    raw = conn.execute(
        sa.text("SELECT value FROM app_state WHERE key = :key"), {"key": USAGE_LIMITS}
    ).scalar()
    try:
        limits = json.loads(raw) if raw else {}
    except ValueError:
        limits = {}
    if not isinstance(limits, dict):
        limits = {}

    accounts: dict[str, str] = {}
    now = _now()
    for cli in CLIS:
        accounts[cli] = str(uuid.uuid4())
        limit = limits.get(LIMIT_KEYS[cli])
        conn.execute(
            sa.text(
                "INSERT INTO cli_accounts (id, workspace_id, cli, label, email, plan, config_dir,"
                " is_default, session_state, daily_limit, quota, created_at, updated_at)"
                " VALUES (:id, 'default', :cli, :label, '', '', NULL, 1, 'unknown', :limit, '{}',"
                " :now, :now)"
            ),
            {
                "id": accounts[cli],
                "cli": cli,
                "label": SYSTEM_LABEL,
                "limit": float(limit) if isinstance(limit, int | float) else None,
                "now": now,
            },
        )
    conn.execute(sa.text("DELETE FROM app_state WHERE key = :key"), {"key": USAGE_LIMITS})

    for cli, account_id in accounts.items():
        # The runs keep an empty label: the API shows the account's current name.
        conn.execute(
            sa.text("UPDATE runs SET account_id = :account WHERE cli = :cli"),
            {"account": account_id, "cli": cli},
        )
        # The limit and quota items named the CLI; they name the account now.
        conn.execute(
            sa.text(
                "UPDATE inbox_items SET command = :account"
                " WHERE kind IN ('limit', 'quota') AND command = :cli"
            ),
            {"account": account_id, "cli": cli},
        )


def downgrade() -> None:
    conn = op.get_bind()
    system = {
        row.id: row.cli
        for row in conn.execute(
            sa.text("SELECT id, cli FROM cli_accounts WHERE config_dir IS NULL")
        ).fetchall()
    }
    limits: dict[str, float | None] = {}
    for account_id, cli in system.items():
        limit = conn.execute(
            sa.text("SELECT daily_limit FROM cli_accounts WHERE id = :id"), {"id": account_id}
        ).scalar()
        limits[LIMIT_KEYS[cli]] = int(limit) if cli == "agy" and limit is not None else limit
        conn.execute(
            sa.text(
                "UPDATE inbox_items SET command = :cli"
                " WHERE kind IN ('limit', 'quota') AND command = :account"
            ),
            {"cli": cli, "account": account_id},
        )
    if any(value is not None for value in limits.values()):
        conn.execute(
            sa.text("INSERT INTO app_state (key, value) VALUES (:key, :value)"),
            {"key": USAGE_LIMITS, "value": json.dumps(limits)},
        )
    # Items of an account that is not a system one cannot name a CLI any more.
    op.execute("DELETE FROM inbox_items WHERE kind = 'account'")
    op.execute(
        "DELETE FROM inbox_items WHERE kind IN ('limit', 'quota') AND command NOT IN ('claude', 'agy')"
    )
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_inbox_items_kind"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_inbox_items_kind"), f"kind IN ({OLD_INBOX_KINDS})"
        )

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("fk_runs_account_id_cli_accounts"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_runs_account_id"))
        batch_op.drop_column("account_label")
        batch_op.drop_column("account_id")

    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("fk_agents_team_id_teams"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_agents_account_id_cli_accounts"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_agents_team_id"))
        batch_op.drop_index(batch_op.f("ix_agents_account_id"))
        batch_op.drop_column("account_id")
        batch_op.drop_column("team_id")

    with op.batch_alter_table("teams", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_teams_workspace_id"))
    op.drop_table("teams")

    with op.batch_alter_table("cli_accounts", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_cli_accounts_default_per_cli",
            sqlite_where=sa.text("is_default = 1"),
            postgresql_where=sa.text("is_default"),
        )
        batch_op.drop_index(batch_op.f("ix_cli_accounts_workspace_id"))
    op.drop_table("cli_accounts")
