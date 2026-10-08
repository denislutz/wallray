from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads root .env.local (where mise loads it) then be/.env as local override
    model_config = SettingsConfigDict(
        env_file=("../.env.local", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Photo upload limits — shared with FE via NEXT_PUBLIC_ prefix
    photo_min_count: int = Field(default=1, validation_alias="NEXT_PUBLIC_PHOTO_MIN_COUNT")
    photo_max_count: int = Field(default=5, validation_alias="NEXT_PUBLIC_PHOTO_MAX_COUNT")
    photo_max_size_mb: int = Field(default=20, validation_alias="NEXT_PUBLIC_PHOTO_MAX_SIZE_MB")
    photo_resize_threshold_mb: int = Field(default=12)
    report_photo_max_size_mb: float = Field(default=2)

    debug: bool = False
    log_level: str = "info"
    database_url: str = "sqlite+aiosqlite:///./wallray.db"
    cors_origins: str = Field(validation_alias="CORS_ORIGINS")

    # LLM providers
    anthropic_api_key: str = ""
    anthropic_classification_model: str = "claude-haiku-4-5-20251001"
    anthropic_assessment_model: str = "claude-fable-5"
    customer_after_questions: int = 1
    anthropic_max_calls_per_job: int = 5

    # Free tier — AI-only report cap per user. Expert-role accounts (EXPERT_REVIEW_EMAILS) get
    # the higher internal-testing cap instead of the customer-facing one.
    free_tier_limit: int = Field(default=2, validation_alias="FREE_TIER_LIMIT")
    free_tier_limit_expert: int = Field(default=50, validation_alias="FREE_TIER_LIMIT_EXPERT")

    # Storage
    storage_provider: str = "s3"
    storage_endpoint_url: str = ""
    storage_region: str = "eu-central-1"
    storage_access_key_id: str = ""
    storage_secret_access_key: str = ""
    storage_bucket: str = "wallray"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # Payments
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Email
    resend_api_key: str = ""
    resend_from_address: str = "WallRay <reports@wallray.com>"

    # Roles — comma-separated email lists
    expert_review_emails: str = Field(default="", validation_alias="EXPERT_REVIEW_EMAILS")
    admin_emails: str = Field(default="", validation_alias="ADMIN_EMAILS")

    # Notifications
    new_user_notification_email: str = Field(
        default="", validation_alias="NEW_USER_NOTIFICATION_EMAIL"
    )

    # Anti-abuse — Cloudflare Turnstile CAPTCHA on /auth/otp/send. Empty means verification is
    # skipped (matches how resend_api_key/sentry_dsn are treated — off by default, not required).
    turnstile_secret_key: str = ""

    # Base URLs
    fe_base_url: str = Field(validation_alias="FE_BASE_URL")
    be_base_url: str = Field(validation_alias="BE_BASE_URL")
    marketing_base_url: str = Field(validation_alias="MARKETING_BASE_URL")

    # Error monitoring
    sentry_dsn: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expert_review_emails_set(self) -> frozenset[str]:
        return frozenset(
            e.strip().lower() for e in self.expert_review_emails.split(",") if e.strip()
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expert_review_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.expert_review_emails.split(",") if e.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def admin_emails_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.admin_emails.split(",") if e.strip())


settings = Settings()  # type: ignore[call-arg]
