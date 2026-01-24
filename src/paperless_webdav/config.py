"""Application configuration via environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Core
    paperless_url: str = Field(description="Paperless-ngx base URL")
    database_url: SecretStr = Field(description="PostgreSQL connection string")
    encryption_key: SecretStr = Field(description="32-byte base64 key for token encryption")

    # Ports
    admin_port: int = Field(default=8080, description="Admin UI port")
    webdav_port: int = Field(default=8081, description="WebDAV server port")

    # Auth mode
    auth_mode: str = Field(default="paperless", pattern="^(paperless|oidc)$")

    # OIDC settings (when auth_mode=oidc)
    oidc_issuer: str | None = Field(default=None)
    oidc_client_id: str | None = Field(default=None)
    oidc_client_secret: SecretStr | None = Field(default=None)
    ldap_url: str | None = Field(default=None)
    ldap_base_dn: str | None = Field(default=None)
    ldap_bind_dn: str | None = Field(default=None)
    ldap_bind_password: SecretStr | None = Field(default=None)

    # Security
    session_expiry_hours: int = Field(default=24)
    rate_limit_attempts: int = Field(default=5)
    rate_limit_window_minutes: int = Field(default=15)
    secret_key: SecretStr = Field(description="Secret key for session signing")

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json", pattern="^(json|console)$")

    model_config = {"env_prefix": "", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
