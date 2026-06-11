from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ANTHROPIC_BASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()