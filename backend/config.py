"""
config.py — central configuration, loaded from environment variables (.env).
Nothing here is hardcoded to a real secret; copy .env.example to .env and fill it in.
"""
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- App ---
    APP_NAME: str = "NextRound AI Interview Assistant"
    ENV: str = os.getenv("ENV", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5500")

    # --- Database (MySQL) ---
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "3306")
    DB_NAME: str = os.getenv("DB_NAME", "ai_interview")

    # DB_USER/DB_PASSWORD are URL-encoded here because MySQL passwords often
    # contain characters (@, :, /, ?, #, %) that are reserved in a connection
    # URL. Without this, a password like "Avijit.@933" gets misparsed — the
    # "@" is read as the userinfo/host separator, corrupting the hostname.
    _encoded_user = quote_plus(DB_USER)
    _encoded_password = quote_plus(DB_PASSWORD)

    SQLALCHEMY_DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"mysql+pymysql://{_encoded_user}:{_encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    )

    # --- JWT Auth ---
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # --- Google Gemini ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

    # --- Embeddings / FAISS ---
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    VECTOR_DB_DIR: str = os.getenv("VECTOR_DB_DIR", "vector_db")

    # --- Whisper ---
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")

    # --- Contact form (SMTP) ---
    # If SMTP_HOST is left blank, the contact endpoint logs the message
    # instead of emailing it, so the rest of the app still works without
    # real mail credentials configured.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    CONTACT_TO_EMAIL: str = os.getenv("CONTACT_TO_EMAIL", "hello@nextround.ai")

    # --- Uploads ---
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_RESUME_SIZE_MB: int = 5
    MAX_PROFILE_PICTURE_SIZE_MB: int = 2
    # Used to build an absolute URL for uploaded files (e.g. profile pictures)
    # that the frontend can put straight into an <img src>.
    BACKEND_BASE_URL: str = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")

    # --- CORS ---
    # Comma-separated list of allowed origins for the frontend, e.g.
    # "http://localhost:5500,http://127.0.0.1:5500". Must exactly match the
    # scheme+host+port the frontend is actually served from.
    CORS_ORIGINS: list = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500"
        ).split(",")
        if origin.strip()
    ]


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.VECTOR_DB_DIR, exist_ok=True)
