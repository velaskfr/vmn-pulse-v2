from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://netmonitor:changeme@db:5432/netmonitor"
    secret_key: str = "please-change-this-secret"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12 horas

    admin_user: str = "admin"
    admin_password: str = "admin123"

    discord_webhook_url: str = ""

    ping_interval_seconds: int = 60
    ping_count: int = 4
    ping_concurrency: int = 20
    latency_warn_ms: int = 100
    loss_warn_pct: int = 20
    offline_confirm_cycles: int = 2
    retention_detail_days: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
