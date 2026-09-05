from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RecoveryRun(Base):
    __tablename__ = "recovery_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cases_processed: Mapped[int] = mapped_column(nullable=False, default=0)
    actions_executed: Mapped[int] = mapped_column(nullable=False, default=0)
    recovered_cases: Mapped[int] = mapped_column(nullable=False, default=0)
    escalated_cases: Mapped[int] = mapped_column(nullable=False, default=0)
    stopped_cases: Mapped[int] = mapped_column(nullable=False, default=0)
    revenue_at_risk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    revenue_recovered: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    recovery_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
