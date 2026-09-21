from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    ENV: str = "development"
    DEV_AUTH_ENABLED: bool = True
    DEV_DEFAULT_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    DATABASE_URL: str = "sqlite:///./golftrace.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "golftrace"
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False

    LOCAL_STORAGE_PATH: str = "./.storage"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    MAX_UPLOAD_SIZE_MB: int = 500
    MAX_DURATION_SEC: int = 60
    MAX_ANALYSIS_INTERVAL_SEC: int = 15
    MAX_LONG_EDGE: int = 3840
    MAX_SHORT_EDGE: int = 2160
    MAX_FPS: int = 120
    ANALYSIS_BUDGET_FRAMES: int = 1800

    MAX_EXPORT_WIDTH: int = 1920
    MAX_EXPORT_HEIGHT: int = 1080
    MAX_EXPORT_FPS: int = 60

    JWT_SECRET: str = "change-me"
    SIGNED_URL_EXPIRY_SEC: int = 900

    MAX_PROJECTS_PER_USER: int = 100
    MAX_STORAGE_PER_USER_GB: int = 10
    MAX_CONCURRENT_JOBS_PER_USER: int = 2

    DEFAULT_MAX_GAP_MS: int = 100
    CAMERA_MODEL: str = "affine"

    VITE_API_BASE_URL: str = "http://localhost:8000/api/v1"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

def is_dev_auth_allowed() -> bool:
    if settings.ENV == "production" and settings.DEV_AUTH_ENABLED:
        raise RuntimeError("DEV_AUTH_ENABLED must be false in production")
    return settings.DEV_AUTH_ENABLED

def max_upload_bytes() -> int:
    return settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
