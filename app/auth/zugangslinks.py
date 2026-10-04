"""Zugangslinks: Einladung (neues Konto, sofort freigeschaltet) und Passwort neu setzen.

A link is a signed token, valid for 14 days and usable once per server (used
links are stored in the table used_zugangslinks). Signed with the shared
FILE_LOGIN_KEY when configured, so a link created at the Landkreis also works
on the Notfallserver and vice versa; otherwise with the server's SECRET_KEY.
"""
from __future__ import annotations

import os
import secrets

from flask import current_app, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

SALT = "notenapp-zugangslink-v1"
MAX_AGE = 14 * 24 * 3600
EINLADUNG = "einladung"
PASSWORT = "passwort"


def _serializer() -> URLSafeTimedSerializer:
    key = current_app.config.get("FILE_LOGIN_KEY") or current_app.config["SECRET_KEY"]
    return URLSafeTimedSerializer(key, salt=SALT)


def make_token(art: str, user=None) -> str:
    payload = {"a": art, "j": secrets.token_hex(16)}
    if art == PASSWORT:
        payload["u"] = user.username
        payload["e"] = user.email
    return _serializer().dumps(payload)


def make_link(art: str, user=None) -> str:
    """Absolute URL to send to the colleague (uses PUBLIC_BASE_URL if configured)."""
    token = make_token(art, user)
    base = (current_app.config.get("PUBLIC_BASE_URL") or os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if base:
        return base + url_for("auth.zugang", token=token)
    return url_for("auth.zugang", token=token, _external=True)


def read_token(token: str, max_age: int = MAX_AGE) -> dict | None:
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except BadSignature:   # includes SignatureExpired
        return None
    if not isinstance(payload, dict) or payload.get("a") not in (EINLADUNG, PASSWORT) or not payload.get("j"):
        return None
    if payload["a"] == PASSWORT and not (payload.get("u") and payload.get("e")):
        return None
    return payload
