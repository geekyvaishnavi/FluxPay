from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Customer, Payment, PaymentAttempt, RecoveryCase
from app.models.enums import (
    AuditEventType,
    CustomerStatus,
    FailureReason,
    PaymentStatus,
    RecoveryCaseStatus,
)
from tests.conftest import create_case


def test_payment_failure_creates_recovery_case(
    client: TestClient, session: Session, payment: Payment
) -> None:
    response = client.post(
        f"/payments/{payment.id}/fail",
        json={"failure_reason": FailureReason.INSUFFICIENT_FUNDS.value},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["payment_id"] == payment.id
    assert body["status"] == RecoveryCaseStatus.DETECTED.value

    session.refresh(payment)
    assert payment.status == PaymentStatus.FAILED

    recovery_case = session.scalar(select(RecoveryCase).where(RecoveryCase.payment_id == payment.id))
    assert recovery_case is not None
    assert recovery_case.revenue_at_risk == Decimal("250.00")

    attempt = session.scalar(select(PaymentAttempt).where(PaymentAttempt.payment_id == payment.id))
    assert attempt is not None
    assert attempt.failure_reason == FailureReason.INSUFFICIENT_FUNDS

    audit_log = session.scalar(select(AuditLog).where(AuditLog.recovery_case_id == recovery_case.id))
    assert audit_log is not None
    assert audit_log.event_type == AuditEventType.PAYMENT_FAILED


def test_duplicate_recovery_case_is_prevented(
    client: TestClient, session: Session, payment: Payment
) -> None:
    create_case(session, payment, RecoveryCaseStatus.DETECTED, Decimal("250.00"))

    response = client.post(
        f"/payments/{payment.id}/fail",
        json={"failure_reason": FailureReason.EXPIRED_CARD.value},
    )

    assert response.status_code == 409
    case_count = session.scalar(
        select(func.count()).select_from(RecoveryCase).where(RecoveryCase.payment_id == payment.id)
    )
    assert case_count == 1


def test_revenue_at_risk_comes_from_payment_amount(
    client: TestClient, session: Session, customer: Customer
) -> None:
    payment = Payment(
        customer_id=customer.id,
        amount=Decimal("987.65"),
        currency="USD",
        invoice_number="INV-TEST-002",
        status=PaymentStatus.SUCCEEDED,
        due_at=datetime.now(UTC),
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)

    response = client.post(
        f"/payments/{payment.id}/fail",
        json={"failure_reason": FailureReason.CARD_DECLINED.value},
    )

    assert response.status_code == 201
    assert response.json()["revenue_at_risk"] == "987.65"


def test_recovery_cases_list_returns_failure_context(
    client: TestClient, payment: Payment
) -> None:
    client.post(
        f"/payments/{payment.id}/fail",
        json={"failure_reason": FailureReason.AUTHENTICATION_REQUIRED.value},
    )

    response = client.get("/recovery/cases")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["customer_name"] == "Maya Chen"
    assert body[0]["payment_amount"] == "250.00"
    assert body[0]["failure_reason"] == FailureReason.AUTHENTICATION_REQUIRED.value
    assert body[0]["revenue_at_risk"] == "250.00"


def test_dashboard_metrics_are_calculated_by_backend(
    client: TestClient, session: Session
) -> None:
    customer = Customer(
        name="Avery Stone",
        email="avery@example.com",
        company_name="Northstar Analytics",
        status=CustomerStatus.ACTIVE,
    )
    session.add(customer)
    session.commit()

    payments: list[Payment] = []
    for index, amount in enumerate([Decimal("100.00"), Decimal("300.00"), Decimal("200.00")], start=1):
        payment = Payment(
            customer_id=customer.id,
            amount=amount,
            currency="USD",
            invoice_number=f"INV-METRIC-{index}",
            status=PaymentStatus.FAILED,
            due_at=datetime.now(UTC),
        )
        session.add(payment)
        payments.append(payment)
    session.commit()

    create_case(session, payments[0], RecoveryCaseStatus.DETECTED, Decimal("100.00"))
    create_case(
        session,
        payments[1],
        RecoveryCaseStatus.RECOVERED,
        Decimal("300.00"),
        Decimal("300.00"),
    )
    create_case(session, payments[2], RecoveryCaseStatus.STOPPED, Decimal("200.00"))

    response = client.get("/dashboard/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "total_revenue_at_risk": "600.00",
        "total_recovered_revenue": "300.00",
        "active_recovery_cases": 1,
        "recovered_cases": 1,
        "recovery_rate": "50.00",
    }
