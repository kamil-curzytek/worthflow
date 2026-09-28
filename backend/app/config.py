from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'private' / 'finance.db').as_posix()}"
    default_display_currency: str = "EUR"

    exchange_rate_provider: str = "frankfurter"

    ai_analysis_enabled: bool = False
    ai_provider: str = "local"
    ai_allow_external_data: bool = False
    ai_model: str = "claude-sonnet-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    @property
    def database_path(self) -> Path | None:
        """Filesystem path for the sqlite file, if the URL is a sqlite URL."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return Path(self.database_url[len(prefix) :])
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
