from app.core.config import Settings


def test_production_settings_include_cloud_run_frontend_origin() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        DATABASE_URL="postgresql://user:password@localhost:5432/s2pnexus",
        CORS_ORIGINS_RAW="http://localhost:3000",
    )

    assert "https://s2pnexus-frontend-120737021520.us-central1.run.app" in settings.CORS_ORIGINS
