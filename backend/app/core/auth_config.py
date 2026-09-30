from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    auth_jwt_secret: SecretStr
    auth_access_token_minutes: int = Field(default=30, ge=1, le=1440)
    auth_jwt_issuer: str = "multi-agent-job-assistant"
    auth_jwt_audience: str = "job-assistant-api"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("auth_jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError(
                "AUTH_JWT_SECRET must contain at least 32 bytes."
            )
        return value


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()