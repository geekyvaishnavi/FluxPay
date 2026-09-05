from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models import (
    AgentDecision,
    AuditLog,
    Customer,
    Payment,
    PaymentAttempt,
    RecoveryAction,
    RecoveryCase,
)
from app.models.enums import (
    AuditEventType,
    CustomerStatus,
    DecisionStatus,
    FailureReason,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)

CUSTOMER_NAMES = [
    ("Avery Stone", "Northstar Analytics"),
    ("Maya Chen", "BrightCart"),
    ("Jordan Brooks", "LedgerLoop"),
    ("Priya Raman", "CloudWorks"),
    ("Ethan Miller", "FieldPilot"),
    ("Sofia Garcia", "Medley HR"),
    ("Noah Patel", "AtlasOps"),
    ("Olivia Brown", "SignalDesk"),
    ("Liam Wilson", "RouteSpring"),
    ("Emma Davis", "MetricNest"),
]

FAILURE_PROFILES = [
    (FailureReason.INSUFFICIENT_FUNDS, "card_declined_insufficient_funds", RecoveryActionType.RETRY_PAYMENT),
    (FailureReason.EXPIRED_CARD, "expired_card", RecoveryActionType.SEND_PAYMENT_LINK),
    (FailureReason.CARD_DECLINED, "generic_decline", RecoveryActionType.RETRY_PAYMENT),
    (FailureReason.PROCESSOR_ERROR, "processor_timeout", RecoveryActionType.RETRY_PAYMENT),
    (FailureReason.AUTHENTICATION_REQUIRED, "authentication_required", RecoveryActionType.SEND_PAYMENT_LINK),
]


def reset_database() -> None:
    with SessionLocal() as session:
        for model in [AuditLog, AgentDecision, RecoveryAction, RecoveryCase, PaymentAttempt, Payment, Customer]:
            session.execute(delete(model))
        session.commit()


def seed_database() -> None:
    now = datetime.now(UTC).replace(microsecond=0)

    with SessionLocal() as session:
        customers: list[Customer] = []
        for index, (name, company) in enumerate(CUSTOMER_NAMES, start=1):
            customer = Customer(
                name=name,
                email=f"billing{index}@{company.lower().replace(' ', '')}.example",
                company_name=company,
                status=CustomerStatus.PAST_DUE if index % 3 == 0 else CustomerStatus.ACTIVE,
            )
            session.add(customer)
            customers.append(customer)

        session.flush()

        for index in range(80):
            customer = customers[index % len(customers)]
            failure_reason, processor_code, recommended_action = FAILURE_PROFILES[index % len(FAILURE_PROFILES)]
            amount = Decimal("79.00") + Decimal((index % 8) * 45)
            opened_at = now - timedelta(days=index % 21, hours=index % 7)
            attempts_count = 1 + (index % 3)
            status = RecoveryCaseStatus.DETECTED
            recovered_revenue = Decimal("0.00")
            payment_status = PaymentStatus.FAILED

            if index % 10 == 0:
                status = RecoveryCaseStatus.RECOVERED
                recovered_revenue = amount
                payment_status = PaymentStatus.RECOVERED
            elif attempts_count >= 3:
                status = RecoveryCaseStatus.ANALYZING

            payment = Payment(
                customer_id=customer.id,
                amount=amount,
                currency="USD",
                invoice_number=f"INV-2026-{index + 1:04d}",
                status=payment_status,
                due_at=opened_at - timedelta(days=1),
            )
            session.add(payment)
            session.flush()

            for attempt_number in range(1, attempts_count + 1):
                session.add(
                    PaymentAttempt(
                        payment_id=payment.id,
                        attempt_number=attempt_number,
                        status=PaymentStatus.FAILED,
                        failure_reason=failure_reason,
                        processor_code=processor_code,
                        message=f"Attempt {attempt_number} failed due to {failure_reason.value.lower()}.",
                        attempted_at=opened_at + timedelta(hours=(attempt_number - 1) * 24),
                    )
                )

            recovery_case = RecoveryCase(
                payment_id=payment.id,
                status=status,
                revenue_at_risk=amount,
                recovered_revenue=recovered_revenue,
                priority="HIGH" if amount >= Decimal("300.00") else "MEDIUM",
                opened_at=opened_at,
                closed_at=opened_at + timedelta(days=2) if status == RecoveryCaseStatus.RECOVERED else None,
            )
            session.add(recovery_case)
            session.flush()

            session.add(
                AgentDecision(
                    recovery_case_id=recovery_case.id,
                    provider="stub",
                    model="stub-recovery-v1",
                    recommended_action=recommended_action,
                    diagnosis=f"Seed diagnosis for {failure_reason.value.lower()} on invoice {payment.invoice_number}.",
                    confidence="MEDIUM",
                    status=DecisionStatus.VALIDATED,
                    raw_response={
                        "diagnosis": failure_reason.value,
                        "recommended_action": recommended_action.value,
                        "confidence": "MEDIUM",
                    },
                )
            )
            session.add(
                RecoveryAction(
                    recovery_case_id=recovery_case.id,
                    action_type=recommended_action,
                    status=RecoveryActionStatus.EXECUTED if index % 4 == 0 else RecoveryActionStatus.APPROVED,
                    reason="Seeded action for demo data.",
                    executed_at=opened_at + timedelta(hours=2) if index % 4 == 0 else None,
                )
            )
            session.add(
                AuditLog(
                    recovery_case_id=recovery_case.id,
                    event_type=AuditEventType.CASE_CREATED,
                    actor="seed",
                    details={
                        "invoice_number": payment.invoice_number,
                        "revenue_at_risk": str(amount),
                        "failure_reason": failure_reason.value,
                    },
                )
            )

        session.commit()


if __name__ == "__main__":
    reset_database()
    seed_database()
    print("Seeded Revive database with 10 customers and 80 recovery cases.")
