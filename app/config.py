import os
import sys
from datetime import timedelta

# When frozen by PyInstaller, instance/ lives next to the .exe (persistent).
# During normal development it lives at the repo root.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
SESSION_DIR = os.path.join(INSTANCE_DIR, "sessions")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change-me-in-production-use-long-random-string"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(INSTANCE_DIR, 'app.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Session: server-side filesystem sessions
    SESSION_TYPE = "filesystem"
    SESSION_FILE_DIR = SESSION_DIR
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Flask-WTF CSRF
    WTF_CSRF_TIME_LIMIT = None  # no per-token expiry; session lifetime is the limit

    # File upload
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max upload

    # Rate limiting (intranet app – limits are generous to allow autosave every 15s)
    RATELIMIT_DEFAULT = "10000 per day;2000 per hour"
    RATELIMIT_STORAGE_URL = "memory://"


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # requires HTTPS


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
