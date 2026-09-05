"""audit lifecycle events

Revision ID: 202609050008
Revises: 202609050007
Create Date: 2026-09-05 00:08:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "202609050008"
down_revision: Union[str, None] = "202609050007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for event_type in [
        "AI_ANALYSIS_STARTED", "AI_DECISION_CREATED", "PAYMENT_RETRY_FAILED", "PAYMENT_LINK_SENT",
        "RECOVERY_RUN_STARTED", "RECOVERY_RUN_COMPLETED", "RECOVERY_RUN_FAILED",
    ]:
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{event_type}'")


def downgrade() -> None:
    pass
