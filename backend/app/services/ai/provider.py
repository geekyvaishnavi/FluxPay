from abc import ABC, abstractmethod
from typing import Any

from app.schemas.ai_decision import AgentDecisionOutput


class LLMProvider(ABC):
    @abstractmethod
    def diagnose_recovery_case(self, context: dict[str, Any]) -> AgentDecisionOutput:
        """Return a structured recovery decision without executing any action."""
