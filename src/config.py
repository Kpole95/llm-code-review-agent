"""Loads environment variables into a shared settings object."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    chroma_db_dir: str = os.getenv("CHROMA_DB_DIR", "./chroma_db")
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")
    mlflow_tracking_username: str = os.getenv("MLFLOW_TRACKING_USERNAME", "")
    mlflow_tracking_password: str = os.getenv("MLFLOW_TRACKING_PASSWORD", "")


settings = Settings()
