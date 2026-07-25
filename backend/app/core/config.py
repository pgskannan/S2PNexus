"""
Configuration management for S2PNexus.

Uses Pydantic Settings for environment-based configuration with validation.
All sensitive values must be provided via environment variables.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_HEADERS: List[str] = Field(default_factory=lambda: ["*"])

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

    # Monitoring / Observability
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = Field(default=True)
    PROMETHEUS_PORT: int = Field(default=9090, ge=1, le=65535)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

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