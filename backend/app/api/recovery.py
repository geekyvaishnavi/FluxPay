from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models import (
    AgentDecision,
    AuditLog,
    Customer,
    Payment,
    PaymentAttempt,
    RecoveryAction,
    RecoveryCase,
    RecoveryRun,
)
from app.schemas.ai_decision import AgentAnalysisResponse
from app.schemas.execution import ActionExecutionResult
from app.schemas.recovery import AuditActivityItem, RecoveryCaseDetail, RecoveryCaseListItem
from app.schemas.recovery_run import RecoveryRunHistoryItem, RecoveryRunProgress, RecoveryRunRequest, RecoveryRunSummary
from app.services.agent_analysis import analyze_recovery_case
from app.services.action_executor import ActionExecutor, get_action_executor
from app.services.ai.factory import get_llm_provider
from app.services.ai.provider import LLMProvider
from app.services.policy.rules import PolicyEngine, get_policy_engine
from app.services.recovery_execution import execute_recovery_case
from app.services.recovery_batch import recovery_run_progress, run_recovery_batch
from app.services.demo_data import reset_demo_dataset

router = APIRouter(prefix="/recovery", tags=["recovery"])


@router.get("/cases", response_model=list[RecoveryCaseListItem])
def list_recovery_cases(session: Session = Depends(get_db)):
    cases = session.execute(
        select(RecoveryCase, Payment, Customer)
        .join(Payment, RecoveryCase.payment_id == Payment.id)
        .join(Customer, Payment.customer_id == Customer.id)
        .order_by(RecoveryCase.created_at.desc(), RecoveryCase.id.desc())
    ).all()

    response: list[RecoveryCaseListItem] = []
    for recovery_case, payment, customer in cases:
        latest_attempt = session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id)
            .order_by(PaymentAttempt.attempted_at.desc(), PaymentAttempt.attempt_number.desc())
            .limit(1)
        )
        latest_decision = session.scalar(
            select(AgentDecision)
            .where(AgentDecision.recovery_case_id == recovery_case.id)
            .order_by(AgentDecision.created_at.desc(), AgentDecision.id.desc())
            .limit(1)
        )
        response.append(
            RecoveryCaseListItem(
                id=recovery_case.id,
                customer_name=customer.name,
                customer_email=customer.email,
                invoice_number=payment.invoice_number,
                payment_amount=payment.amount,
                currency=payment.currency,
                failure_reason=latest_attempt.failure_reason if latest_attempt else None,
                revenue_at_risk=recovery_case.revenue_at_risk,
                status=recovery_case.status,
                created_at=recovery_case.created_at,
                risk_level=latest_decision.risk_level if latest_decision else None,
                recommended_action=latest_decision.recommended_action if latest_decision else None,
            )
        )

    return response


