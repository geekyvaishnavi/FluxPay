"""recovery run tracking

Revision ID: 202609050005
Revises: 202609050004
Create Date: 2026-09-05 00:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050005"
down_revision: Union[str, None] = "202609050004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recovery_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cases_processed", sa.Integer(), nullable=False),
        sa.Column("actions_executed", sa.Integer(), nullable=False),
        sa.Column("recovered_cases", sa.Integer(), nullable=False),
        sa.Column("escalated_cases", sa.Integer(), nullable=False),
        sa.Column("stopped_cases", sa.Integer(), nullable=False),
        sa.Column("revenue_at_risk", sa.Numeric(12, 2), nullable=False),
        sa.Column("revenue_recovered", sa.Numeric(12, 2), nullable=False),
        sa.Column("recovery_rate", sa.Numeric(8, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("recovery_runs")
