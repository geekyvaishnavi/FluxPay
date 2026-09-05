from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Payment, PaymentAttempt, RecoveryAction, RecoveryCase
from app.models.enums import PaymentStatus


def _decimal_to_string(value: Decimal) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))


def build_recovery_case_context(session: Session, recovery_case_id: str) -> dict:
    row = session.execute(
        select(RecoveryCase, Payment, Customer)
        .join(Payment, RecoveryCase.payment_id == Payment.id)
        .join(Customer, Payment.customer_id == Customer.id)
        .where(RecoveryCase.id == recovery_case_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Recovery case not found")

    recovery_case, payment, customer = row
    latest_attempt = session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment.id)
        .order_by(PaymentAttempt.attempted_at.desc(), PaymentAttempt.attempt_number.desc())
        .limit(1)
    )
    previous_payment_failures = session.scalar(
        select(func.count())
        .select_from(PaymentAttempt)
        .join(Payment, PaymentAttempt.payment_id == Payment.id)
        .where(Payment.customer_id == customer.id)
        .where(PaymentAttempt.status == PaymentStatus.FAILED)
    )
    previous_successful_payments = session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.customer_id == customer.id)
        .where(Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.RECOVERED]))
    )
    previous_recovery_attempts = session.scalar(
        select(func.count())
        .select_from(RecoveryAction)
        .join(RecoveryCase, RecoveryAction.recovery_case_id == RecoveryCase.id)
        .join(Payment, RecoveryCase.payment_id == Payment.id)
        .where(Payment.customer_id == customer.id)
    )

    return {
        "recovery_case_id": recovery_case.id,
        "recovery_case_status": recovery_case.status.value,
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "company_name": customer.company_name,
            "status": customer.status.value,
        },
        "payment": {
            "id": payment.id,
            "invoice_number": payment.invoice_number,
            "amount": _decimal_to_string(payment.amount),
            "currency": payment.currency,
            "status": payment.status.value,
            "due_at": payment.due_at.isoformat(),
        },
        "latest_failure_reason": latest_attempt.failure_reason.value if latest_attempt and latest_attempt.failure_reason else None,
        "previous_payment_failures": previous_payment_failures or 0,
        "previous_successful_payments": previous_successful_payments or 0,
        "previous_recovery_attempts": previous_recovery_attempts or 0,
    }
