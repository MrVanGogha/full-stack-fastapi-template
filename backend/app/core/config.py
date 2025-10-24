import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    
    # WeChat Website App Config (set via environment variables)
    WECHAT_APP_ID: str | None = None
    WECHAT_APP_SECRET: str | None = None
    # The backend callback URL registered in WeChat Open Platform, e.g. https://your-domain.com/api/v1/auth/wechat/callback
    WECHAT_REDIRECT_URI: HttpUrl | None = None
    # Scope for website QR login
    WECHAT_SCOPE: str = "snsapi_login"
    # OTP (One-Time Password) configuration
    OTP_CODE_LENGTH: int = 6
    OTP_CODE_TTL_SECONDS: int = 300
    OTP_RATE_LIMIT_SECONDS: int = 60
    OTP_LOCAL_ECHO: bool = True

    # SMS provider configuration (extensible)
    SMS_PROVIDER: Literal["console", "aliyun", "tencent"] = "console"
    # Aliyun SMS
    ALIYUN_ACCESS_KEY_ID: str | None = None
    ALIYUN_ACCESS_KEY_SECRET: str | None = None
    ALIYUN_SIGN_NAME: str | None = None
    ALIYUN_TEMPLATE_CODE_LOGIN: str | None = None
    # Optional settings for Aliyun
    ALIYUN_REGION_ID: str = "cn-hangzhou"
    ALIYUN_TEMPLATE_PARAM_CODE_KEY: str = "code"
    # Tencent Cloud SMS
    TENCENT_SECRET_ID: str | None = None
    TENCENT_SECRET_KEY: str | None = None
    TENCENT_SDK_APP_ID: str | None = None
    TENCENT_SIGN_NAME: str | None = None
    TENCENT_TEMPLATE_ID_LOGIN: str | None = None
    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: EmailStr | None = None

    # Redis configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> str:
        scheme = "rediss" if self.REDIS_SSL else "redis"
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
