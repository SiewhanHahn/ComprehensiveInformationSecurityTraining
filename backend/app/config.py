from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret_key: str = "dev-insecure-secret"
    database_url: str = "mysql+pymysql://weather_app:weather_app_pw@127.0.0.1:3306/weather_warning?charset=utf8mb4"
    redis_url: str = "redis://127.0.0.1:6379/0"

    session_cookie_name: str = "ww_session"
    session_ttl_seconds: int = 3600
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    csrf_cookie_name: str = "ww_csrf"
    max_login_attempts: int = 5
    lockout_seconds: int = 300

    cors_origins: str = ""

    open_meteo_base_url: str = "https://previous-runs-api.open-meteo.com/v1/forecast"
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _reject_default_secret(self) -> "Settings":
        if self.app_env != "development" and self.app_secret_key in ("dev-insecure-secret", ""):
            raise ValueError("APP_SECRET_KEY 必须设置为非默认值（非 development 环境）")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
