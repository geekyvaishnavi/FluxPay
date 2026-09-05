from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AgentDecision, AuditLog, Payment, PaymentAttempt, RecoveryAction, RecoveryCase
from app.models.enums import (
    AuditEventType,
    FailureReason,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from app.schemas.execution import ActionExecutionResult, PolicyEvaluationResult


class RetrySimulator(Protocol):
    def __call__(self, payment: Payment, recovery_case: RecoveryCase, attempt_number: int) -> bool:
        pass


class PaymentLinkSimulator(Protocol):
    def __call__(self, payment: Payment, recovery_case: RecoveryCase) -> bool:
        pass


@dataclass(frozen=True)
class SimulationConfig:
    retry_success_probability: Decimal
    payment_link_success_probability: Decimal
    seed: str


def _deterministic_outcome(
    action: RecoveryActionType,
    recovery_case: RecoveryCase,
    probability: Decimal,
    seed: str,
) -> bool:
    if probability <= 0:
        return False
    if probability >= 1:
        return True
    digest = sha256(f"{seed}:{action.value}:{recovery_case.id}".encode()).digest()
    sample = Decimal(int.from_bytes(digest[:8], "big")) / Decimal(2**64)
    return sample < probability


def default_retry_simulator(
    payment: Payment,
    recovery_case: RecoveryCase,
    attempt_number: int,
) -> bool:
    return _deterministic_outcome(
        RecoveryActionType.RETRY_PAYMENT,
        recovery_case,
        Decimal(str(settings.retry_success_probability)),
        settings.simulation_seed,
    )


def default_payment_link_simulator(payment: Payment, recovery_case: RecoveryCase) -> bool:
    return _deterministic_outcome(
        RecoveryActionType.SEND_PAYMENT_LINK,
        recovery_case,
        Decimal(str(settings.payment_link_success_probability)),
        settings.simulation_seed,
    )


class ActionExecutor:
    def __init__(
        self,
        retry_simulator: RetrySimulator = default_retry_simulator,
        payment_link_simulator: PaymentLinkSimulator = default_payment_link_simulator,
    ) -> None:
        self.retry_simulator = retry_simulator
        self.payment_link_simulator = payment_link_simulator

    def with_simulation_config(self, config: SimulationConfig) -> "ActionExecutor":
        return ActionExecutor(
            retry_simulator=lambda payment, recovery_case, attempt_number: _deterministic_outcome(
                RecoveryActionType.RETRY_PAYMENT,
                recovery_case,
                config.retry_success_probability,
                config.seed,
            ),
            payment_link_simulator=lambda payment, recovery_case: _deterministic_outcome(
                RecoveryActionType.SEND_PAYMENT_LINK,
                recovery_case,
                config.payment_link_success_probability,
                config.seed,
            ),
        )

    def execute(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
        policy_result: PolicyEvaluationResult,
    ) -> ActionExecutionResult:
        existing_action = self._existing_executed_action(session, recovery_case, decision)
        if existing_action is not None:
            return ActionExecutionResult(
                executed=True,
                idempotent=True,
                action=existing_action.action_type,
                status=recovery_case.status,
                reason="Action was already executed for this recovery case.",
                recovered_revenue=recovery_case.recovered_revenue,
                payment_attempt_id=existing_action.result.get("payment_attempt_id"),
                recovery_action_id=existing_action.id,
                executed_at=existing_action.executed_at,
                policy=policy_result,
            )

        if decision.recommended_action == RecoveryActionType.RETRY_PAYMENT:
            return self._execute_retry(session, recovery_case, decision, policy_result)
        if decision.recommended_action == RecoveryActionType.SEND_PAYMENT_LINK:
            return self._execute_send_payment_link(session, recovery_case, decision, policy_result)
        if decision.recommended_action == RecoveryActionType.ESCALATE:
            return self._execute_escalate(session, recovery_case, decision, policy_result)
        return self._execute_stop(session, recovery_case, decision, policy_result)

    def _existing_executed_action(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
    ) -> RecoveryAction | None:
        return session.scalar(
            select(RecoveryAction)
            .where(RecoveryAction.recovery_case_id == recovery_case.id)
            .where(RecoveryAction.action_type == decision.recommended_action.value)
            .where(RecoveryAction.status == RecoveryActionStatus.EXECUTED.value)
            .order_by(RecoveryAction.executed_at.desc(), RecoveryAction.created_at.desc())
            .limit(1)
        )

    def _execute_retry(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
        policy_result: PolicyEvaluationResult,
    ) -> ActionExecutionResult:
        payment = session.get_one(Payment, recovery_case.payment_id)
        now = datetime.now(UTC).replace(microsecond=0)
        latest_attempt_number = session.scalar(
            select(func.max(PaymentAttempt.attempt_number)).where(
                PaymentAttempt.payment_id == payment.id
            )
        ) or 0
        next_attempt_number = latest_attempt_number + 1
        retry_succeeded = self.retry_simulator(payment, recovery_case, next_attempt_number)
        attempt_status = PaymentStatus.SUCCEEDED if retry_succeeded else PaymentStatus.FAILED

        attempt = PaymentAttempt(
            payment_id=payment.id,
            attempt_number=next_attempt_number,
            status=attempt_status,
            failure_reason=self._failure_reason_for_retry(decision, retry_succeeded),
            processor_code="simulated_retry_success" if retry_succeeded else "simulated_retry_failed",
            message="Simulated retry succeeded." if retry_succeeded else "Simulated retry failed.",
            attempted_at=now,
        )
        session.add(attempt)
        session.flush()

        if retry_succeeded:
            payment.status = PaymentStatus.RECOVERED
            recovery_case.status = RecoveryCaseStatus.RECOVERED
            recovery_case.recovered_revenue = Decimal(payment.amount).quantize(Decimal("0.01"))
            recovery_case.closed_at = now
        else:
            payment.status = PaymentStatus.FAILED
            recovery_case.status = RecoveryCaseStatus.ACTION_REQUIRED

        result = {
            "decision_id": decision.id,
            "payment_attempt_id": attempt.id,
            "retry_succeeded": retry_succeeded,
            "recovered_revenue": str(recovery_case.recovered_revenue),
        }
        action = self._record_action(
            session,
            recovery_case,
            decision,
            policy_result,
            result,
            now,
            "Simulated payment retry executed.",
        )
        self._record_audit(
            session,
            recovery_case.id,
            AuditEventType.PAYMENT_RETRY_CREATED,
            {"payment_attempt_id": attempt.id, "attempt_number": next_attempt_number},
        )
        if not retry_succeeded:
            self._record_audit(
                session,
                recovery_case.id,
                AuditEventType.PAYMENT_RETRY_FAILED,
                {"payment_id": payment.id, "payment_attempt_id": attempt.id, "reason": "Simulated retry failed."},
            )
        if retry_succeeded:
            self._record_audit(
                session,
                recovery_case.id,
                AuditEventType.PAYMENT_RECOVERED,
                {
                    "payment_id": payment.id,
                    "recovered_revenue": str(recovery_case.recovered_revenue),
                },
            )

        return ActionExecutionResult(
            executed=True,
            action=decision.recommended_action,
            status=recovery_case.status,
            reason="Simulated retry succeeded." if retry_succeeded else "Simulated retry failed.",
            recovered_revenue=recovery_case.recovered_revenue,
            payment_attempt_id=attempt.id,
            recovery_action_id=action.id,
            executed_at=now,
            policy=policy_result,
        )

    def _execute_send_payment_link(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
        policy_result: PolicyEvaluationResult,
    ) -> ActionExecutionResult:
        payment = session.get_one(Payment, recovery_case.payment_id)
        now = datetime.now(UTC).replace(microsecond=0)
        link_succeeded = self.payment_link_simulator(payment, recovery_case)
        if link_succeeded:
            payment.status = PaymentStatus.RECOVERED
            recovery_case.status = RecoveryCaseStatus.RECOVERED
            recovery_case.recovered_revenue = Decimal(payment.amount).quantize(Decimal("0.01"))
            recovery_case.closed_at = now
        else:
            recovery_case.status = RecoveryCaseStatus.ACTION_REQUIRED
        action = self._record_action(
            session,
            recovery_case,
            decision,
            policy_result,
            {
                "decision_id": decision.id,
                "payment_link_succeeded": link_succeeded,
                "recovered_revenue": str(recovery_case.recovered_revenue),
            },
            now,
            "Simulated payment recovery link sent.",
        )
        self._record_audit(
            session,
            recovery_case.id,
            AuditEventType.PAYMENT_LINK_SENT,
            {"payment_id": payment.id, "recovered": link_succeeded},
        )
        if link_succeeded:
            self._record_audit(
                session,
                recovery_case.id,
                AuditEventType.PAYMENT_RECOVERED,
                {"payment_id": payment.id, "recovered_revenue": str(recovery_case.recovered_revenue)},
            )
        return ActionExecutionResult(
            executed=True,
            action=decision.recommended_action,
            status=recovery_case.status,
            reason=(
                "Simulated payment link recovery succeeded."
                if link_succeeded
                else "Simulated payment recovery link sent."
            ),
            recovered_revenue=recovery_case.recovered_revenue,
            recovery_action_id=action.id,
            executed_at=now,
            policy=policy_result,
        )

    def _execute_escalate(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
        policy_result: PolicyEvaluationResult,
    ) -> ActionExecutionResult:
        now = datetime.now(UTC).replace(microsecond=0)
        recovery_case.status = RecoveryCaseStatus.ESCALATED
        action = self._record_action(
            session,
            recovery_case,
            decision,
            policy_result,
            {"decision_id": decision.id, "escalated": True},
            now,
            "Recovery case escalated.",
        )
        self._record_audit(session, recovery_case.id, AuditEventType.CASE_ESCALATED, {"decision_id": decision.id})
        return ActionExecutionResult(
            executed=True,
            action=decision.recommended_action,
            status=recovery_case.status,
            reason="Recovery case escalated.",
            recovered_revenue=recovery_case.recovered_revenue,
            recovery_action_id=action.id,
            executed_at=now,
            policy=policy_result,
        )

    def _execute_stop(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
        policy_result: PolicyEvaluationResult,
    ) -> ActionExecutionResult:
        now = datetime.now(UTC).replace(microsecond=0)
        recovery_case.status = RecoveryCaseStatus.STOPPED
        recovery_case.closed_at = now
        action = self._record_action(
            session,
            recovery_case,
            decision,
            policy_result,
            {"decision_id": decision.id, "stopped": True},
            now,
            "Recovery case stopped.",
        )
        self._record_audit(session, recovery_case.id, AuditEventType.CASE_STOPPED, {"decision_id": decision.id})
        return ActionExecutionResult(
            executed=True,
            action=decision.recommended_action,
            status=recovery_case.status,
            reason="Recovery case stopped.",
            recovered_revenue=recovery_case.recovered_revenue,
            recovery_action_id=action.id,
            executed_at=now,
            policy=policy_result,
        )

    def _record_action(
        self,
        session: Session,
        recovery_case: RecoveryCase,
        decision: AgentDecision,
        policy_result: PolicyEvaluationResult,
        result: dict,
        executed_at: datetime,
        reason: str,
    ) -> RecoveryAction:
        action = RecoveryAction(
            recovery_case_id=recovery_case.id,
            action_type=decision.recommended_action,
            status=RecoveryActionStatus.EXECUTED,
            reason=reason,
            result=result,
            executed_at=executed_at,
        )
        session.add(action)
        session.flush()
        self._record_audit(
            session,
            recovery_case.id,
            AuditEventType.ACTION_EXECUTED,
            {
                "recovery_action_id": action.id,
                "recommended_action": decision.recommended_action.value,
                "policy": policy_result.model_dump(mode="json"),
                "result": result,
            },
        )
        return action

    def _record_audit(
        self,
        session: Session,
        recovery_case_id: str,
        event_type: AuditEventType,
        details: dict,
    ) -> None:
        session.add(
            AuditLog(
                recovery_case_id=recovery_case_id,
                event_type=event_type,
                actor="system",
                details=details,
            )
        )

    def _failure_reason_for_retry(
        self,
        decision: AgentDecision,
        retry_succeeded: bool,
    ) -> FailureReason | None:
        if retry_succeeded:
            return None
        failure_reason = decision.context_snapshot.get("latest_failure_reason")
        return FailureReason(failure_reason) if failure_reason else FailureReason.CARD_DECLINED


def get_action_executor() -> ActionExecutor:
    return ActionExecutor()
