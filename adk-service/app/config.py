"""Configuration for the standalone ADK P2P pipeline service.

Deliberately separate from the main backend's `app.core.config.Settings` --
this service has its own process, its own requirements.txt, and its own
deploy (see ../README.md and Dockerfile). It never touches Postgres or the
main backend's credentials; it only receives pre-fetched grounding data over
HTTP and a request to run the ADK Workflow over it.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini / Vertex AI -- same model + project as the main backend
    # (see backend/app/core/config.py GEMINI_MODEL/GOOGLE_CLOUD_PROJECT) so
    # both agent implementations are judged against the same model version.
    GOOGLE_CLOUD_PROJECT: str | None = Field(default=None, description="GCP project ID; when set, ADK routes through Vertex AI")
    GOOGLE_CLOUD_LOCATION: str = Field(default="global", description="Vertex AI location")
    GEMINI_MODEL: str = Field(default="gemini-3.5-flash", description="Gemini model name used by every pipeline step")
    GEMINI_API_KEY: str | None = Field(default=None, description="Gemini Developer API key; local/dev fallback when GOOGLE_CLOUD_PROJECT is unset")

    # Service-to-service auth: the main backend sends this as a Bearer token.
    # If unset, the service accepts unauthenticated requests -- fine for local
    # dev, not for the deployed Cloud Run URL (set it before deploying).
    INTERNAL_TOKEN: str | None = Field(default=None, description="Shared-secret bearer token required from callers")


settings = Settings()
