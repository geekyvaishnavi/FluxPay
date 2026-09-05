from pydantic import BaseModel

from app.models.enums import FailureReason


class PaymentFailureRequest(BaseModel):
    failure_reason: FailureReason
    processor_code: str | None = None
    message: str | None = None
