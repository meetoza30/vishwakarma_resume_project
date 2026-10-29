import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Vishwakarma Faculty Resume Screening Platform"
    VERSION: str = "3.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment & Debug
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # Security & Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "vishwakarma_production_super_secret_jwt_key_2026_change_in_env!")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./vishwakarma_platform.db")

    # File Storage & Limits
    MAX_FILE_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB max per resume
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".docx", ".doc"]
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "uploads")
    STATIC_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

    # Multi-Provider AI / LLM Configuration
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OMNIROUTE_API_KEY: str = os.getenv("OMNIROUTE_API_KEY", "")
    NVIDIA_NIM_API_KEY: str = os.getenv("NVIDIA_NIM_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    DEEPINFRA_API_KEY: str = os.getenv("DEEPINFRA_API_KEY", "")
    NEBIUS_API_KEY: str = os.getenv("NEBIUS_API_KEY", "")
    
    PRIMARY_LLM_MODEL: str = "google/gemma-3-12b-it"
    FALLBACK_LLM_MODELS: List[str] = ["qwen/qwen3-32b", "meta-llama/llama-3.3-70b-instruct"]
    LLM_TIMEOUT_SECONDS: int = 90
    LLM_MAX_RETRIES: int = 3

    # OCR Settings
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "tesseract")
    OCR_DENSITY_THRESHOLD_CHARS: int = 50  # If < 50 chars per page, trigger PyTesseract OCR

    # Asynchronous Workers & Rate Limiting
    MAX_CONCURRENT_JOBS: int = 10
    MAX_CONCURRENT_RESUME_WORKERS: int = 5
    RATE_LIMIT_PER_MINUTE: int = 60

    # CORS Configuration
    CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

# Ensure required storage directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.STATIC_DIR, exist_ok=True)
