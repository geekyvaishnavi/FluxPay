from typing import Any

from app.models.enums import RecoveryActionType
from app.schemas.ai_decision import AgentDecisionOutput
from app.services.ai.provider import LLMProvider


class StubLLMProvider(LLMProvider):
    def diagnose_recovery_case(self, context: dict[str, Any]) -> AgentDecisionOutput:
        failure_reason = context.get("failure_reason")
        if failure_reason == "EXPIRED_CARD":
            action = RecoveryActionType.SEND_PAYMENT_LINK
            diagnosis = "The saved payment method appears expired."
        elif context.get("failed_attempts", 0) >= 3:
            action = RecoveryActionType.ESCALATE
            diagnosis = "Repeated failures require human review."
        else:
            action = RecoveryActionType.RETRY_PAYMENT
            diagnosis = "The failure may be recoverable with a scheduled retry."

        return AgentDecisionOutput(
            diagnosis=diagnosis,
            recommended_action=action,
            confidence="MEDIUM",
            reasoning="Stub provider selected a deterministic recommendation for local development.",
        )
