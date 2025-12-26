"""
PipeVision Configuration
Loads settings from environment variables
"""

from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "PipeVision"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://pipevision:pipevision@localhost:5432/pipevision"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Storage (S3-compatible)
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    STORAGE_LOCAL_PATH: str = "./storage"
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_ENDPOINT_URL: str = ""  # For MinIO compatibility
    
    # File upload limits
    MAX_UPLOAD_SIZE_MB: int = 500
    ALLOWED_EXTENSIONS: List[str] = ["dwg", "dxf"]
    
    # Processing
    ODA_CONVERTER_PATH: str = "/usr/bin/ODAFileConverter"
    THUMBNAIL_SIZE: tuple = (800, 600)
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://app.pipevision.io",
    ]
    
    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # API Keys (for B2B integrations)
    API_KEY_PREFIX: str = "pv_"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# Ensure storage directory exists for local storage
if settings.STORAGE_BACKEND == "local":
    os.makedirs(settings.STORAGE_LOCAL_PATH, exist_ok=True)
    os.makedirs(os.path.join(settings.STORAGE_LOCAL_PATH, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(settings.STORAGE_LOCAL_PATH, "thumbnails"), exist_ok=True)
    os.makedirs(os.path.join(settings.STORAGE_LOCAL_PATH, "exports"), exist_ok=True)
