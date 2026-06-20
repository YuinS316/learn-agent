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

    PARENT_MAX_TURNS: int = 100
    PARENT_MAX_FAILURES: int = 5
    SUBAGENT_MAX_TURNS: int = 20
    SUBAGENT_MAX_FAILURES: int = 3

    # ── Compaction ──────────────────────────────
    COMPACTION_ENABLED: bool = True
    CONTEXT_WINDOW: int = 0  # 0 = auto-detect from model

    # L1
    L1_ENABLED: bool = True
    L1_TOOL_RESULT_THRESHOLD_TOKENS: int = 10_000
    L1_PREVIEW_HEAD_LINES: int = 30
    L1_PREVIEW_TAIL_LINES: int = 20
    L1_CACHE_DIR: str = ".agents/cache/tool_results"

    # L2
    L2_ENABLED: bool = True
    L2_TRIGGER_RATIO: float = 0.75
    L2_TARGET_RATIO: float = 0.55
    L2_KEEP_RECENT_TOOL_RESULTS: int = 3

    # Transcript
    TRANSCRIPT_ENABLED: bool = True
    TRANSCRIPT_DIR: str = ".agents/transcripts"

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
