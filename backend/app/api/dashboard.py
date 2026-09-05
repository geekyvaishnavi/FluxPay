from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AgentDecision, RecoveryAction, RecoveryCase
from app.models.enums import RecoveryCaseStatus
from app.schemas.dashboard import DashboardMetrics

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ACTIVE_STATUSES = {
    RecoveryCaseStatus.DETECTED,
    RecoveryCaseStatus.ANALYZING,
    RecoveryCaseStatus.ACTION_REQUIRED,
    RecoveryCaseStatus.ESCALATED,
}


def _money(value: Decimal | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@router.get("/metrics", response_model=DashboardMetrics)
def get_dashboard_metrics(session: Session = Depends(get_db)):
    total_revenue_at_risk = _money(session.scalar(select(func.sum(RecoveryCase.revenue_at_risk))))
    total_recovered_revenue = _money(
        session.scalar(select(func.sum(RecoveryCase.recovered_revenue)))
    )
    active_recovery_cases = session.scalar(
        select(func.count()).select_from(RecoveryCase).where(RecoveryCase.status.in_(ACTIVE_STATUSES))
    )
    recovered_cases = session.scalar(
        select(func.count())
        .select_from(RecoveryCase)
        .where(RecoveryCase.status == RecoveryCaseStatus.RECOVERED)
    )
    total_recovery_cases = session.scalar(select(func.count()).select_from(RecoveryCase))
    retrying_cases = session.scalar(
        select(func.count())
        .select_from(RecoveryCase)
        .join(RecoveryAction, RecoveryAction.recovery_case_id == RecoveryCase.id)
        .where(RecoveryCase.status == RecoveryCaseStatus.ACTION_REQUIRED)
        .where(RecoveryAction.action_type == "RETRY_PAYMENT")
    )
    escalated_cases = session.scalar(
        select(func.count())
        .select_from(RecoveryCase)
        .where(RecoveryCase.status == RecoveryCaseStatus.ESCALATED)
    )
    stopped_cases = session.scalar(
        select(func.count())
        .select_from(RecoveryCase)
        .where(RecoveryCase.status == RecoveryCaseStatus.STOPPED)
    )
    average_expected_recovery_probability = Decimal(
        session.scalar(select(func.avg(AgentDecision.expected_recovery_probability))) or 0
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    recovery_rate = Decimal("0.00")
    if total_revenue_at_risk > 0:
        recovery_rate = (
            (total_recovered_revenue / total_revenue_at_risk) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    expected_recovery_rate = (average_expected_recovery_probability * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    expected_vs_actual_recovery = (recovery_rate - expected_recovery_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return DashboardMetrics(
        total_revenue_at_risk=total_revenue_at_risk,
        total_recovered_revenue=total_recovered_revenue,
        active_recovery_cases=active_recovery_cases or 0,
        recovered_cases=recovered_cases or 0,
        recovery_rate=recovery_rate,
        total_recovery_cases=total_recovery_cases or 0,
        retrying_cases=retrying_cases or 0,
        escalated_cases=escalated_cases or 0,
        stopped_cases=stopped_cases or 0,
        average_expected_recovery_probability=average_expected_recovery_probability,
        expected_recovery_rate=expected_recovery_rate,
        expected_vs_actual_recovery=expected_vs_actual_recovery,
    )
