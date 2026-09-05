"""agent decision details

Revision ID: 202609050003
Revises: 202609050002
Create Date: 2026-09-05 00:03:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050003"
down_revision: Union[str, None] = "202609050002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    risk_level = sa.Enum("LOW", "MEDIUM", "HIGH", name="risk_level")
    risk_level.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "agent_decisions",
        sa.Column("risk_level", risk_level, nullable=False, server_default="MEDIUM"),
    )
    op.add_column(
        "agent_decisions",
        sa.Column("delay_hours", sa.Integer(), nullable=False, server_default="24"),
    )
    op.add_column(
        "agent_decisions",
        sa.Column("reason", sa.Text(), nullable=False, server_default="Existing seeded decision."),
    )
    op.add_column(
        "agent_decisions",
        sa.Column("context_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.alter_column(
        "agent_decisions",
        "confidence",
        existing_type=sa.String(length=16),
        type_=sa.Numeric(5, 4),
        postgresql_using=(
            "CASE confidence "
            "WHEN 'LOW' THEN 0.4000 "
            "WHEN 'MEDIUM' THEN 0.7500 "
            "WHEN 'HIGH' THEN 0.9000 "
            "ELSE 0.5000 END"
        ),
        existing_nullable=False,
    )

    op.alter_column("agent_decisions", "risk_level", server_default=None)
    op.alter_column("agent_decisions", "delay_hours", server_default=None)
    op.alter_column("agent_decisions", "reason", server_default=None)
    op.alter_column("agent_decisions", "context_snapshot", server_default=None)

    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'AI_ANALYSIS_COMPLETED'")
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'AI_ANALYSIS_FAILED'")


def downgrade() -> None:
    op.alter_column(
        "agent_decisions",
        "confidence",
        existing_type=sa.Numeric(5, 4),
        type_=sa.String(length=16),
        postgresql_using=(
            "CASE "
            "WHEN confidence < 0.5000 THEN 'LOW' "
            "WHEN confidence >= 0.8500 THEN 'HIGH' "
            "ELSE 'MEDIUM' END"
        ),
        existing_nullable=False,
    )
    op.drop_column("agent_decisions", "context_snapshot")
    op.drop_column("agent_decisions", "reason")
    op.drop_column("agent_decisions", "delay_hours")
    op.drop_column("agent_decisions", "risk_level")
    sa.Enum(name="risk_level").drop(op.get_bind(), checkfirst=True)
