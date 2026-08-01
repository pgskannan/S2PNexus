"""
Configuration management for S2PNexus.

Uses Pydantic Settings for environment-based configuration with validation.
All sensitive values must be provided via environment variables.
"""

import json
import logging
from functools import lru_cache
from typing import List, Optional

from pydantic import EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("s2pnexus.config")


def _parse_str_list(raw: str) -> List[str]:
    """Parse a comma-separated string or a JSON array string into a list of strings.

    Handles both "http://a.com,http://b.com" / "*" (plain) and
    '["http://a.com", "http://b.com"]' (JSON, as used in local .env files).
    """
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "S2PNexus"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "AI-powered Source-to-Pay procurement platform"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")
    DEBUG: bool = Field(default=False)
    API_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = Field(..., min_length=32, description="Secret key for JWT signing")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=30)
    SESSION_MAX_AGE: int = Field(default=86400, ge=1, le=31536000)
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=8, le=128)
    BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=15)

    # CORS
    # Stored as a raw string (validation_alias keeps reading the CORS_ORIGINS env
    # var), then exposed as a List[str] via the CORS_ORIGINS property below.
    # pydantic-settings otherwise tries to JSON-decode List[str] env vars before
    # any field_validator runs, which blows up on plain values like "*" or
    # "http://a.com,http://b.com" -- only valid JSON array strings survive that.
    CORS_ORIGINS_RAW: str = Field(default="http://localhost:3000", validation_alias="CORS_ORIGINS")
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_HEADERS: List[str] = Field(default_factory=lambda: ["*"])

    # TrustedHostMiddleware (only enforced when ENVIRONMENT != development)
    ALLOWED_HOSTS_RAW: str = Field(default="*", validation_alias="ALLOWED_HOSTS")

    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=50)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=1, le=300)
    DATABASE_POOL_RECYCLE: int = Field(default=3600, ge=300, le=86400)
    DATABASE_ECHO: bool = Field(default=False)

    # Redis (for caching, sessions, rate limiting)
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=1, le=200)
    REDIS_SOCKET_TIMEOUT: int = Field(default=5, ge=1, le=30)
    REDIS_SOCKET_CONNECT_TIMEOUT: int = Field(default=5, ge=1, le=30)

    # Ollama / LLM
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", description="Base URL for the Ollama API")
    OLLAMA_MODEL: str = Field(default="llama3.1:8b", min_length=1, description="Default Ollama model")
    OLLAMA_EMBEDDING_MODEL: str = Field(default="nomic-embed-text", min_length=1, description="Embedding model for Ollama")
    OLLAMA_TIMEOUT: int = Field(default=120, ge=10, le=600, description="Ollama request timeout in seconds")
    OLLAMA_NUM_CTX: int = Field(default=4096, ge=512, le=32768)
    OLLAMA_NUM_PREDICT: int = Field(default=512, ge=64, le=4096)
    OLLAMA_TEMPERATURE: float = Field(default=0.7, ge=0.0, le=2.0)
    ENABLE_AI: bool = Field(default=True, description="Enable the AI gateway endpoints")
    ENABLE_RAG: bool = Field(default=False, description="Enable retrieval-augmented generation features")

    # AI provider selection
    AI_PROVIDER: str = Field(default="gemini", description="Default LLM provider: gemini, ollama, openai, azure-openai, anthropic")

    # Gemini / Vertex AI (Google Cloud)
    GOOGLE_CLOUD_PROJECT: Optional[str] = Field(default=None, description="GCP project ID; when set, Gemini calls route through Vertex AI")
    GOOGLE_CLOUD_LOCATION: str = Field(default="global", description="Vertex AI location ('global' or a specific region)")
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = Field(default=None, description="Path to a GCP service account JSON key; falls back to Application Default Credentials if unset")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Gemini Developer API key; used only when GOOGLE_CLOUD_PROJECT is unset (local/dev fallback)")
    GEMINI_MODEL: str = Field(default="gemini-3.1-flash-lite", min_length=1, description="Gemini model name")
    GEMINI_TIMEOUT: int = Field(default=60, ge=10, le=300, description="Gemini request timeout in seconds")

    # ChromaDB / Vector DB
    CHROMA_HOST: str = Field(default="localhost")
    CHROMA_PORT: int = Field(default=8000)
    CHROMA_COLLECTION_NAME: str = Field(default="s2pnexus_documents")
    CHROMA_PERSIST_DIRECTORY: str = Field(default="./data/chroma")

    # LangChain
    LANGCHAIN_TRACING_V2: bool = Field(default=False)
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = Field(default="s2pnexus")

    # File Storage
    UPLOAD_DIR: str = Field(default="./data/uploads")
    MAX_FILE_SIZE: int = Field(default=52428800, ge=1048576, le=524288000)  # 50MB default, max 500MB
    ALLOWED_EXTENSIONS: List[str] = Field(
        default_factory=lambda: [".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"]
    )
    EMBEDDING_DIMENSIONS: int = Field(default=768, ge=1, le=4096)

    # Logging
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    LOG_FORMAT: str = Field(default="json", pattern="^(json|text)$")
    LOG_FILE: Optional[str] = Field(default="./logs/s2pnexus.log")
    LOG_MAX_BYTES: int = Field(default=10485760, ge=1048576)  # 10MB
    LOG_BACKUP_COUNT: int = Field(default=5, ge=1, le=20)

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_REQUESTS: int = Field(default=100, ge=1, le=10000)
    RATE_LIMIT_WINDOW: int = Field(default=60, ge=1, le=3600)  # seconds

    # Email (for notifications, password reset)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True
    EMAIL_FROM: str = Field(default="noreply@s2pnexus.com")
    EMAIL_FROM_NAME: str = Field(default="S2PNexus")

    # --- Email provider (Email Redirect spec, Section 2) -------------------
    # Selects the concrete SMTP transport: "gmail", "smtp" (generic), or
    # "sendgrid"/"ses" (reserved for future API-based providers).
    EMAIL_PROVIDER: str = Field(
        default="gmail",
        pattern="^(gmail|smtp|sendgrid|ses)$",
        description="SMTP provider: gmail, smtp (generic), sendgrid, ses",
    )
    EMAIL_USERNAME: Optional[str] = Field(
        default=None, description="SMTP username (Gmail address for the gmail provider)"
    )
    EMAIL_PASSWORD: Optional[str] = Field(
        default=None,
        description="SMTP password. For Gmail use an App Password, never the account password.",
    )

    # --- Email redirect (DEV / QA / Sandbox only) --------------------------
    # When enabled, every REDIRECTABLE system email is sent to EMAIL_REDIRECT_TO
    # instead of the real recipient. Never affects welcome / initial-password /
    # password-reset emails, and is force-disabled in production.
    EMAIL_REDIRECT_ENABLED: bool = Field(
        default=False,
        description="Redirect all redirectable outbound email to EMAIL_REDIRECT_TO (non-production only).",
    )
    EMAIL_REDIRECT_TO: Optional[EmailStr] = Field(
        default=None,
        description="Catch-all inbox that receives redirected email in DEV/QA/Sandbox environments.",
    )

    @model_validator(mode="after")
    def _guard_production_redirect(self) -> "Settings":
        """Fail fast at startup: redirecting mail in production is never allowed.

        This is a hard safety interlock (spec Section 2/3) rather than a soft
        warning so a misconfigured production deployment cannot silently leak or
        drop real user email.
        """
        if self.ENVIRONMENT == "production" and self.EMAIL_REDIRECT_ENABLED:
            raise ValueError(
                "EMAIL_REDIRECT_ENABLED must be false when ENVIRONMENT=production; "
                "email redirect is for DEV/QA/Sandbox only."
            )
        return self

    @property
    def email_redirect_active(self) -> bool:
        """True when the redirect pipeline should be applied to outbound email.

        Combines the flag, the environment interlock, and presence of a target.
        Non-redirectable types (welcome, initial password, password reset) are
        additionally excluded inside the email service, not here.
        """
        return self.EMAIL_REDIRECT_ENABLED and not self.is_production and bool(self.EMAIL_REDIRECT_TO)

    @property
    def smtp_host_resolved(self) -> str:
        """Resolved SMTP host, applying the provider default when unset."""
        if self.SMTP_HOST:
            return self.SMTP_HOST
        return {"gmail": "smtp.gmail.com"}.get(self.EMAIL_PROVIDER, "smtp.gmail.com")

    @property
    def smtp_port_resolved(self) -> int:
        """Resolved SMTP port, applying the provider default when unset."""
        if self.SMTP_PORT:
            return self.SMTP_PORT
        return 587  # STARTTLS default; Gmail-compatible

    # Monitoring / Observability
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = Field(default=True)
    PROMETHEUS_PORT: int = Field(default=9090, ge=1, le=65535)

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        """Validate that the Ollama base URL is a usable URL."""
        if not value or not value.strip():
            raise ValueError("OLLAMA_BASE_URL must not be empty")
        return value.rstrip("/")

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, v: str | List[str]) -> List[str]:
        """Parse allowed extensions from string or list."""
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """CORS origins, parsed from CORS_ORIGINS_RAW with safe defaults for local and deployed frontend origins."""
        parsed = _parse_str_list(self.CORS_ORIGINS_RAW)
        if "*" in parsed:
            return ["*"]

        default_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://s2pnexus-frontend-120737021520.us-central1.run.app",
        ]
        for origin in default_origins:
            if origin not in parsed:
                parsed.append(origin)
        return parsed

    @property
    def ALLOWED_HOSTS(self) -> List[str]:
        """Allowed hosts, parsed from ALLOWED_HOSTS_RAW (comma-separated or JSON array)."""
        return _parse_str_list(self.ALLOWED_HOSTS_RAW)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == "production"

    @property
    def database_url_async(self) -> str:
        """Get async database URL for asyncpg."""
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()