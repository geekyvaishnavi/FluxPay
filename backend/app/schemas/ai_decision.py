from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import RecoveryActionType, RiskLevel


class AgentDecisionOutput(BaseModel):
    diagnosis: str = Field(min_length=1)
    risk_level: RiskLevel
    recommended_action: RecoveryActionType
    delay_hours: int = Field(ge=0, le=720)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class AgentContext(BaseModel):
    recovery_case_id: str
    recovery_case_status: str
    customer: dict
    payment: dict
    latest_failure_reason: str | None
    previous_payment_failures: int
    previous_successful_payments: int
    previous_recovery_attempts: int


class AgentAnalysisResponse(BaseModel):
    decision_id: str
    recovery_case_id: str
    status: Literal["ACTION_REQUIRED"]
    decision: AgentDecisionOutput
