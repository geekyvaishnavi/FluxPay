from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Customer, Payment, PaymentAttempt, RecoveryAction, RecoveryCase, RecoveryRun
from app.models.enums import (
    AuditEventType,
    FailureReason,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryCaseStatus,
)
from app.services.ai.factory import get_llm_provider
from app.services.ai.provider import LLMProvider


class BatchProvider(LLMProvider):
    provider_name = "batch-fake"
    model_name = "batch-fake-v1"

    def diagnose_recovery_case(self, context: dict[str, Any]) -> Mapping[str, Any]:
        amount = context["payment"]["amount"]
        if amount == "300.00":
            risk_level = "HIGH"
        else:
            risk_level = "LOW"
        if amount == "400.00":
            action = "ESCALATE"
        elif amount == "150.00":
            action = "SEND_PAYMENT_LINK"
        else:
            action = "RETRY_PAYMENT"
        return {
            "diagnosis": "batch_test",
            "risk_level": risk_level,
            "recommended_action": action,
            "delay_hours": 24,
            "confidence": 0.9,
            "expected_recovery_probability": 0.75,
            "reason": "Batch test decision.",
        }


def override_provider() -> LLMProvider:
    return BatchProvider()


def create_batch_case(session: Session, customer: Customer, amount: str, number: int) -> RecoveryCase:
    payment = Payment(
        customer_id=customer.id,
        amount=Decimal(amount),
        currency="USD",
        invoice_number=f"INV-BATCH-{number:03}",
        status=PaymentStatus.FAILED,
        due_at=datetime.now(UTC),
    )
    session.add(payment)
    session.flush()
    session.add(
        PaymentAttempt(
            payment_id=payment.id,
            attempt_number=1,
            status=PaymentStatus.FAILED,
            failure_reason=FailureReason.INSUFFICIENT_FUNDS,
            attempted_at=datetime.now(UTC) - timedelta(hours=25),
        )
    )
    recovery_case = RecoveryCase(
        payment_id=payment.id,
        status=RecoveryCaseStatus.DETECTED,
        revenue_at_risk=Decimal(amount),
        recovered_revenue=Decimal("0.00"),
        priority="MEDIUM",
        opened_at=datetime.now(UTC),
    )
    session.add(recovery_case)
    session.commit()
    return recovery_case


def test_batch_processes_cases_and_persists_metrics(
    client: TestClient, session: Session, customer: Customer
) -> None:
    recovery_cases = [
        create_batch_case(session, customer, amount, number)
        for number, amount in enumerate(("100.00", "200.00", "300.00", "400.00"), start=1)
    ]
    client.app.dependency_overrides[get_llm_provider] = override_provider

    response = client.post("/recovery/run", json={"retry_success_probability": 1})

    assert response.status_code == 200
    assert response.json() == {
        "run_id": response.json()["run_id"],
        "cases_processed": 4,
        "actions_executed": 3,
        "recovered_cases": 2,
        "escalated_cases": 1,
        "stopped_cases": 0,
        "revenue_at_risk": "1000.00",
        "revenue_recovered": "300.00",
        "recovery_rate": "0.3000",
    }
    run = session.scalar(select(RecoveryRun))
    assert run is not None
    assert run.finished_at is not None
    assert run.revenue_recovered == Decimal("300.00")
    blocked_case = recovery_cases[2]
    blocked_action = session.scalar(
        select(RecoveryAction).where(RecoveryAction.recovery_case_id == blocked_case.id)
    )
    assert blocked_action is not None
    assert blocked_action.status == RecoveryActionStatus.BLOCKED
    policy_events = session.scalars(
        select(AuditLog.event_type).where(AuditLog.recovery_case_id == blocked_case.id)
    ).all()
    assert AuditEventType.POLICY_REJECTED in policy_events
    progress = client.get(f"/recovery/runs/{response.json()['run_id']}/progress")
    assert progress.status_code == 200
    assert progress.json()["status"] == "COMPLETED"
    assert progress.json()["processed_cases"] == 4
    assert progress.json()["total_cases"] == 4
    assert session.scalar(
        select(AuditLog).where(AuditLog.event_type == AuditEventType.RECOVERY_RUN_STARTED)
    ) is not None
    assert session.scalar(
        select(AuditLog).where(AuditLog.event_type == AuditEventType.RECOVERY_RUN_COMPLETED)
    ) is not None


def test_batch_failed_recovery_and_repeated_execution_are_idempotent(
    client: TestClient, session: Session, customer: Customer
) -> None:
    recovery_case = create_batch_case(session, customer, "250.00", 1)
    client.app.dependency_overrides[get_llm_provider] = override_provider

    first = client.post("/recovery/run", json={"retry_success_probability": 0})
    second = client.post("/recovery/run", json={"retry_success_probability": 0})

    assert first.status_code == 200
    assert first.json()["revenue_recovered"] == "0.00"
    assert second.status_code == 200
    assert second.json()["cases_processed"] == 0
    assert session.scalar(
        select(func.count())
        .select_from(PaymentAttempt)
        .where(PaymentAttempt.payment_id == recovery_case.payment_id)
    ) == 2


def test_batch_idempotency_key_reuses_the_original_run(
    client: TestClient, session: Session, customer: Customer
) -> None:
    create_batch_case(session, customer, "250.00", 1)
    client.app.dependency_overrides[get_llm_provider] = override_provider

    first = client.post(
        "/recovery/run", json={"retry_success_probability": 1, "idempotency_key": "demo-run-1"}
    )
    second = client.post(
        "/recovery/run", json={"retry_success_probability": 0, "idempotency_key": "demo-run-1"}
    )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert session.scalar(select(func.count()).select_from(RecoveryRun)) == 1


def test_payment_link_simulation_uses_its_configured_probability(
    client: TestClient, session: Session, customer: Customer
) -> None:
    successful_case = create_batch_case(session, customer, "150.00", 1)
    client.app.dependency_overrides[get_llm_provider] = override_provider

    successful_run = client.post("/recovery/run", json={"payment_link_success_probability": 1})

    assert successful_run.status_code == 200
    session.refresh(successful_case)
    assert successful_case.status == RecoveryCaseStatus.RECOVERED
    assert successful_case.recovered_revenue == Decimal("150.00")

    failed_case = create_batch_case(session, customer, "150.00", 2)
    failed_run = client.post("/recovery/run", json={"payment_link_success_probability": 0})

    assert failed_run.status_code == 200
    session.refresh(failed_case)
    assert failed_case.status == RecoveryCaseStatus.ACTION_REQUIRED
    assert failed_case.recovered_revenue == Decimal("0.00")


def test_run_history_and_dashboard_include_batch_results(
    client: TestClient, session: Session, customer: Customer
) -> None:
    create_batch_case(session, customer, "250.00", 1)
    client.app.dependency_overrides[get_llm_provider] = override_provider

    response = client.post("/recovery/run", json={"retry_success_probability": 1})
    history = client.get("/recovery/runs")
    metrics = client.get("/dashboard/metrics")

    assert history.status_code == 200
    assert history.json()[0]["run_id"] == response.json()["run_id"]
    assert metrics.status_code == 200
    assert metrics.json()["total_recovery_cases"] == 1
    assert metrics.json()["total_recovered_revenue"] == "250.00"
    assert metrics.json()["recovered_cases"] == 1
    assert metrics.json()["average_expected_recovery_probability"] == "0.7500"
    assert metrics.json()["expected_recovery_rate"] == "75.00"
    assert metrics.json()["expected_vs_actual_recovery"] == "25.00"
