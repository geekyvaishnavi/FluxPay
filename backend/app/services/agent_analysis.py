from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import AgentDecision, AuditLog, RecoveryCase
from app.models.enums import AuditEventType, DecisionStatus, RecoveryCaseStatus
from app.schemas.ai_decision import AgentAnalysisResponse, AgentDecisionOutput
from app.services.agent_context import build_recovery_case_context
from app.services.ai.errors import AIInvalidResponseError, AIProviderError
from app.services.ai.provider import LLMProvider


def analyze_recovery_case(
    session: Session,
    recovery_case_id: str,
    provider: LLMProvider,
) -> AgentAnalysisResponse:
    recovery_case = session.get(RecoveryCase, recovery_case_id)
    if recovery_case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found")

    context = build_recovery_case_context(session, recovery_case_id)
    session.add(AuditLog(recovery_case_id=recovery_case.id, event_type=AuditEventType.AI_ANALYSIS_STARTED, actor="agent", details={"previous_state": recovery_case.status.value}))
    session.commit()

    try:
        raw_response = dict(provider.diagnose_recovery_case(context))
        decision_output = AgentDecisionOutput.model_validate(raw_response)
    except AIProviderError as exc:
        _record_analysis_failure(session, recovery_case.id, str(exc))
        raise HTTPException(status_code=503, detail="AI provider unavailable") from exc
    except (ValidationError, TypeError, ValueError) as exc:
        _record_analysis_failure(session, recovery_case.id, "Invalid AI response")
        raise HTTPException(status_code=502, detail="AI provider returned invalid output") from exc

    recovery_case.status = RecoveryCaseStatus.ACTION_REQUIRED
    decision = AgentDecision(
        recovery_case_id=recovery_case.id,
        provider=provider.provider_name,
        model=provider.model_name,
        recommended_action=decision_output.recommended_action,
        diagnosis=decision_output.diagnosis,
        risk_level=decision_output.risk_level,
        delay_hours=decision_output.delay_hours,
        confidence=Decimal(str(decision_output.confidence)),
        expected_recovery_probability=Decimal(str(decision_output.expected_recovery_probability)),
        reason=decision_output.reason,
        status=DecisionStatus.VALIDATED,
        raw_response=raw_response,
        context_snapshot=context,
    )
    session.add(decision)
    session.flush()

    session.add(
        AuditLog(
            recovery_case_id=recovery_case.id,
            event_type=AuditEventType.AI_ANALYSIS_COMPLETED,
            actor="agent",
            details={
                "decision_id": decision.id,
                "recommended_action": decision_output.recommended_action.value,
                "risk_level": decision_output.risk_level.value,
                "confidence": decision_output.confidence,
                "expected_recovery_probability": decision_output.expected_recovery_probability,
            },
        )
    )
    session.add(
        AuditLog(
            recovery_case_id=recovery_case.id,
            event_type=AuditEventType.AI_DECISION_CREATED,
            actor="agent",
            details={"decision_id": decision.id, "action": decision_output.recommended_action.value, "reason": decision_output.reason},
        )
    )
    session.commit()
    session.refresh(decision)

    return AgentAnalysisResponse(
        decision_id=decision.id,
        recovery_case_id=recovery_case.id,
        status=RecoveryCaseStatus.ACTION_REQUIRED.value,
        decision=decision_output,
    )


def _record_analysis_failure(session: Session, recovery_case_id: str, reason: str) -> None:
    session.rollback()
    session.add(
        AuditLog(
            recovery_case_id=recovery_case_id,
            event_type=AuditEventType.AI_ANALYSIS_FAILED,
            actor="agent",
            details={"reason": reason},
        )
    )
    session.commit()
