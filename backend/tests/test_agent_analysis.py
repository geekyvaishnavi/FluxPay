from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentDecision, AuditLog, Customer, Payment, PaymentAttempt, RecoveryCase
from app.models.enums import (
    AuditEventType,
    CustomerStatus,
    FailureReason,
    PaymentStatus,
    RecoveryCaseStatus,
)
from app.services.ai.errors import AIProviderError
from app.services.ai.factory import get_llm_provider
from app.services.ai.provider import LLMProvider
from tests.conftest import create_case


class SuccessfulFakeProvider(LLMProvider):
    provider_name = "fake"
    model_name = "fake-recovery-model"

    def diagnose_recovery_case(self, context: dict[str, Any]) -> Mapping[str, Any]:
        assert context["customer"]["email"] == "maya@example.com"
        assert context["payment"]["amount"] == "250.00"
        assert context["latest_failure_reason"] == FailureReason.INSUFFICIENT_FUNDS.value
        return {
            "diagnosis": "temporary_insufficient_funds",
            "risk_level": "LOW",
            "recommended_action": "RETRY_PAYMENT",
            "delay_hours": 24,
            "confidence": 0.91,
            "reason": "Customer has a strong payment history with only one previous failure.",
        }


class InvalidFakeProvider(LLMProvider):
    provider_name = "fake"
    model_name = "invalid-output"

    def diagnose_recovery_case(self, context: dict[str, Any]) -> Mapping[str, Any]:
        return {
            "diagnosis": "",
            "risk_level": "CRITICAL",
            "recommended_action": "WIRE_MONEY",
            "delay_hours": -1,
            "confidence": 2,
        }


class FailingFakeProvider(LLMProvider):
    provider_name = "fake"
    model_name = "provider-down"

    def diagnose_recovery_case(self, context: dict[str, Any]) -> Mapping[str, Any]:
        raise AIProviderError("provider unavailable")


def override_provider(provider: LLMProvider):
    def _override() -> LLMProvider:
        return provider

    return _override


def create_failed_case(session: Session, payment: Payment) -> RecoveryCase:
    attempt = PaymentAttempt(
        payment_id=payment.id,
        attempt_number=1,
        status=PaymentStatus.FAILED,
        failure_reason=FailureReason.INSUFFICIENT_FUNDS,
        processor_code="insufficient_funds",
        message="Payment failed.",
        attempted_at=datetime.now(UTC),
    )
    session.add(attempt)
    return create_case(session, payment, RecoveryCaseStatus.DETECTED, Decimal("250.00"))


