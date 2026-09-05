from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def find_env_file() -> Path:
    root_env = PROJECT_ROOT / ".env"
    if root_env.exists():
        return root_env
    return Path.cwd() / ".env"


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
    simulation_seed: str = "revive-demo"
    retry_success_probability: float = 0.65
    payment_link_success_probability: float = 0.55


settings = Settings()
