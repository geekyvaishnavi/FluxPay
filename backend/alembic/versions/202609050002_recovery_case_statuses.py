"""recovery case statuses

Revision ID: 202609050002
Revises: 202609050001
Create Date: 2026-09-05 00:02:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "202609050002"
down_revision: Union[str, None] = "202609050001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum
                JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                WHERE pg_type.typname = 'recovery_case_status'
                AND pg_enum.enumlabel IN ('OPEN', 'IN_PROGRESS', 'CLOSED')
            ) THEN
                CREATE TYPE recovery_case_status_new AS ENUM (
                    'DETECTED',
                    'ANALYZING',
                    'ACTION_REQUIRED',
                    'RECOVERED',
                    'ESCALATED',
                    'STOPPED'
                );

                ALTER TABLE recovery_cases
                ALTER COLUMN status TYPE recovery_case_status_new
                USING (
                    CASE status::text
                        WHEN 'OPEN' THEN 'DETECTED'
                        WHEN 'IN_PROGRESS' THEN 'ANALYZING'
                        WHEN 'CLOSED' THEN 'STOPPED'
                        ELSE status::text
                    END
                )::recovery_case_status_new;

                DROP TYPE recovery_case_status;
                ALTER TYPE recovery_case_status_new RENAME TO recovery_case_status;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE TYPE recovery_case_status_old AS ENUM (
            'OPEN',
            'IN_PROGRESS',
            'RECOVERED',
            'ESCALATED',
            'CLOSED'
        );

        ALTER TABLE recovery_cases
        ALTER COLUMN status TYPE recovery_case_status_old
        USING (
            CASE status::text
                WHEN 'DETECTED' THEN 'OPEN'
                WHEN 'ANALYZING' THEN 'IN_PROGRESS'
                WHEN 'ACTION_REQUIRED' THEN 'IN_PROGRESS'
                WHEN 'STOPPED' THEN 'CLOSED'
                ELSE status::text
            END
        )::recovery_case_status_old;

        DROP TYPE recovery_case_status;
        ALTER TYPE recovery_case_status_old RENAME TO recovery_case_status;
        """
    )