@router.get("/cases/{case_id}", response_model=RecoveryCaseDetail)
def get_recovery_case(case_id: str, session: Session = Depends(get_db)):
    row = session.execute(
        select(RecoveryCase, Payment, Customer)
        .join(Payment, RecoveryCase.payment_id == Payment.id)
        .join(Customer, Payment.customer_id == Customer.id)
        .where(RecoveryCase.id == case_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Recovery case not found")

    recovery_case, payment, customer = row
    attempts = session.scalars(
        select(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment.id)
        .order_by(PaymentAttempt.attempt_number.desc())
    ).all()
    decision = session.scalar(
        select(AgentDecision)
        .where(AgentDecision.recovery_case_id == recovery_case.id)
        .order_by(AgentDecision.created_at.desc(), AgentDecision.id.desc())
        .limit(1)
    )
    actions = session.scalars(
        select(RecoveryAction)
        .where(RecoveryAction.recovery_case_id == recovery_case.id)
        .order_by(RecoveryAction.created_at.desc(), RecoveryAction.id.desc())
    ).all()
    audit_logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.recovery_case_id == recovery_case.id)
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    policy_audit = next(
        (
            audit_log
            for audit_log in reversed(audit_logs)
            if audit_log.event_type.value in {"POLICY_EVALUATED", "POLICY_REJECTED"}
        ),
        None,
    )
    policy_result = policy_audit.details if policy_audit else next(
        (action.result.get("policy") for action in actions if action.result.get("policy") is not None),
        None,
    )
    previous_successes = int(decision.context_snapshot.get("previous_successful_payments", 0)) if decision else 0
    previous_failures = int(decision.context_snapshot.get("previous_payment_failures", 0)) if decision else 0
    failure_attempt = next((attempt for attempt in attempts if attempt.failure_reason is not None), None)
    failure_reason = failure_attempt.failure_reason.value if failure_attempt else None
    return RecoveryCaseDetail(
        id=recovery_case.id,
        status=recovery_case.status,
        revenue_at_risk=recovery_case.revenue_at_risk,
        recovered_revenue=recovery_case.recovered_revenue,
        opened_at=recovery_case.opened_at,
        closed_at=recovery_case.closed_at,
        customer={
            "name": customer.name,
            "email": customer.email,
            "company_name": customer.company_name,
            "status": customer.status.value,
        },
        payment={
            "invoice_number": payment.invoice_number,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "status": payment.status.value,
            "due_at": payment.due_at,
            "failure_reason": failure_reason,
        },
        payment_history={
            "attempt_count": len(attempts),
            "failed_attempts": sum(attempt.status.value == "FAILED" for attempt in attempts),
            "latest_attempt_at": attempts[0].attempted_at if attempts else None,
            "previous_successful_payments": previous_successes,
            "previous_payment_failures": previous_failures,
        },
        decision=(
            {
                "diagnosis": decision.diagnosis,
                "risk_level": decision.risk_level.value,
                "recommended_action": decision.recommended_action.value,
                "confidence": str(decision.confidence),
                "expected_recovery_probability": str(decision.expected_recovery_probability),
                "reason": decision.reason,
                "delay_hours": decision.delay_hours,
                "created_at": decision.created_at,
            }
            if decision
            else None
        ),
        policy_result=policy_result,
        actions=[
            {
                "action_type": action.action_type.value,
                "status": action.status.value,
                "reason": action.reason,
                "result": action.result,
                "executed_at": action.executed_at,
                "created_at": action.created_at,
            }
            for action in actions
        ],
        audit_events=[
            {
                "event_type": audit_log.event_type.value,
                "actor": audit_log.actor,
                "created_at": audit_log.created_at,
            }
            for audit_log in audit_logs
        ],
        explanation=_build_case_explanation(
            failure_reason=failure_reason,
            previous_successes=previous_successes,
            previous_failures=previous_failures,
            decision=decision,
        ),
        outcome={
            "status": recovery_case.status.value,
            "revenue_at_risk": str(recovery_case.revenue_at_risk),
            "revenue_recovered": str(recovery_case.recovered_revenue),
            "closed_at": recovery_case.closed_at,
        },
    )


def _build_case_explanation(
    failure_reason: str | None,
    previous_successes: int,
    previous_failures: int,
    decision: AgentDecision | None,
) -> str | None:
    if decision is None:
        return None
    failure = (failure_reason or "an unknown payment issue").replace("_", " ").lower()
    action = decision.recommended_action.value.replace("_", " ").lower()
    return (
        f"Payment failed because of {failure}. The customer has {previous_successes} previous "
        f"successful payments and {previous_failures} previous payment failures. Revive recommended "
        f"{action} because {decision.reason}"
    )


def _audit_item(audit_log: AuditLog) -> AuditActivityItem:
    return AuditActivityItem(
        id=audit_log.id,
        recovery_case_id=audit_log.recovery_case_id,
        event_type=audit_log.event_type.value,
        actor=audit_log.actor,
        details=audit_log.details,
        created_at=audit_log.created_at,
    )


@router.get("/cases/{case_id}/audit", response_model=list[AuditActivityItem])
def get_case_audit(case_id: str, session: Session = Depends(get_db)):
    if session.get(RecoveryCase, case_id) is None:
        raise HTTPException(status_code=404, detail="Recovery case not found")
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.recovery_case_id == case_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    return [_audit_item(audit_log) for audit_log in logs]


@router.get("/audit-logs", response_model=list[AuditActivityItem])
def list_audit_logs(
    event_type: str | None = None,
    case_id: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    session: Session = Depends(get_db),
):
    query = select(AuditLog)
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if case_id:
        query = query.where(AuditLog.recovery_case_id == case_id)
    if start_at:
        query = query.where(AuditLog.created_at >= start_at)
    if end_at:
        query = query.where(AuditLog.created_at <= end_at)
    logs = session.scalars(query.order_by(AuditLog.created_at, AuditLog.id).limit(200)).all()
    return [_audit_item(audit_log) for audit_log in logs]


@router.get("/audit-activity", response_model=list[AuditActivityItem])
def list_audit_activity(limit: int = 12, session: Session = Depends(get_db)):
    limit = min(max(limit, 1), 50)
    logs = session.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
    ).all()
    return [
        AuditActivityItem(
            id=audit_log.id,
            recovery_case_id=audit_log.recovery_case_id,
            event_type=audit_log.event_type.value,
            actor=audit_log.actor,
            details=audit_log.details,
            created_at=audit_log.created_at,
        )
        for audit_log in logs
    ]


