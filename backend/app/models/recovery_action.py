from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RecoveryActionStatus, RecoveryActionType


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recovery_case_id: Mapped[str] = mapped_column(
        ForeignKey("recovery_cases.id"), nullable=False, index=True
    )
    action_type: Mapped[RecoveryActionType] = mapped_column(
        Enum(RecoveryActionType, name="recovery_action_type"), nullable=False
    )
    status: Mapped[RecoveryActionStatus] = mapped_column(
        Enum(RecoveryActionStatus, name="recovery_action_status"),
        nullable=False,
        default=RecoveryActionStatus.PROPOSED,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recovery_case = relationship("RecoveryCase", back_populates="actions")
