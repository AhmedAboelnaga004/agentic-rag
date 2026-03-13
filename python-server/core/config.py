import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_host: str
    app_port: int
    cors_allow_origins: list[str]
    database_url: str
    database_url_direct: str
    google_api_key: str
    pinecone_api_key: str
    pinecone_index: str
    jwt_secret: str
    jwt_algorithm: str
    jwt_access_token_exp_minutes: int



def _split_csv(value: str | None, default: str = "*") -> list[str]:
    raw = value or default
    return [part.strip() for part in raw.split(",") if part.strip()]



def get_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")

    return Settings(
        app_name=os.environ.get("APP_NAME", "Agentic Personal Assistant"),
        app_host=os.environ.get("APP_HOST", "0.0.0.0"),
        app_port=int(os.environ.get("APP_PORT", "8000")),
        cors_allow_origins=_split_csv(os.environ.get("CORS_ALLOW_ORIGINS"), default="*"),
        database_url=database_url,
        database_url_direct=os.environ.get("DATABASE_URL_DIRECT", database_url),
        google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        pinecone_api_key=os.environ.get("PINECONE_API_KEY", ""),
        pinecone_index=os.environ.get("PINECONE_INDEX", ""),
        jwt_secret=os.environ.get("JWT_SECRET", "change-me-in-production"),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        jwt_access_token_exp_minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXP_MINUTES", "60")),
    )


settings = get_settings()
