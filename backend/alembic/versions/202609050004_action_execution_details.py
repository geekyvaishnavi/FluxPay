"""action execution details

Revision ID: 202609050004
Revises: 202609050003
Create Date: 2026-09-05 00:04:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050004"
down_revision: Union[str, None] = "202609050003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recovery_actions",
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.alter_column("recovery_actions", "result", server_default=None)

    for event_type in [
        "POLICY_EVALUATED",
        "POLICY_REJECTED",
        "ACTION_EXECUTED",
        "PAYMENT_RETRY_CREATED",
        "PAYMENT_RECOVERED",
        "CASE_ESCALATED",
        "CASE_STOPPED",
    ]:
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{event_type}'")


def downgrade() -> None:
    op.drop_column("recovery_actions", "result")
