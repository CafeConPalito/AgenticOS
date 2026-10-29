"""branch always is no condition

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-29 21:00:00.000000

Phase 21: a branch without a condition is always taken, so «always» and «no condition» mean the
same. A branch marked «always» loses the condition it may still carry (the decider never read
it), and the saved pipelines keep doing what they did.
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE stage_links SET condition = '' WHERE always = 1")


def downgrade() -> None:
    # The cleared conditions were never used: there is nothing to put back.
    pass
