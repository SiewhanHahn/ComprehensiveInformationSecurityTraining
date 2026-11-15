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
    session_absolute_ttl_seconds: int = 28800
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    # 只有前面挂了可信反向代理（Nginx 覆写 X-Real-IP）时才信任该头；直连 API 时它可被客户端伪造
    trust_proxy_headers: bool = False

    csrf_cookie_name: str = "ww_csrf"
    max_login_attempts: int = 5
    lockout_seconds: int = 300
    ip_login_attempts: int = 20
    ip_lockout_seconds: int = 60

    cors_origins: str = ""

    # 定时扫描（compose 的 scheduler 服务）
    notification_scan_interval_seconds: int = 300
    notification_backfill_hours: int = 24

    # 响应任务处置时限；用分钟而不是小时，答辩时可以设成 2 分钟现场演示超时升级
    response_task_due_minutes: int = 1440

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

    def validate_for_serving(self) -> None:
        """只在真正对外提供 HTTP 服务的进程里调用（``main.py``）。

        这两条只与「怎么把响应发出去」有关。放在 ``Settings()`` 构造期会连带把
        alembic、seed 与 scheduler 一起拦下——生产环境漏配一个变量时，整个栈连迁移都跑不了，
        只能看到一串 traceback，而不是一条可操作的启动错误。
        """
        if self.app_env != "development" and not self.cookie_secure:
            # 非开发环境按 HTTPS 部署：Cookie 不带 Secure 时，明文链路可被直接重放
            raise ValueError("非 development 环境必须设置 COOKIE_SECURE=true")
        if "*" in self.cors_origin_list:
            # 通配来源 + allow_credentials 会让任意站点带着会话跨域读接口
            raise ValueError("CORS_ORIGINS 不允许使用 '*'，请逐个列出前端来源")


@lru_cache
def get_settings() -> Settings:
    return Settings()
