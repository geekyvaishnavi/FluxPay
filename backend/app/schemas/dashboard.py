from decimal import Decimal

from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    total_revenue_at_risk: Decimal
    total_recovered_revenue: Decimal
    active_recovery_cases: int
    recovered_cases: int
    recovery_rate: Decimal
    total_recovery_cases: int
    retrying_cases: int
    escalated_cases: int
    stopped_cases: int
    average_expected_recovery_probability: Decimal
    expected_recovery_rate: Decimal
    expected_vs_actual_recovery: Decimal


class RecoveryByFailureReason(BaseModel):
    failure_reason: str
    case_count: int
    revenue_at_risk: Decimal
    revenue_recovered: Decimal
    recovery_rate: Decimal


class RecoveryActionMix(BaseModel):
    action: str
    case_count: int
    recovered_cases: int
    recovery_rate: Decimal


class RecoveryAnalytics(BaseModel):
    recovery_by_failure_reason: list[RecoveryByFailureReason]
    expected_recovery_rate: Decimal
    actual_recovery_rate: Decimal
    action_mix: list[RecoveryActionMix]
