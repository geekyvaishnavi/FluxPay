from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AgentDecision, RecoveryAction, RecoveryCase, RecoveryRun
from app.models.enums import RecoveryActionStatus, RecoveryCaseStatus
from app.schemas.recovery_run import RecoveryRunRequest, RecoveryRunSummary
from app.services.action_executor import ActionExecutor, SimulationConfig
from app.services.agent_analysis import analyze_recovery_case
from app.services.ai.provider import LLMProvider
from app.services.policy.rules import PolicyEngine
from app.services.recovery_execution import execute_recovery_case


ELIGIBLE_STATUSES = {RecoveryCaseStatus.DETECTED, RecoveryCaseStatus.ACTION_REQUIRED}


def run_recovery_batch(
    session: Session,
    request: RecoveryRunRequest,
    provider: LLMProvider,
    policy_engine: PolicyEngine,
    action_executor: ActionExecutor,
    recovery_run_id: str | None = None,
) -> RecoveryRunSummary:
    if recovery_run_id is None and request.idempotency_key:
        existing_run = session.scalar(
            select(RecoveryRun).where(RecoveryRun.idempotency_key == request.idempotency_key)
        )
        if existing_run is not None:
            return _summary(existing_run)

    if recovery_run_id is not None:
        recovery_run = session.get(RecoveryRun, recovery_run_id)
        if recovery_run is None:
            raise HTTPException(status_code=404, detail="Recovery run not found")
        recovery_run.status = "RUNNING"
        session.commit()
    else:
        recovery_run = RecoveryRun(
            idempotency_key=request.idempotency_key,
            started_at=datetime.now(UTC).replace(microsecond=0),
            status="RUNNING",
            demo_mode=request.demo_mode,
        )
        session.add(recovery_run)
        session.commit()

    executor = _configured_executor(action_executor, request)
    eligible_cases = _eligible_cases(session)
    eligible_case_ids = [case.id for case in eligible_cases]
    recovery_run.cases_processed = len(eligible_cases)
    recovery_run.total_cases = len(eligible_cases)
    recovery_run.revenue_at_risk = _money(sum((case.revenue_at_risk for case in eligible_cases), Decimal()))
    session.commit()

    for recovery_case in eligible_cases:
        recovery_run.current_case_id = recovery_case.id
        session.commit()
        if not _has_decision(session, recovery_case):
            try:
                analyze_recovery_case(session, recovery_case.id, provider)
            except HTTPException:
                recovery_run.processed_cases += 1
                recovery_run.failed_cases += 1
                session.commit()
                continue

        try:
            result = execute_recovery_case(
                session=session,
                recovery_case_id=recovery_case.id,
                policy_engine=policy_engine,
                action_executor=executor,
            )
        except HTTPException:
            recovery_run.processed_cases += 1
            recovery_run.failed_cases += 1
            session.commit()
            continue
        if result.executed and not result.idempotent:
            recovery_run.actions_executed += 1
        recovery_run.processed_cases += 1
        session.commit()

    session.expire_all()
    processed_cases = session.scalars(
        select(RecoveryCase).where(RecoveryCase.id.in_(eligible_case_ids))
    ).all()
    recovery_run.recovered_cases = sum(
        case.status == RecoveryCaseStatus.RECOVERED for case in processed_cases
    )
    recovery_run.escalated_cases = sum(
        case.status == RecoveryCaseStatus.ESCALATED for case in processed_cases
    )
    recovery_run.stopped_cases = sum(case.status == RecoveryCaseStatus.STOPPED for case in processed_cases)
    recovery_run.revenue_recovered = _money(
        sum((case.recovered_revenue for case in processed_cases), Decimal())
    )
    recovery_run.recovery_rate = _recovery_rate(
        recovery_run.revenue_recovered, recovery_run.revenue_at_risk
    )
    recovery_run.finished_at = datetime.now(UTC).replace(microsecond=0)
    recovery_run.current_case_id = None
    recovery_run.status = "COMPLETED"
    session.commit()
    session.refresh(recovery_run)
    return _summary(recovery_run)


def _eligible_cases(session: Session) -> list[RecoveryCase]:
    candidates = session.scalars(
        select(RecoveryCase)
        .where(RecoveryCase.status.in_(ELIGIBLE_STATUSES))
        .order_by(RecoveryCase.created_at, RecoveryCase.id)
    ).all()
    return [case for case in candidates if _needs_processing(session, case)]


def _needs_processing(session: Session, recovery_case: RecoveryCase) -> bool:
    decision = session.scalar(
        select(AgentDecision)
        .where(AgentDecision.recovery_case_id == recovery_case.id)
        .order_by(AgentDecision.created_at.desc(), AgentDecision.id.desc())
        .limit(1)
    )
    if decision is None:
        return True
    action = session.scalar(
        select(RecoveryAction)
        .where(RecoveryAction.recovery_case_id == recovery_case.id)
        .where(RecoveryAction.action_type == decision.recommended_action.value)
        .where(
            RecoveryAction.status.in_(
                {RecoveryActionStatus.EXECUTED, RecoveryActionStatus.BLOCKED}
            )
        )
        .limit(1)
    )
    return action is None


def _has_decision(session: Session, recovery_case: RecoveryCase) -> bool:
    return session.scalar(
        select(AgentDecision.id)
        .where(AgentDecision.recovery_case_id == recovery_case.id)
        .limit(1)
    ) is not None


def _configured_executor(action_executor: ActionExecutor, request: RecoveryRunRequest) -> ActionExecutor:
    if not any(
        (
            request.retry_success_probability is not None,
            request.payment_link_success_probability is not None,
            request.simulation_seed is not None,
        )
    ):
        return action_executor
    return action_executor.with_simulation_config(
        SimulationConfig(
            retry_success_probability=(
                request.retry_success_probability
                if request.retry_success_probability is not None
                else Decimal(str(settings.retry_success_probability))
            ),
            payment_link_success_probability=(
                request.payment_link_success_probability
                if request.payment_link_success_probability is not None
                else Decimal(str(settings.payment_link_success_probability))
            ),
            seed=request.simulation_seed or settings.simulation_seed,
        )
    )


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _recovery_rate(recovered: Decimal, at_risk: Decimal) -> Decimal:
    if not at_risk:
        return Decimal("0.0000")
    return (recovered / at_risk).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _summary(recovery_run: RecoveryRun) -> RecoveryRunSummary:
    return RecoveryRunSummary(
        run_id=recovery_run.id,
        cases_processed=recovery_run.cases_processed,
        actions_executed=recovery_run.actions_executed,
        recovered_cases=recovery_run.recovered_cases,
        escalated_cases=recovery_run.escalated_cases,
        stopped_cases=recovery_run.stopped_cases,
        revenue_at_risk=recovery_run.revenue_at_risk,
        revenue_recovered=recovery_run.revenue_recovered,
        recovery_rate=recovery_run.recovery_rate,
    )


def recovery_run_progress(recovery_run: RecoveryRun):
    from app.schemas.recovery_run import RecoveryRunProgress

    return RecoveryRunProgress(
        **_summary(recovery_run).model_dump(),
        status=recovery_run.status,
        total_cases=recovery_run.total_cases,
        processed_cases=recovery_run.processed_cases,
        failed_cases=recovery_run.failed_cases,
        current_case_id=recovery_run.current_case_id,
    )
