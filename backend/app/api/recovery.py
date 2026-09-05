from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Customer, Payment, PaymentAttempt, RecoveryCase
from app.schemas.ai_decision import AgentAnalysisResponse
from app.schemas.recovery import RecoveryCaseListItem
from app.services.agent_analysis import analyze_recovery_case
from app.services.ai.factory import get_llm_provider
from app.services.ai.provider import LLMProvider

router = APIRouter(prefix="/recovery", tags=["recovery"])


@router.get("/cases", response_model=list[RecoveryCaseListItem])
def list_recovery_cases(session: Session = Depends(get_db)):
    cases = session.execute(
        select(RecoveryCase, Payment, Customer)
        .join(Payment, RecoveryCase.payment_id == Payment.id)
        .join(Customer, Payment.customer_id == Customer.id)
        .order_by(RecoveryCase.created_at.desc(), RecoveryCase.id.desc())
    ).all()

    response: list[RecoveryCaseListItem] = []
    for recovery_case, payment, customer in cases:
        latest_attempt = session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id)
            .order_by(PaymentAttempt.attempted_at.desc(), PaymentAttempt.attempt_number.desc())
            .limit(1)
        )
        response.append(
            RecoveryCaseListItem(
                id=recovery_case.id,
                customer_name=customer.name,
                customer_email=customer.email,
                invoice_number=payment.invoice_number,
                payment_amount=payment.amount,
                currency=payment.currency,
                failure_reason=latest_attempt.failure_reason if latest_attempt else None,
                revenue_at_risk=recovery_case.revenue_at_risk,
                status=recovery_case.status,
                created_at=recovery_case.created_at,
            )
        )

    return response


@router.post("/cases/{case_id}/analyze", response_model=AgentAnalysisResponse)
def analyze_case(
    case_id: str,
    session: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
):
    return analyze_recovery_case(session=session, recovery_case_id=case_id, provider=provider)