@router.post("/cases/{case_id}/analyze", response_model=AgentAnalysisResponse)
def analyze_case(
    case_id: str,
    session: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
):
    return analyze_recovery_case(session=session, recovery_case_id=case_id, provider=provider)


@router.post("/cases/{case_id}/execute", response_model=ActionExecutionResult)
def execute_case(
    case_id: str,
    session: Session = Depends(get_db),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    action_executor: ActionExecutor = Depends(get_action_executor),
):
    return execute_recovery_case(
        session=session,
        recovery_case_id=case_id,
        policy_engine=policy_engine,
        action_executor=action_executor,
    )


@router.post("/run", response_model=RecoveryRunSummary)
def run_recovery(
    request: RecoveryRunRequest | None = None,
    session: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    action_executor: ActionExecutor = Depends(get_action_executor),
):
    return run_recovery_batch(
        session=session,
        request=request or RecoveryRunRequest(),
        provider=provider,
        policy_engine=policy_engine,
        action_executor=action_executor,
    )


@router.post("/run/live", response_model=RecoveryRunProgress, status_code=202)
def start_live_recovery(
    request: RecoveryRunRequest | None = None,
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_db),
):
    recovery_request = request or RecoveryRunRequest()
    recovery_run = RecoveryRun(
        idempotency_key=recovery_request.idempotency_key,
        started_at=datetime.now(UTC).replace(microsecond=0),
        status="QUEUED",
        demo_mode=recovery_request.demo_mode,
    )
    session.add(recovery_run)
    session.commit()
    session.refresh(recovery_run)
    background_tasks.add_task(_run_live_recovery, recovery_run.id, recovery_request)
    return recovery_run_progress(recovery_run)


def _run_live_recovery(recovery_run_id: str, request: RecoveryRunRequest) -> None:
    from app.services.action_executor import get_action_executor
    from app.services.ai.factory import get_llm_provider
    from app.services.policy.rules import get_policy_engine

    with SessionLocal() as session:
        run_recovery_batch(
            session=session,
            request=request,
            provider=get_llm_provider(),
            policy_engine=get_policy_engine(),
            action_executor=get_action_executor(),
            recovery_run_id=recovery_run_id,
        )


@router.get("/runs/{run_id}/progress", response_model=RecoveryRunProgress)
def get_recovery_run_progress(run_id: str, session: Session = Depends(get_db)):
    recovery_run = session.get(RecoveryRun, run_id)
    if recovery_run is None:
        raise HTTPException(status_code=404, detail="Recovery run not found")
    return recovery_run_progress(recovery_run)


@router.post("/demo/reset")
def reset_demo(session: Session = Depends(get_db)):
    return reset_demo_dataset(session)


@router.get("/runs", response_model=list[RecoveryRunHistoryItem])
def list_recovery_runs(session: Session = Depends(get_db)):
    runs = session.scalars(
        select(RecoveryRun).order_by(RecoveryRun.started_at.desc(), RecoveryRun.id.desc())
    ).all()
    return [
        RecoveryRunHistoryItem(
            run_id=recovery_run.id,
            cases_processed=recovery_run.cases_processed,
            actions_executed=recovery_run.actions_executed,
            recovered_cases=recovery_run.recovered_cases,
            escalated_cases=recovery_run.escalated_cases,
            stopped_cases=recovery_run.stopped_cases,
            revenue_at_risk=recovery_run.revenue_at_risk,
            revenue_recovered=recovery_run.revenue_recovered,
            recovery_rate=recovery_run.recovery_rate,
            started_at=recovery_run.started_at,
            finished_at=recovery_run.finished_at,
        )
        for recovery_run in runs
    ]
