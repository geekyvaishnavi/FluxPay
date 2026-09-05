from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Payment, RecoveryCase


def test_demo_reset_creates_a_deterministic_isolated_dataset(
    client: TestClient, session: Session
) -> None:
    first = client.post("/recovery/demo/reset")
    first_invoices = session.scalars(
        select(Payment.invoice_number).where(Payment.invoice_number.like("DEMO-%"))
    ).all()

    second = client.post("/recovery/demo/reset")
    second_invoices = session.scalars(
        select(Payment.invoice_number).where(Payment.invoice_number.like("DEMO-%"))
    ).all()

    assert first.status_code == 200
    assert first.json() == {"customers": 6, "recovery_cases": 6}
    assert second.status_code == 200
    assert first_invoices == second_invoices
    assert session.scalar(
        select(Customer).where(Customer.email == "demo-1@revive.example")
    ) is not None
    assert session.scalar(
        select(RecoveryCase).join(Payment).where(Payment.invoice_number == "DEMO-0001")
    ) is not None
