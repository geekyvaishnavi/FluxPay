"""expected recovery probability

Revision ID: 202609050006
Revises: 202609050005
Create Date: 2026-09-05 00:06:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050006"
down_revision: Union[str, None] = "202609050005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_decisions",
        sa.Column(
            "expected_recovery_probability",
            sa.Numeric(5, 4),
            nullable=False,
            server_default="0.0000",
        ),
    )
    op.alter_column("agent_decisions", "expected_recovery_probability", server_default=None)


def downgrade() -> None:
    op.drop_column("agent_decisions", "expected_recovery_probability")
