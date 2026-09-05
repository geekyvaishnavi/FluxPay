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
