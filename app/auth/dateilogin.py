"""Anmelden mit Notendatei.

Every export with a password gets a signed access token ("Zugriffsschlüssel")
in the hidden Einstellungen sheet. On the Notfall-Server a teacher can log in
by uploading that file with its password: the password proves possession of
the file, the signature proves that the token was issued by our server for
this user. Landkreis server and Notfall-exe share the key FILE_LOGIN_KEY, so
files from normal operation work on the emergency server, too.

The key is never built into the exe (it could be extracted); the exe reads it
from dateilogin.key in its data folder.
"""
from __future__ import annotations

import os
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import paths

SALT = "notenapp-dateilogin-v1"
MAX_AGE = 15 * 31 * 24 * 3600   # 15 months; renewed with every export
KEY_FILE = "dateilogin.key"
MIN_KEY_LEN = 32

# Payload field → User attribute. Never contains admin rights.
FIELDS = {
    "u": "username",
    "e": "email",
    "vn": "lehrer_vorname",
    "nn": "lehrer_nachname",
    "db": "dienstbezeichnung",
    "an": "anrede",
    "ni": "notendatei_import",
}


def _read_key_file(path: str) -> str:
    """Read a key file written by any editor (UTF-8 with/without BOM, UTF-16 from PowerShell)."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    # First non-empty line, without quotes/whitespace (e.g. pasted as "abc…")
    for line in text.splitlines():
        line = line.strip().strip('"').strip("'").strip()
        if line:
            return line
    return ""


def key_file_path() -> str | None:
    """Existing key file in the data folder; also accepts 'dateilogin.key.txt'
    (Windows hides the .txt that Notepad appends)."""
    for name in (KEY_FILE, KEY_FILE + ".txt"):
        p = paths.data_file(name)
        if os.path.isfile(p):
            return p
    return None


def ensure_key_file() -> str:
    """Notfall-exe: create dateilogin.key with a random key if there is none yet.

    The value must then be set as FILE_LOGIN_KEY at the Landkreis so that files
    and links from there are accepted here (tray: "Datei-Login-Schlüssel anzeigen").
    """
    existing = key_file_path()
    if existing:
        return existing
    path = paths.data_file(KEY_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(secrets.token_urlsafe(48) + "\n")
    print(f"[INFO] Neuer Schlüssel für das Anmelden mit Notendatei angelegt: {path}")
    print("[INFO] Diesen Wert beim Landkreis als FILE_LOGIN_KEY setzen (Tray: „Datei-Login-Schlüssel anzeigen“).")
    return path


def load_key() -> str | None:
    """FILE_LOGIN_KEY from the environment, else (exe) from dateilogin.key in the data folder."""
    key = (os.environ.get("FILE_LOGIN_KEY") or "").strip()
    if not key and paths.is_frozen():
        path = ensure_key_file() if accept_enabled() else key_file_path()
        if path:
            try:
                key = _read_key_file(path)
            except (OSError, UnicodeDecodeError) as exc:
                print(f"[WARN] {path} konnte nicht gelesen werden: {exc}")
        else:
            print(f"[INFO] Anmelden mit Notendatei deaktiviert: {KEY_FILE} fehlt in {paths.data_dir()}")
    if key and key.upper().startswith("CHANGE_ME"):
        print("[WARN] FILE_LOGIN_KEY ist noch der Platzhalter aus der Beispielkonfiguration – Anmelden mit Notendatei deaktiviert.")
        return None
    if key and len(key) < MIN_KEY_LEN:
        print(f"[WARN] FILE_LOGIN_KEY ist zu kurz (mind. {MIN_KEY_LEN} Zeichen) – Anmelden mit Notendatei deaktiviert.")
        return None
    return key or None


def accept_enabled() -> bool:
    """Whether this server accepts the file login (Notfall-exe, or FILE_LOGIN_ACCEPT=true)."""
    val = (os.environ.get("FILE_LOGIN_ACCEPT") or "").strip().lower()
    if val:
        return val in {"1", "true", "yes", "on"}
    if not paths.is_frozen():
        return False
    try:
        from app._build_profile import EMERGENCY_MODE
    except ImportError:
        return False
    return bool(EMERGENCY_MODE)


def _serializer(key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(key, salt=SALT)


def make_token(user, key: str) -> str:
    payload = {short: getattr(user, attr, None) for short, attr in FIELDS.items()}
    payload["ni"] = bool(payload["ni"])
    return _serializer(key).dumps(payload)


def read_token(token: str, key: str, max_age: int = MAX_AGE) -> dict | None:
    """Return {attr: value} of a valid token, else None (bad signature or expired)."""
    if not token or not key:
        return None
    try:
        payload = _serializer(key).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or not payload.get("u") or not payload.get("e"):
        return None
    return {attr: payload.get(short) for short, attr in FIELDS.items()}
