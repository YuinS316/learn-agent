from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ANTHROPIC_BASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = ""

    MAX_PLAN_ITEMS: int = 10

    PARENT_MAX_TURNS: int = 20
    PARENT_MAX_FAILURES: int = 5
    SUBAGENT_MAX_TURNS: int = 6
    SUBAGENT_MAX_FAILURES: int = 3

    @model_validator(mode="after")
    def _validate_required(self):
        missing = []
        for field in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL"):
            if not getattr(self, field):
                missing.append(field)
        if missing:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing)}. "
                f"Set them in .env or as environment variables."
            )
        return self


settings = Settings()
