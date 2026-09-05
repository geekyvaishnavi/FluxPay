from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DecisionStatus, RecoveryActionType, RiskLevel


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recovery_case_id: Mapped[str] = mapped_column(
        ForeignKey("recovery_cases.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    recommended_action: Mapped[RecoveryActionType] = mapped_column(
        Enum(RecoveryActionType, name="recovery_action_type"), nullable=False
    )
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), nullable=False)
    delay_hours: Mapped[int] = mapped_column(nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    expected_recovery_probability: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.0000")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DecisionStatus] = mapped_column(
        Enum(DecisionStatus, name="decision_status"), nullable=False, default=DecisionStatus.PROPOSED
    )
    raw_response: Mapped[dict] = mapped_column(JSON, nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recovery_case = relationship("RecoveryCase", back_populates="decisions")
