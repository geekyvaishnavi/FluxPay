from typing import Any, Mapping

from app.models.enums import RecoveryActionType
from app.services.ai.provider import LLMProvider


class StubLLMProvider(LLMProvider):
    provider_name = "stub"
    model_name = "stub-recovery-v2"

    def diagnose_recovery_case(self, context: dict[str, Any]) -> Mapping[str, Any]:
        failure_reason = context.get("latest_failure_reason")
        previous_failures = int(context.get("previous_payment_failures", 0))
        previous_successes = int(context.get("previous_successful_payments", 0))

        if failure_reason == "EXPIRED_CARD":
            action = RecoveryActionType.SEND_PAYMENT_LINK.value
            diagnosis = "expired_payment_method"
            risk_level = "MEDIUM"
            delay_hours = 0
            reason = "The saved payment method is expired, so the customer needs an updated payment link."
        elif previous_failures >= 3:
            action = RecoveryActionType.ESCALATE.value
            diagnosis = "repeated_payment_failures"
            risk_level = "HIGH"
            delay_hours = 0
            reason = "The customer has repeated payment failures and should be reviewed before more automation."
        elif previous_successes >= 2:
            action = RecoveryActionType.RETRY_PAYMENT.value
            diagnosis = "temporary_payment_failure"
            risk_level = "LOW"
            delay_hours = 24
            reason = "The customer has a strong prior payment history and this looks recoverable."
        else:
            action = RecoveryActionType.RETRY_PAYMENT.value
            diagnosis = "temporary_payment_failure"
            risk_level = "MEDIUM"
            delay_hours = 24
            reason = "The failure may be recoverable with a delayed retry recommendation."

        return {
            "diagnosis": diagnosis,
            "risk_level": risk_level,
            "recommended_action": action,
            "delay_hours": delay_hours,
            "confidence": 0.82,
            "reason": reason,
        }
