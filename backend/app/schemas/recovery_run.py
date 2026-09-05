from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class RecoveryRunRequest(BaseModel):
    retry_success_probability: Decimal | None = Field(default=None, ge=0, le=1)
    payment_link_success_probability: Decimal | None = Field(default=None, ge=0, le=1)
    simulation_seed: str | None = Field(default=None, min_length=1, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    demo_mode: bool = False


class RecoveryRunSummary(BaseModel):
    run_id: str
    cases_processed: int
    actions_executed: int
    recovered_cases: int
    escalated_cases: int
    stopped_cases: int
    revenue_at_risk: Decimal
    revenue_recovered: Decimal
    recovery_rate: Decimal


class RecoveryRunHistoryItem(RecoveryRunSummary):
    started_at: datetime
    finished_at: datetime | None


class RecoveryRunProgress(RecoveryRunSummary):
    status: str
    total_cases: int
    processed_cases: int
    failed_cases: int
    current_case_id: str | None
