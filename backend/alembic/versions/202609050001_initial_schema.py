"""initial schema

Revision ID: 202609050001
Revises:
Create Date: 2026-09-05 00:01:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202609050001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    customer_status = sa.Enum("ACTIVE", "PAST_DUE", "CHURN_RISK", name="customer_status")
    payment_status = sa.Enum("SUCCEEDED", "FAILED", "RECOVERED", "CANCELED", name="payment_status")
    failure_reason = sa.Enum(
        "INSUFFICIENT_FUNDS",
        "EXPIRED_CARD",
        "CARD_DECLINED",
        "PROCESSOR_ERROR",
        "AUTHENTICATION_REQUIRED",
        name="failure_reason",
    )
    recovery_case_status = sa.Enum(
        "DETECTED",
        "ANALYZING",
        "ACTION_REQUIRED",
        "RECOVERED",
        "ESCALATED",
        "STOPPED",
        name="recovery_case_status",
    )
    recovery_action_type = sa.Enum(
        "RETRY_PAYMENT", "SEND_PAYMENT_LINK", "ESCALATE", "STOP", name="recovery_action_type"
    )
    recovery_action_status = sa.Enum(
        "PROPOSED", "APPROVED", "EXECUTED", "BLOCKED", name="recovery_action_status"
    )
    decision_status = sa.Enum("PROPOSED", "VALIDATED", "REJECTED", name="decision_status")
    audit_event_type = sa.Enum(
        "CASE_CREATED", "PAYMENT_FAILED", "ACTION_SEEDED", "DECISION_SEEDED", name="audit_event_type"
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("status", customer_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_customers_email"), "customers", ["email"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_index(op.f("ix_payments_customer_id"), "payments", ["customer_id"], unique=False)

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("failure_reason", failure_reason, nullable=True),
        sa.Column("processor_code", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_attempts_payment_id"), "payment_attempts", ["payment_id"], unique=False)

    op.create_table(
        "recovery_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("status", recovery_case_status, nullable=False),
        sa.Column("revenue_at_risk", sa.Numeric(12, 2), nullable=False),
        sa.Column("recovered_revenue", sa.Numeric(12, 2), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id"),
    )

    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recovery_case_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("recommended_action", recovery_action_type, nullable=False),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("status", decision_status, nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_decisions_recovery_case_id"),
        "agent_decisions",
        ["recovery_case_id"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recovery_case_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", audit_event_type, nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_recovery_case_id"), "audit_logs", ["recovery_case_id"], unique=False)

    op.create_table(
        "recovery_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recovery_case_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", recovery_action_type, nullable=False),
        sa.Column("status", recovery_action_status, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recovery_actions_recovery_case_id"),
        "recovery_actions",
        ["recovery_case_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recovery_actions_recovery_case_id"), table_name="recovery_actions")
    op.drop_table("recovery_actions")
    op.drop_index(op.f("ix_audit_logs_recovery_case_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_agent_decisions_recovery_case_id"), table_name="agent_decisions")
    op.drop_table("agent_decisions")
    op.drop_table("recovery_cases")
    op.drop_index(op.f("ix_payment_attempts_payment_id"), table_name="payment_attempts")
    op.drop_table("payment_attempts")
    op.drop_index(op.f("ix_payments_customer_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_customers_email"), table_name="customers")
    op.drop_table("customers")

    bind = op.get_bind()
    for name in [
        "audit_event_type",
        "decision_status",
        "recovery_action_status",
        "recovery_action_type",
        "recovery_case_status",
        "failure_reason",
        "payment_status",
        "customer_status",
    ]:
        sa.Enum(name=name).drop(bind, checkfirst=True)
