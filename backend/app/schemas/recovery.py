from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import FailureReason, RecoveryCaseStatus


class RecoveryCaseCreatedResponse(BaseModel):
    id: str
    payment_id: str
    status: RecoveryCaseStatus
    revenue_at_risk: Decimal
    recovered_revenue: Decimal
    created_at: datetime


class RecoveryCaseListItem(BaseModel):
    id: str
    customer_name: str
    customer_email: str
    invoice_number: str
    payment_amount: Decimal
    currency: str
    failure_reason: FailureReason | None
    revenue_at_risk: Decimal
    status: RecoveryCaseStatus
    created_at: datetime
