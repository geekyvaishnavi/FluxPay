from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.payments import PaymentFailureRequest
from app.schemas.recovery import RecoveryCaseCreatedResponse
from app.services.revenue_detection import detect_failed_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/{payment_id}/fail", response_model=RecoveryCaseCreatedResponse, status_code=201)
def fail_payment(
    payment_id: str,
    payload: PaymentFailureRequest,
    session: Session = Depends(get_db),
):
    recovery_case = detect_failed_payment(
        session=session,
        payment_id=payment_id,
        failure_reason=payload.failure_reason,
        processor_code=payload.processor_code,
        message=payload.message,
    )
    return RecoveryCaseCreatedResponse(
        id=recovery_case.id,
        payment_id=recovery_case.payment_id,
        status=recovery_case.status,
        revenue_at_risk=recovery_case.revenue_at_risk,
        recovered_revenue=recovery_case.recovered_revenue,
        created_at=recovery_case.created_at,
    )
