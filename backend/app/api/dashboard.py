from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AgentDecision, Payment, PaymentAttempt, RecoveryAction, RecoveryCase
from app.models.enums import RecoveryCaseStatus
from app.schemas.dashboard import (
    DashboardMetrics,
    RecoveryActionMix,
    RecoveryAnalytics,
    RecoveryByFailureReason,
)

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


@router.get("/analytics", response_model=RecoveryAnalytics)
def get_recovery_analytics(session: Session = Depends(get_db)):
    """Dashboard-ready aggregates calculated from the latest state of every case."""
    cases = session.execute(
        select(RecoveryCase, Payment)
        .join(Payment, RecoveryCase.payment_id == Payment.id)
        .order_by(RecoveryCase.created_at.desc())
    ).all()

    by_reason: dict[str, dict[str, Decimal | int]] = {}
    by_action: dict[str, dict[str, int]] = {}
    expected_probabilities: list[Decimal] = []

    for recovery_case, payment in cases:
        failure_reason = session.scalar(
            select(PaymentAttempt.failure_reason)
            .where(PaymentAttempt.payment_id == payment.id)
            .where(PaymentAttempt.failure_reason.is_not(None))
            .order_by(PaymentAttempt.attempted_at.desc(), PaymentAttempt.attempt_number.desc())
            .limit(1)
        )
        reason_key = failure_reason.value if failure_reason else "UNKNOWN"
        reason = by_reason.setdefault(
            reason_key,
            {"case_count": 0, "revenue_at_risk": Decimal("0"), "revenue_recovered": Decimal("0")},
        )
        reason["case_count"] = int(reason["case_count"]) + 1
        reason["revenue_at_risk"] = Decimal(reason["revenue_at_risk"]) + recovery_case.revenue_at_risk
        reason["revenue_recovered"] = Decimal(reason["revenue_recovered"]) + recovery_case.recovered_revenue

        decision = session.scalar(
            select(AgentDecision)
            .where(AgentDecision.recovery_case_id == recovery_case.id)
            .order_by(AgentDecision.created_at.desc(), AgentDecision.id.desc())
            .limit(1)
        )
        if decision is None:
            continue
        expected_probabilities.append(decision.expected_recovery_probability)
        action_key = decision.recommended_action.value
        action = by_action.setdefault(action_key, {"case_count": 0, "recovered_cases": 0})
        action["case_count"] = int(action["case_count"]) + 1
        action["recovered_cases"] = int(action["recovered_cases"]) + int(
            recovery_case.status == RecoveryCaseStatus.RECOVERED
        )

    recovery_by_failure_reason = []
    for reason, values in by_reason.items():
        at_risk = _money(Decimal(values["revenue_at_risk"]))
        recovered = _money(Decimal(values["revenue_recovered"]))
        rate = (recovered / at_risk * Decimal("100")) if at_risk else Decimal("0")
        recovery_by_failure_reason.append(
            RecoveryByFailureReason(
                failure_reason=reason,
                case_count=int(values["case_count"]),
                revenue_at_risk=at_risk,
                revenue_recovered=recovered,
                recovery_rate=rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
        )
    recovery_by_failure_reason.sort(key=lambda item: item.revenue_at_risk, reverse=True)

    action_mix = []
    for action_name, values in by_action.items():
        count = int(values["case_count"])
        recovered_cases = int(values["recovered_cases"])
        action_mix.append(
            RecoveryActionMix(
                action=action_name,
                case_count=count,
                recovered_cases=recovered_cases,
                recovery_rate=(Decimal(recovered_cases * 100) / count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if count else Decimal("0"),
            )
        )
    action_mix.sort(key=lambda item: item.case_count, reverse=True)

    total_at_risk = sum((Decimal(case.revenue_at_risk) for case, _ in cases), Decimal("0"))
    total_recovered = sum((Decimal(case.recovered_revenue) for case, _ in cases), Decimal("0"))
    actual_rate = (total_recovered / total_at_risk * Decimal("100")) if total_at_risk else Decimal("0")
    expected_rate = (
        sum(expected_probabilities, Decimal("0")) / len(expected_probabilities) * Decimal("100")
        if expected_probabilities
        else Decimal("0")
    )
    return RecoveryAnalytics(
        recovery_by_failure_reason=recovery_by_failure_reason,
        expected_recovery_rate=expected_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        actual_recovery_rate=actual_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        action_mix=action_mix,
    )
