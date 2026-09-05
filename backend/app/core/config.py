from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def find_env_file() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://revive:revive@localhost:5432/revive"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    llm_provider: str = "stub"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
