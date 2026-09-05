from app.core.config import settings
from app.services.ai.provider import LLMProvider
from app.services.ai.stub_provider import StubLLMProvider


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "stub":
        return StubLLMProvider()
    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
