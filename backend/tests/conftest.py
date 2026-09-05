from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Customer, Payment, RecoveryCase
from app.models.enums import CustomerStatus, PaymentStatus, RecoveryCaseStatus


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    with TestingSessionLocal() as db:
        yield db


@pytest.fixture()
def client(session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def customer(session: Session) -> Customer:
    customer = Customer(
        name="Maya Chen",
        email="maya@example.com",
        company_name="BrightCart",
        status=CustomerStatus.ACTIVE,
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


@pytest.fixture()
def payment(session: Session, customer: Customer) -> Payment:
    payment = Payment(
        customer_id=customer.id,
        amount=Decimal("250.00"),
        currency="USD",
        invoice_number="INV-TEST-001",
        status=PaymentStatus.SUCCEEDED,
        due_at=datetime.now(UTC),
    )
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


def create_case(
    session: Session,
    payment: Payment,
    status: RecoveryCaseStatus,
    revenue_at_risk: Decimal,
    recovered_revenue: Decimal = Decimal("0.00"),
) -> RecoveryCase:
    recovery_case = RecoveryCase(
        payment_id=payment.id,
        status=status,
        revenue_at_risk=revenue_at_risk,
        recovered_revenue=recovered_revenue,
        priority="MEDIUM",
        opened_at=datetime.now(UTC),
    )
    session.add(recovery_case)
    session.commit()
    session.refresh(recovery_case)
    return recovery_case
