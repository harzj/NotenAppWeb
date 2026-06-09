import os
import sys
from datetime import timedelta


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    val = val.strip().lower()
    if val == "":
        return default
    return val in {"1", "true", "yes", "on"}

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
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(INSTANCE_DIR, 'app.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Runtime / URL
    HOST = os.environ.get("NOTENAPP_HOST", "0.0.0.0")
    PORT = int(os.environ.get("NOTENAPP_PORT", "5000"))
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")

    # Reverse proxy support (for hosted deployments)
    TRUST_PROXY = _env_bool("TRUST_PROXY", False)
    PROXY_FIX_X_FOR = int(os.environ.get("PROXY_FIX_X_FOR", "1"))
    PROXY_FIX_X_PROTO = int(os.environ.get("PROXY_FIX_X_PROTO", "1"))
    PROXY_FIX_X_HOST = int(os.environ.get("PROXY_FIX_X_HOST", "1"))
    PROXY_FIX_X_PORT = int(os.environ.get("PROXY_FIX_X_PORT", "1"))
    PROXY_FIX_X_PREFIX = int(os.environ.get("PROXY_FIX_X_PREFIX", "0"))

    # Flask-Session: server-side filesystem sessions
    SESSION_TYPE = "filesystem"
    SESSION_FILE_DIR = SESSION_DIR
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "notenapp_session")
    SESSION_COOKIE_DOMAIN = os.environ.get("SESSION_COOKIE_DOMAIN") or None

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
