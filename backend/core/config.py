"""Configuration management for Zoria."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=False)
else:
    load_dotenv(override=False)


class Settings:
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "zoria")
    DB_USER: str = os.getenv("DB_USER", "zoria")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
    DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "20"))
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_HOURS: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_HOURS", "24"))
    
    # Server
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # File Upload
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "./uploads"))
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    
    # Vector Store
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
    VECTOR_SEARCH_TOP_K: int = int(os.getenv("VECTOR_SEARCH_TOP_K", "5"))
    VECTOR_SIMILARITY_THRESHOLD: float = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.7"))
    
    # Ollama (optional)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    USE_OLLAMA_EMBEDDINGS: bool = os.getenv("USE_OLLAMA_EMBEDDINGS", "false").lower() == "true"

    # Question generation: model for generating quiz questions (e.g. "gpt-5-nano" or "llama3.1")
    QUESTION_GENERATION_MODEL: str = os.getenv("QUESTION_GENERATION_MODEL", "gpt-5-nano")
    
    @classmethod
    def ensure_upload_dir(cls) -> None:
        """Ensure upload directory exists."""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate(cls) -> None:
        """Validate required settings."""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required")
        if len(cls.JWT_SECRET_KEY) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")


# Global settings instance
settings = Settings()
