from abc import ABC, abstractmethod
from typing import Any, Mapping


class LLMProvider(ABC):
    provider_name = "unknown"
    model_name = "unknown"

    @abstractmethod
    def diagnose_recovery_case(self, context: dict[str, Any]) -> Mapping[str, Any]:
        """Return raw structured decision data without executing any action."""
