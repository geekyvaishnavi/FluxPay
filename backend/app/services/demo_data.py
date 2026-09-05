from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Customer, Payment, PaymentAttempt, RecoveryAction, RecoveryCase
from app.models.enums import AuditEventType, CustomerStatus, FailureReason, PaymentStatus, RecoveryCaseStatus


DEMO_START = datetime(2026, 1, 15, 12, tzinfo=UTC)
SCENARIOS = [
    ("Strong history", FailureReason.INSUFFICIENT_FUNDS, Decimal("420.00"), 8),
    ("Card refresh", FailureReason.EXPIRED_CARD, Decimal("180.00"), 4),
    ("Network retry", FailureReason.PROCESSOR_ERROR, Decimal("650.00"), 6),
    ("Repeated failures", FailureReason.CARD_DECLINED, Decimal("310.00"), 0),
    ("High value", FailureReason.INSUFFICIENT_FUNDS, Decimal("1450.00"), 14),
    ("Authentication", FailureReason.AUTHENTICATION_REQUIRED, Decimal("95.00"), 2),
]


def reset_demo_dataset(session: Session) -> dict[str, int]:
    demo_payment_ids = session.scalars(
        select(Payment.id).where(Payment.invoice_number.like("DEMO-%"))
    ).all()
    if demo_payment_ids:
        demo_case_ids = session.scalars(
            select(RecoveryCase.id).where(RecoveryCase.payment_id.in_(demo_payment_ids))
        ).all()
        if demo_case_ids:
            session.execute(delete(AuditLog).where(AuditLog.recovery_case_id.in_(demo_case_ids)))
            session.execute(delete(RecoveryAction).where(RecoveryAction.recovery_case_id.in_(demo_case_ids)))
            from app.models import AgentDecision

            session.execute(delete(AgentDecision).where(AgentDecision.recovery_case_id.in_(demo_case_ids)))
            session.execute(delete(RecoveryCase).where(RecoveryCase.id.in_(demo_case_ids)))
        session.execute(delete(PaymentAttempt).where(PaymentAttempt.payment_id.in_(demo_payment_ids)))
        session.execute(delete(Payment).where(Payment.id.in_(demo_payment_ids)))
    session.execute(delete(Customer).where(Customer.email.like("demo-%@revive.example")))

    case_count = 0
    for scenario_index, (scenario, failure_reason, amount, history_count) in enumerate(SCENARIOS, start=1):
        customer_id = str(uuid5(NAMESPACE_URL, f"revive-demo-customer-{scenario_index}"))
        customer = Customer(
            id=customer_id,
            name=f"Demo {scenario}",
            email=f"demo-{scenario_index}@revive.example",
            company_name=f"{scenario} Co.",
            status=CustomerStatus.ACTIVE,
        )
        session.add(customer)
        for history_index in range(history_count):
            session.add(
                Payment(
                    id=str(uuid5(NAMESPACE_URL, f"revive-demo-history-{scenario_index}-{history_index}")),
                    customer_id=customer_id,
                    amount=amount,
                    currency="USD",
                    invoice_number=f"DEMO-H-{scenario_index}-{history_index:02}",
                    status=PaymentStatus.SUCCEEDED,
                    due_at=DEMO_START - timedelta(days=30 + history_index),
                )
            )
        attempts = 3 if failure_reason == FailureReason.CARD_DECLINED else 1
        payment_id = str(uuid5(NAMESPACE_URL, f"revive-demo-payment-{scenario_index}"))
        payment = Payment(
            id=payment_id,
            customer_id=customer_id,
            amount=amount,
            currency="USD",
            invoice_number=f"DEMO-{scenario_index:04}",
            status=PaymentStatus.FAILED,
            due_at=DEMO_START - timedelta(days=2),
        )
        session.add(payment)
        for attempt_number in range(1, attempts + 1):
            session.add(
                PaymentAttempt(
                    id=str(uuid5(NAMESPACE_URL, f"revive-demo-attempt-{scenario_index}-{attempt_number}")),
                    payment_id=payment_id,
                    attempt_number=attempt_number,
                    status=PaymentStatus.FAILED,
                    failure_reason=failure_reason,
                    processor_code="demo_simulated_failure",
                    message=f"Demo {scenario.lower()} failure.",
                    attempted_at=DEMO_START - timedelta(hours=48 - attempt_number),
                )
            )
        recovery_case = RecoveryCase(
            id=str(uuid5(NAMESPACE_URL, f"revive-demo-case-{scenario_index}")),
            payment_id=payment_id,
            status=RecoveryCaseStatus.DETECTED,
            revenue_at_risk=amount,
            recovered_revenue=Decimal("0.00"),
            priority="HIGH" if amount >= Decimal("1000") else "MEDIUM",
            opened_at=DEMO_START - timedelta(days=1),
        )
        session.add(recovery_case)
        session.add(
            AuditLog(
                recovery_case_id=recovery_case.id,
                event_type=AuditEventType.CASE_CREATED,
                actor="demo",
                details={"scenario": scenario, "failure_reason": failure_reason.value},
            )
        )
        case_count += 1
    session.commit()
    return {"customers": len(SCENARIOS), "recovery_cases": case_count}
