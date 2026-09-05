from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Payment, PaymentAttempt, RecoveryCase
from app.models.enums import AuditEventType, FailureReason, PaymentStatus, RecoveryCaseStatus


def calculate_revenue_at_risk(payment: Payment) -> Decimal:
    return Decimal(payment.amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_priority(amount: Decimal) -> str:
    if amount >= Decimal("500.00"):
        return "CRITICAL"
    if amount >= Decimal("300.00"):
        return "HIGH"
    return "MEDIUM"


def detect_failed_payment(
    session: Session,
    payment_id: str,
    failure_reason: FailureReason,
    processor_code: str | None = None,
    message: str | None = None,
) -> RecoveryCase:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    existing_case = session.scalar(
        select(RecoveryCase).where(RecoveryCase.payment_id == payment_id)
    )
    if existing_case is not None:
        raise HTTPException(status_code=409, detail="Recovery case already exists for this payment")

    now = datetime.now(UTC).replace(microsecond=0)
    latest_attempt_number = session.scalar(
        select(func.max(PaymentAttempt.attempt_number)).where(PaymentAttempt.payment_id == payment_id)
    )
    next_attempt_number = (latest_attempt_number or 0) + 1
    revenue_at_risk = calculate_revenue_at_risk(payment)

    payment.status = PaymentStatus.FAILED

    attempt = PaymentAttempt(
        payment_id=payment.id,
        attempt_number=next_attempt_number,
        status=PaymentStatus.FAILED,
        failure_reason=failure_reason,
        processor_code=processor_code,
        message=message or f"Payment failed due to {failure_reason.value}.",
        attempted_at=now,
    )
    session.add(attempt)
    session.flush()

    recovery_case = RecoveryCase(
        payment_id=payment.id,
        status=RecoveryCaseStatus.DETECTED,
        revenue_at_risk=revenue_at_risk,
        recovered_revenue=Decimal("0.00"),
        priority=calculate_priority(revenue_at_risk),
        opened_at=now,
    )
    session.add(recovery_case)
    session.flush()

    session.add(
        AuditLog(
            recovery_case_id=recovery_case.id,
            event_type=AuditEventType.PAYMENT_FAILED,
            actor="system",
            details={
                "payment_id": payment.id,
                "invoice_number": payment.invoice_number,
                "failure_reason": failure_reason.value,
                "revenue_at_risk": str(revenue_at_risk),
                "payment_attempt_id": attempt.id,
            },
        )
    )
    session.add(
        AuditLog(
            recovery_case_id=recovery_case.id,
            event_type=AuditEventType.CASE_CREATED,
            actor="system",
            details={"payment_id": payment.id, "previous_state": None, "new_state": RecoveryCaseStatus.DETECTED.value},
        )
    )
    session.commit()
    session.refresh(recovery_case)
    return recovery_case
