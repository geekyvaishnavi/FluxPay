from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RecoveryCaseStatus


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), nullable=False, unique=True)
    status: Mapped[RecoveryCaseStatus] = mapped_column(
        Enum(RecoveryCaseStatus, name="recovery_case_status"),
        nullable=False,
        default=RecoveryCaseStatus.DETECTED,
    )
    revenue_at_risk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    recovered_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payment = relationship("Payment", back_populates="recovery_case")
    actions = relationship("RecoveryAction", back_populates="recovery_case", cascade="all, delete-orphan")
    decisions = relationship("AgentDecision", back_populates="recovery_case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="recovery_case", cascade="all, delete-orphan")
