"""Настройки приложения. Все значения можно переопределить через переменные окружения / файл .env."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-please-32-bytes-min")

    # PostgreSQL: postgresql+psycopg://пользователь:пароль@хост:порт/база
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://politech:politech@localhost:5432/politech"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_ACCESS_HOURS", "12")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "30")))

    # CORS: адрес фронтенда (Vite по умолчанию на 5173)
    CORS_ORIGINS = _list(os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"))

    # Загрузка файлов
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024

    JSON_AS_ASCII = False
    JSON_SORT_KEYS = False


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "postgresql+psycopg://politech:politech@localhost:5432/politech_test"
    )
