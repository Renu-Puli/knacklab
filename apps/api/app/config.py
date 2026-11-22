from pydantic import Field, field_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "apps/api/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = Field(..., alias="DATABASE_URL")
    mongodb_uri: str = Field(default="")
    redis_url: str = Field(default="")
    jwt_secret: str = Field(default="")
    api_key_a: str = Field(
        default="",
        validation_alias=AliasChoices("API_KEY_PRIMARY", "API_KEY_A", "api_key_a")
    )
    api_key_b: str = Field(
        default="",
        validation_alias=AliasChoices("API_KEY_SECONDARY", "API_KEY_B", "api_key_b")
    )
    retention_days: int = Field(default=30)
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError(f"Invalid PORT {value}: must be between 1 and 65535.")
        return value

try:
    settings = Settings()
except Exception as e:
    raise RuntimeError(f"Startup Configuration Error: Invalid or missing environment configuration.\n{e}")
