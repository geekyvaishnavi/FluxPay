from dataclasses import dataclass

from app.models.enums import RecoveryActionType


ALLOWED_RECOVERY_ACTIONS = {
    RecoveryActionType.RETRY_PAYMENT,
    RecoveryActionType.SEND_PAYMENT_LINK,
    RecoveryActionType.ESCALATE,
    RecoveryActionType.STOP,
}


@dataclass(frozen=True)
class RecoveryPolicy:
    max_retries: int = 3
    minimum_retry_interval_hours: int = 24
    escalation_failure_threshold: int = 3


DEFAULT_RECOVERY_POLICY = RecoveryPolicy()
