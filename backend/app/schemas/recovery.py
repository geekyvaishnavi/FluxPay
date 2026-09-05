from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import (
    FailureReason,
    RecoveryActionType,
    RecoveryCaseStatus,
    RiskLevel,
)


class RecoveryCaseCreatedResponse(BaseModel):
    id: str
    payment_id: str
    status: RecoveryCaseStatus
    revenue_at_risk: Decimal
    recovered_revenue: Decimal
    created_at: datetime


class RecoveryCaseListItem(BaseModel):
    id: str
    customer_name: str
    customer_email: str
    invoice_number: str
    payment_amount: Decimal
    currency: str
    failure_reason: FailureReason | None
    revenue_at_risk: Decimal
    status: RecoveryCaseStatus
    created_at: datetime
    risk_level: RiskLevel | None = None
    recommended_action: RecoveryActionType | None = None


class RecoveryCaseDetail(BaseModel):
    id: str
    status: RecoveryCaseStatus
    revenue_at_risk: Decimal
    recovered_revenue: Decimal
    opened_at: datetime
    closed_at: datetime | None
    customer: dict
    payment: dict
    payment_history: dict
    decision: dict | None
    policy_result: dict | None
    actions: list[dict]
    audit_events: list[dict]
    explanation: str | None
    outcome: dict


class AuditActivityItem(BaseModel):
    id: str
    recovery_case_id: str | None
    event_type: str
    actor: str
    details: dict
    created_at: datetime
