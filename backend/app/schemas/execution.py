from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import RecoveryActionType, RecoveryCaseStatus


class PolicyEvaluationResult(BaseModel):
    allowed: bool
    action: RecoveryActionType
    reason: str


class ActionExecutionResult(BaseModel):
    executed: bool
    idempotent: bool = False
    action: RecoveryActionType
    status: RecoveryCaseStatus
    reason: str
    recovered_revenue: Decimal
    payment_attempt_id: str | None = None
    recovery_action_id: str | None = None
    executed_at: datetime | None = None
    policy: PolicyEvaluationResult
