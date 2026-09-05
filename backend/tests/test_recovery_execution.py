from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AgentDecision, AuditLog, Payment, PaymentAttempt, RecoveryAction, RecoveryCase
from app.models.enums import (
    AuditEventType,
    DecisionStatus,
    FailureReason,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
    RiskLevel,
)
from app.services.action_executor import ActionExecutor, get_action_executor
from tests.conftest import create_case


def override_executor(success: bool):
    def _override() -> ActionExecutor:
        return ActionExecutor(retry_simulator=lambda payment, recovery_case, attempt_number: success)

    return _override


def add_failed_attempt(
    session: Session,
    payment: Payment,
    attempt_number: int = 1,
    attempted_at: datetime | None = None,
) -> PaymentAttempt:
    attempt = PaymentAttempt(
        payment_id=payment.id,
        attempt_number=attempt_number,
        status=PaymentStatus.FAILED,
        failure_reason=FailureReason.INSUFFICIENT_FUNDS,
        processor_code="insufficient_funds",
        message="Payment failed.",
        attempted_at=attempted_at or datetime.now(UTC) - timedelta(hours=25),
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def add_decision(
    session: Session,
    recovery_case: RecoveryCase,
    action: RecoveryActionType,
    risk_level: RiskLevel = RiskLevel.LOW,
) -> AgentDecision:
    decision = AgentDecision(
        recovery_case_id=recovery_case.id,
        provider="fake",
        model="fake-model",
        recommended_action=action,
        diagnosis="test_diagnosis",
        risk_level=risk_level,
        delay_hours=24,
        confidence=Decimal("0.9000"),
        reason="Test decision.",
        status=DecisionStatus.VALIDATED,
        raw_response={
            "diagnosis": "test_diagnosis",
            "risk_level": risk_level.value,
            "recommended_action": action.value,
            "delay_hours": 24,
            "confidence": 0.9,
            "reason": "Test decision.",
        },
        context_snapshot={"latest_failure_reason": FailureReason.INSUFFICIENT_FUNDS.value},
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


def prepare_case(
    session: Session,
    payment: Payment,
    action: RecoveryActionType,
    risk_level: RiskLevel = RiskLevel.LOW,
    attempts: int = 1,
    latest_attempted_at: datetime | None = None,
) -> RecoveryCase:
    for attempt_number in range(1, attempts + 1):
        attempted_at = latest_attempted_at if attempt_number == attempts else datetime.now(UTC) - timedelta(days=3)
        add_failed_attempt(session, payment, attempt_number, attempted_at)
    recovery_case = create_case(session, payment, RecoveryCaseStatus.ACTION_REQUIRED, payment.amount)
    add_decision(session, recovery_case, action, risk_level)
    return recovery_case


def test_allowed_retry_creates_payment_attempt(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT)
    client.app.dependency_overrides[get_action_executor] = override_executor(False)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    assert response.json()["executed"] is True
    assert response.json()["action"] == RecoveryActionType.RETRY_PAYMENT.value
    attempt_count = session.scalar(
        select(func.count()).select_from(PaymentAttempt).where(PaymentAttempt.payment_id == payment.id)
    )
    assert attempt_count == 2


def test_retry_limit_exceeded_rejects_policy(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT, attempts=3)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    assert response.json()["executed"] is False
    assert response.json()["reason"] == "Escalation required after repeated failed attempts."
    blocked = session.scalar(select(RecoveryAction).where(RecoveryAction.status == RecoveryActionStatus.BLOCKED))
    assert blocked is not None


def test_retry_interval_violation_rejects_policy(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(
        session,
        payment,
        RecoveryActionType.RETRY_PAYMENT,
        latest_attempted_at=datetime.now(UTC) - timedelta(hours=2),
    )

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    assert response.json()["executed"] is False
    assert response.json()["reason"] == "Minimum retry interval has not elapsed."


def test_high_risk_case_restricts_automated_action(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(
        session,
        payment,
        RecoveryActionType.SEND_PAYMENT_LINK,
        risk_level=RiskLevel.HIGH,
    )

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    assert response.json()["executed"] is False
    assert response.json()["reason"] == "HIGH-risk cases require manual approval before automated action."


def test_escalation_marks_case_escalated(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.ESCALATE, risk_level=RiskLevel.HIGH)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    session.refresh(recovery_case)
    assert recovery_case.status == RecoveryCaseStatus.ESCALATED


def test_stop_marks_case_stopped(client: TestClient, session: Session, payment: Payment) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.STOP, risk_level=RiskLevel.HIGH)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    session.refresh(recovery_case)
    assert recovery_case.status == RecoveryCaseStatus.STOPPED


def test_simulated_successful_recovery_updates_revenue(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT)
    client.app.dependency_overrides[get_action_executor] = override_executor(True)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    assert response.json()["reason"] == "Simulated retry succeeded."
    session.refresh(payment)
    session.refresh(recovery_case)
    assert payment.status == PaymentStatus.RECOVERED
    assert recovery_case.status == RecoveryCaseStatus.RECOVERED
    assert recovery_case.recovered_revenue == Decimal("250.00")


def test_simulated_failed_recovery_keeps_case_action_required(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT)
    client.app.dependency_overrides[get_action_executor] = override_executor(False)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    assert response.json()["reason"] == "Simulated retry failed."
    session.refresh(recovery_case)
    assert recovery_case.status == RecoveryCaseStatus.ACTION_REQUIRED
    assert recovery_case.recovered_revenue == Decimal("0.00")


def test_duplicate_execution_is_idempotent(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT)
    client.app.dependency_overrides[get_action_executor] = override_executor(True)

    first = client.post(f"/recovery/cases/{recovery_case.id}/execute")
    second = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    attempt_count = session.scalar(
        select(func.count()).select_from(PaymentAttempt).where(PaymentAttempt.payment_id == payment.id)
    )
    assert attempt_count == 2
    session.refresh(recovery_case)
    assert recovery_case.recovered_revenue == Decimal("250.00")


def test_recovered_revenue_comes_from_payment_amount(
    client: TestClient, session: Session, payment: Payment
) -> None:
    payment.amount = Decimal("432.10")
    session.commit()
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT)
    client.app.dependency_overrides[get_action_executor] = override_executor(True)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    assert response.json()["recovered_revenue"] == "432.10"


def test_action_execution_creates_audit_logs(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT)
    client.app.dependency_overrides[get_action_executor] = override_executor(True)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    event_types = set(
        session.scalars(
            select(AuditLog.event_type).where(AuditLog.recovery_case_id == recovery_case.id)
        ).all()
    )
    assert AuditEventType.POLICY_EVALUATED in event_types
    assert AuditEventType.ACTION_EXECUTED in event_types
    assert AuditEventType.PAYMENT_RETRY_CREATED in event_types
    assert AuditEventType.PAYMENT_RECOVERED in event_types


def test_policy_rejection_creates_audit_log(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT, attempts=3)

    response = client.post(f"/recovery/cases/{recovery_case.id}/execute")

    assert response.status_code == 200
    audit_log = session.scalar(
        select(AuditLog)
        .where(AuditLog.recovery_case_id == recovery_case.id)
        .where(AuditLog.event_type == AuditEventType.POLICY_REJECTED)
    )
    assert audit_log is not None


def test_case_detail_returns_explainable_recovery_lifecycle(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = prepare_case(session, payment, RecoveryActionType.RETRY_PAYMENT)
    client.app.dependency_overrides[get_action_executor] = override_executor(True)
    client.post(f"/recovery/cases/{recovery_case.id}/execute")

    response = client.get(f"/recovery/cases/{recovery_case.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["customer"]["email"] == "maya@example.com"
    assert body["payment"]["failure_reason"] == FailureReason.INSUFFICIENT_FUNDS.value
    assert body["payment_history"]["attempt_count"] == 2
    assert body["decision"]["recommended_action"] == RecoveryActionType.RETRY_PAYMENT.value
    assert body["policy_result"]["allowed"] is True
    assert body["actions"][0]["result"]["retry_succeeded"] is True
    assert body["outcome"]["revenue_recovered"] == "250.00"
    assert "Payment failed because of insufficient funds" in body["explanation"]
    event_types = [event["event_type"] for event in body["audit_events"]]
    assert AuditEventType.POLICY_EVALUATED.value in event_types
    assert AuditEventType.PAYMENT_RECOVERED.value in event_types


def test_case_detail_returns_404_for_missing_case(client: TestClient) -> None:
    response = client.get("/recovery/cases/missing-case")

    assert response.status_code == 404
    assert response.json()["detail"] == "Recovery case not found"
