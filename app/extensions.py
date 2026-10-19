from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask import request
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
login_manager = LoginManager()
sess = Session()
csrf = CSRFProtect()

_LOOPBACK = {"127.0.0.1", "::1"}


def _client_address() -> str:
    """Rate-limit key. Requests through a tunnel on the same machine (ngrok on the
    Notfallserver) all come from 127.0.0.1 – use the forwarded client address
    instead, otherwise all teachers share one limit. Only trusted from loopback,
    so LAN clients cannot spoof it."""
    addr = get_remote_address()
    if addr in _LOOPBACK:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return addr


limiter = Limiter(key_func=_client_address)

login_manager.login_view = "auth.login"
login_manager.login_message = "Bitte melde dich an, um auf diese Seite zuzugreifen."
login_manager.login_message_category = "warning"