def test_successful_ai_analysis_persists_decision_and_updates_case(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = create_failed_case(session, payment)
    client.app.dependency_overrides[get_llm_provider] = override_provider(SuccessfulFakeProvider())

    response = client.post(f"/recovery/cases/{recovery_case.id}/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["recovery_case_id"] == recovery_case.id
    assert body["status"] == RecoveryCaseStatus.ACTION_REQUIRED.value
    assert body["decision"] == {
        "diagnosis": "temporary_insufficient_funds",
        "risk_level": "LOW",
        "recommended_action": "RETRY_PAYMENT",
        "delay_hours": 24,
        "confidence": 0.91,
        "reason": "Customer has a strong payment history with only one previous failure.",
    }

    session.refresh(recovery_case)
    assert recovery_case.status == RecoveryCaseStatus.ACTION_REQUIRED


def test_structured_response_validation_rejects_invalid_action(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = create_failed_case(session, payment)
    client.app.dependency_overrides[get_llm_provider] = override_provider(InvalidFakeProvider())

    response = client.post(f"/recovery/cases/{recovery_case.id}/analyze")

    assert response.status_code == 502
    assert response.json()["detail"] == "AI provider returned invalid output"
    decision = session.scalar(
        select(AgentDecision).where(AgentDecision.recovery_case_id == recovery_case.id)
    )
    assert decision is None


def test_ai_provider_failure_returns_service_unavailable(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = create_failed_case(session, payment)
    client.app.dependency_overrides[get_llm_provider] = override_provider(FailingFakeProvider())

    response = client.post(f"/recovery/cases/{recovery_case.id}/analyze")

    assert response.status_code == 503
    assert response.json()["detail"] == "AI provider unavailable"


def test_missing_recovery_case_returns_404(client: TestClient) -> None:
    client.app.dependency_overrides[get_llm_provider] = override_provider(SuccessfulFakeProvider())

    response = client.post("/recovery/cases/missing-case/analyze")

    assert response.status_code == 404
    assert response.json()["detail"] == "Recovery case not found"


def test_agent_decision_persistence_contains_audit_context(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = create_failed_case(session, payment)
    client.app.dependency_overrides[get_llm_provider] = override_provider(SuccessfulFakeProvider())

    response = client.post(f"/recovery/cases/{recovery_case.id}/analyze")

    assert response.status_code == 200
    decision = session.scalar(
        select(AgentDecision).where(AgentDecision.recovery_case_id == recovery_case.id)
    )
    assert decision is not None
    assert decision.provider == "fake"
    assert decision.model == "fake-recovery-model"
    assert decision.diagnosis == "temporary_insufficient_funds"
    assert decision.risk_level == "LOW"
    assert decision.recommended_action == "RETRY_PAYMENT"
    assert decision.delay_hours == 24
    assert decision.confidence == Decimal("0.9100")
    assert decision.reason == "Customer has a strong payment history with only one previous failure."
    assert decision.context_snapshot["customer"]["email"] == "maya@example.com"
    assert decision.raw_response["recommended_action"] == "RETRY_PAYMENT"


def test_successful_analysis_creates_audit_log(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = create_failed_case(session, payment)
    client.app.dependency_overrides[get_llm_provider] = override_provider(SuccessfulFakeProvider())

    response = client.post(f"/recovery/cases/{recovery_case.id}/analyze")

    assert response.status_code == 200
    audit_log = session.scalar(
        select(AuditLog)
        .where(AuditLog.recovery_case_id == recovery_case.id)
        .where(AuditLog.event_type == AuditEventType.AI_ANALYSIS_COMPLETED)
    )
    assert audit_log is not None
    assert audit_log.actor == "agent"
    assert audit_log.details["recommended_action"] == "RETRY_PAYMENT"


def test_failed_analysis_creates_audit_log(
    client: TestClient, session: Session, payment: Payment
) -> None:
    recovery_case = create_failed_case(session, payment)
    client.app.dependency_overrides[get_llm_provider] = override_provider(FailingFakeProvider())

    response = client.post(f"/recovery/cases/{recovery_case.id}/analyze")

    assert response.status_code == 503
    audit_log = session.scalar(
        select(AuditLog)
        .where(AuditLog.recovery_case_id == recovery_case.id)
        .where(AuditLog.event_type == AuditEventType.AI_ANALYSIS_FAILED)
    )
    assert audit_log is not None


def test_context_builder_counts_customer_payment_history(
    client: TestClient, session: Session, customer: Customer, payment: Payment
) -> None:
    successful_payment = Payment(
        customer_id=customer.id,
        amount=Decimal("125.00"),
        currency="USD",
        invoice_number="INV-HISTORY-001",
        status=PaymentStatus.SUCCEEDED,
        due_at=datetime.now(UTC),
    )
    failed_payment = Payment(
        customer_id=customer.id,
        amount=Decimal("150.00"),
        currency="USD",
        invoice_number="INV-HISTORY-002",
        status=PaymentStatus.FAILED,
        due_at=datetime.now(UTC),
    )
    other_customer = Customer(
        name="Other Customer",
        email="other@example.com",
        company_name="Other Co",
        status=CustomerStatus.ACTIVE,
    )
    session.add_all([successful_payment, failed_payment, other_customer])
    session.commit()

    recovery_case = create_failed_case(session, payment)
    client.app.dependency_overrides[get_llm_provider] = override_provider(SuccessfulFakeProvider())

    response = client.post(f"/recovery/cases/{recovery_case.id}/analyze")

    assert response.status_code == 200
    decision = session.scalar(
        select(AgentDecision).where(AgentDecision.recovery_case_id == recovery_case.id)
    )
    assert decision is not None
    assert decision.context_snapshot["previous_successful_payments"] == 2
    assert decision.context_snapshot["previous_payment_failures"] == 1
