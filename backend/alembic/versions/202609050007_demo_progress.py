"""demo progress tracking

Revision ID: 202609050007
Revises: 202609050006
Create Date: 2026-09-05 00:07:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050007"
down_revision: Union[str, None] = "202609050006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recovery_runs", sa.Column("status", sa.String(16), nullable=False, server_default="COMPLETED"))
    op.add_column("recovery_runs", sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("recovery_runs", sa.Column("processed_cases", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("recovery_runs", sa.Column("failed_cases", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("recovery_runs", sa.Column("current_case_id", sa.String(36), nullable=True))
    op.add_column("recovery_runs", sa.Column("demo_mode", sa.Boolean(), nullable=False, server_default=sa.false()))
    for column in ["status", "total_cases", "processed_cases", "failed_cases", "demo_mode"]:
        op.alter_column("recovery_runs", column, server_default=None)


def downgrade() -> None:
    for column in ["demo_mode", "current_case_id", "failed_cases", "processed_cases", "total_cases", "status"]:
        op.drop_column("recovery_runs", column)
