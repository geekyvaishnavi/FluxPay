from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentDecision, AuditLog, RecoveryAction, RecoveryCase
from app.models.enums import AuditEventType, RecoveryActionStatus
from app.schemas.execution import ActionExecutionResult, PolicyEvaluationResult
from app.services.action_executor import ActionExecutor
from app.services.policy.rules import PolicyEngine


def execute_recovery_case(
    session: Session,
    recovery_case_id: str,
    policy_engine: PolicyEngine,
    action_executor: ActionExecutor,
) -> ActionExecutionResult:
    recovery_case = session.get(RecoveryCase, recovery_case_id)
    if recovery_case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found")

    decision = session.scalar(
        select(AgentDecision)
        .where(AgentDecision.recovery_case_id == recovery_case.id)
        .order_by(AgentDecision.created_at.desc(), AgentDecision.id.desc())
        .limit(1)
    )
    if decision is None:
        raise HTTPException(status_code=409, detail="Recovery case has no AI decision to execute")

    existing_execution = session.scalar(
        select(RecoveryAction)
        .where(RecoveryAction.recovery_case_id == recovery_case.id)
        .where(RecoveryAction.action_type == decision.recommended_action.value)
        .where(RecoveryAction.status == RecoveryActionStatus.EXECUTED.value)
        .order_by(RecoveryAction.executed_at.desc(), RecoveryAction.created_at.desc())
        .limit(1)
    )
    if existing_execution is not None:
        return ActionExecutionResult(
            executed=True,
            idempotent=True,
            action=existing_execution.action_type,
            status=recovery_case.status,
            reason="Action was already executed for this recovery case.",
            recovered_revenue=recovery_case.recovered_revenue,
            payment_attempt_id=existing_execution.result.get("payment_attempt_id"),
            recovery_action_id=existing_execution.id,
            executed_at=existing_execution.executed_at,
            policy=PolicyEvaluationResult(
                allowed=True,
                action=existing_execution.action_type,
                reason="Existing execution reused idempotently.",
            ),
        )

    policy_result = policy_engine.evaluate(session, recovery_case, decision)
    session.add(
        AuditLog(
            recovery_case_id=recovery_case.id,
            event_type=AuditEventType.POLICY_EVALUATED,
            actor="system",
            details={
                "decision_id": decision.id,
                "allowed": policy_result.allowed,
                "action": policy_result.action.value,
                "reason": policy_result.reason,
            },
        )
    )

    if not policy_result.allowed:
        existing_rejection = session.scalar(
            select(RecoveryAction)
            .where(RecoveryAction.recovery_case_id == recovery_case.id)
            .where(RecoveryAction.action_type == decision.recommended_action.value)
            .where(RecoveryAction.status == RecoveryActionStatus.BLOCKED.value)
            .limit(1)
        )
        blocked_action = existing_rejection
        if blocked_action is None:
            blocked_action = RecoveryAction(
                    recovery_case_id=recovery_case.id,
                    action_type=decision.recommended_action,
                    status=RecoveryActionStatus.BLOCKED,
                    reason=policy_result.reason,
                    result={"decision_id": decision.id, "policy": policy_result.model_dump(mode="json")},
                    executed_at=None,
                )
            session.add(blocked_action)
            session.flush()
            session.add(
                AuditLog(
                    recovery_case_id=recovery_case.id,
                    event_type=AuditEventType.POLICY_REJECTED,
                    actor="system",
                    details={
                        "decision_id": decision.id,
                        "action": decision.recommended_action.value,
                        "reason": policy_result.reason,
                    },
                )
            )
        session.commit()
        return ActionExecutionResult(
            executed=False,
            idempotent=existing_rejection is not None,
            action=decision.recommended_action,
            status=recovery_case.status,
            reason=policy_result.reason,
            recovered_revenue=recovery_case.recovered_revenue,
            recovery_action_id=blocked_action.id,
            policy=policy_result,
        )

    result = action_executor.execute(session, recovery_case, decision, policy_result)
    session.commit()
    return result
