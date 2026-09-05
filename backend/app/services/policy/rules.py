from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AgentDecision, PaymentAttempt, RecoveryCase
from app.models.enums import RecoveryActionType, RiskLevel
from app.schemas.execution import PolicyEvaluationResult


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
    allow_high_risk_automated_actions: bool = False


DEFAULT_RECOVERY_POLICY = RecoveryPolicy()

AUTOMATED_ACTIONS = {
    RecoveryActionType.RETRY_PAYMENT,
    RecoveryActionType.SEND_PAYMENT_LINK,
}


class PolicyEngine:
    def __init__(self, policy: RecoveryPolicy = DEFAULT_RECOVERY_POLICY) -> None:
        self.policy = policy

    def evaluate(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
    ) -> PolicyEvaluationResult:
        action = decision.recommended_action
        if action not in ALLOWED_RECOVERY_ACTIONS:
            return PolicyEvaluationResult(
                allowed=False,
                action=action,
                reason=f"Action {action.value} is not allowed by policy.",
            )

        if (
            decision.risk_level == RiskLevel.HIGH
            and action in AUTOMATED_ACTIONS
            and not self.policy.allow_high_risk_automated_actions
        ):
            return PolicyEvaluationResult(
                allowed=False,
                action=action,
                reason="HIGH-risk cases require manual approval before automated action.",
            )

        if action == RecoveryActionType.RETRY_PAYMENT:
            return self._evaluate_retry(session, recovery_case, action)

        return PolicyEvaluationResult(
            allowed=True,
            action=action,
            reason=f"{action.value} is allowed by policy.",
        )

    def _evaluate_retry(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        action: RecoveryActionType,
    ) -> PolicyEvaluationResult:
        failed_attempts = session.scalar(
            select(func.count())
            .select_from(PaymentAttempt)
            .where(PaymentAttempt.payment_id == recovery_case.payment_id)
        ) or 0
        if failed_attempts >= self.policy.escalation_failure_threshold:
            return PolicyEvaluationResult(
                allowed=False,
                action=action,
                reason="Escalation required after repeated failed attempts.",
            )
        if failed_attempts >= self.policy.max_retries:
            return PolicyEvaluationResult(
                allowed=False,
                action=action,
                reason="Maximum retry limit reached.",
            )

        latest_attempt = session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == recovery_case.payment_id)
            .order_by(PaymentAttempt.attempted_at.desc(), PaymentAttempt.attempt_number.desc())
            .limit(1)
        )
        if latest_attempt is not None:
            now = datetime.now(UTC)
            attempted_at = latest_attempt.attempted_at
            if attempted_at.tzinfo is None:
                attempted_at = attempted_at.replace(tzinfo=UTC)
            elapsed_hours = (now - attempted_at).total_seconds() / 3600
            if elapsed_hours < self.policy.minimum_retry_interval_hours:
                return PolicyEvaluationResult(
                    allowed=False,
                    action=action,
                    reason="Minimum retry interval has not elapsed.",
                )

        return PolicyEvaluationResult(
            allowed=True,
            action=action,
            reason="Retry limit has not been reached.",
        )


def get_policy_engine() -> PolicyEngine:
    return PolicyEngine()
