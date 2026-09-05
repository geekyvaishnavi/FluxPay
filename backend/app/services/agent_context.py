from datetime import UTC
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
    customer_payments = session.scalars(
        select(Payment)
        .where(Payment.customer_id == customer.id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
    ).all()
    successful_payments = [
        customer_payment
        for customer_payment in customer_payments
        if customer_payment.status in {PaymentStatus.SUCCEEDED, PaymentStatus.RECOVERED}
    ]
    customer_lifetime_value = sum(
        (Decimal(customer_payment.amount) for customer_payment in successful_payments), Decimal()
    )
    consecutive_successful_payments = 0
    for customer_payment in customer_payments:
        if customer_payment.status not in {PaymentStatus.SUCCEEDED, PaymentStatus.RECOVERED}:
            break
        consecutive_successful_payments += 1
    customer_attempts = session.scalars(
        select(PaymentAttempt)
        .join(Payment, PaymentAttempt.payment_id == Payment.id)
        .where(Payment.customer_id == customer.id)
    ).all()
    payment_delays = []
    for attempt in customer_attempts:
        attempted_at = attempt.attempted_at.replace(tzinfo=UTC) if attempt.attempted_at.tzinfo is None else attempt.attempted_at
        due_at = attempt.payment.due_at.replace(tzinfo=UTC) if attempt.payment.due_at.tzinfo is None else attempt.payment.due_at
        if attempt.status == PaymentStatus.SUCCEEDED and attempted_at >= due_at:
            payment_delays.append((attempted_at - due_at).total_seconds() / 3600)
    customer_actions = session.scalars(
        select(RecoveryAction)
        .join(RecoveryCase, RecoveryAction.recovery_case_id == RecoveryCase.id)
        .join(Payment, RecoveryCase.payment_id == Payment.id)
        .where(Payment.customer_id == customer.id)
    ).all()
    recovery_outcomes = {
        "recovered": sum(
            action.result.get("retry_succeeded") is True
            or action.result.get("payment_link_succeeded") is True
            for action in customer_actions
        ),
        "not_recovered": sum(
            action.status.value == "EXECUTED"
            and (
                action.result.get("retry_succeeded") is False
                or action.result.get("payment_link_succeeded") is False
            )
            for action in customer_actions
        ),
    }
    current_retry_count = session.scalar(
        select(func.count())
        .select_from(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment.id)
    ) or 0
    customer_segment = _customer_segment(customer_lifetime_value, len(successful_payments))

    return {
        "recovery_case_id": recovery_case.id,
        "recovery_case_status": recovery_case.status.value,
        "customer": {
            "segment": customer_segment,
        },
        "payment": {
            "amount": _decimal_to_string(payment.amount),
            "currency": payment.currency,
        },
        "latest_failure_reason": latest_attempt.failure_reason.value if latest_attempt and latest_attempt.failure_reason else None,
        "previous_payment_failures": previous_payment_failures or 0,
        "previous_successful_payments": previous_successful_payments or 0,
        "previous_recovery_attempts": previous_recovery_attempts or 0,
        "previous_recovery_outcomes": recovery_outcomes,
        "customer_lifetime_value": _decimal_to_string(customer_lifetime_value),
        "total_successful_payments": len(successful_payments),
        "total_failed_payments": previous_payment_failures or 0,
        "average_payment_delay_hours": round(sum(payment_delays) / len(payment_delays), 2)
        if payment_delays
        else 0.0,
        "consecutive_successful_payments": consecutive_successful_payments,
        "current_retry_count": current_retry_count,
        "customer_segment": customer_segment,
    }


def _customer_segment(customer_lifetime_value: Decimal, successful_payments: int) -> str:
    if customer_lifetime_value >= Decimal("5000") or successful_payments >= 12:
        return "HIGH_VALUE"
    if customer_lifetime_value >= Decimal("1000") or successful_payments >= 4:
        return "ESTABLISHED"
    return "NEW_OR_AT_RISK"
