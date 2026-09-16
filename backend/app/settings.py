from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The application always connects as tenant_vault_app, a non-superuser role
    # created by sql/000_app_role.sql, never as the admin/owner role -- see
    # that file for why this specific distinction is load-bearing for RLS.
    database_url: str = "postgresql+asyncpg://tenant_vault_app:app_password@localhost:5435/tenant_vault"
    # Migrations run as the schema owner, since CREATE POLICY/ALTER TABLE
    # need ownership the app role deliberately does not have.
    admin_database_url: str = "postgresql+asyncpg://vault:vault@localhost:5435/tenant_vault"
    jwt_secret: str = "dev-secret-change-me-in-every-real-deployment"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 3600
    webhook_signing_secret: str = "dev-webhook-secret"
    job_poll_interval_seconds: float = 1.0


settings = Settings()
