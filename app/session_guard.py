"""Protect the server-side session against lost updates.

All open classes live in the session. Flask-Session writes the whole session
back after *every* request (SESSION_REFRESH_EACH_REQUEST). When two requests of
the same user overlap – e.g. the autosave a page sends when it is left and the
next page, or a static file – the request that finishes last overwrites what
the other one just saved: entered grades are silently lost.

Two measures:
- the session is only written when its content actually changed,
- requests of the same session are serialized (per process with a lock; on
  POSIX additionally across gunicorn workers with a file lock).
"""
from __future__ import annotations

import hashlib
import os
import pickle
import threading
import time

from flask import Flask, g

try:
    import fcntl  # POSIX only (gunicorn); the Windows exe is a single process
except ImportError:  # pragma: no cover - Windows
    fcntl = None

LOCK_TIMEOUT = 30  # seconds; afterwards the request proceeds without the lock
REFRESH_AFTER = 30 * 60  # unchanged sessions are written at most this often (keeps them alive)
_TS_KEY = "_guard_ts"

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _thread_lock(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


def _digest(session) -> bytes | None:
    try:
        return hashlib.sha1(pickle.dumps(dict(session), protocol=4)).digest()
    except Exception:
        return None  # unknown content: always save


def _acquire(app: Flask, sid: str) -> None:
    key = hashlib.sha1(sid.encode("utf-8", "replace")).hexdigest()
    if g.get("_session_lock_key") == key:
        return  # session opened twice in one request (e.g. test session_transaction)
    lock = _thread_lock(key)
    if not lock.acquire(timeout=LOCK_TIMEOUT):
        app.logger.warning("Session-Sperre nicht erhalten – Request läuft ohne Sperre weiter.")
        return
    g._session_lock = lock
    g._session_lock_key = key
    if fcntl is not None:
        try:
            # next to (not inside) the session folder, which Flask-Session prunes itself
            lock_dir = os.path.join(os.path.dirname(os.path.abspath(app.config["SESSION_FILE_DIR"])),
                                    "session_locks")
            os.makedirs(lock_dir, exist_ok=True)
            fh = open(os.path.join(lock_dir, key), "a+")
            fcntl.flock(fh, fcntl.LOCK_EX)
            g._session_lock_file = fh
        except OSError as exc:
            app.logger.warning("Session-Dateisperre fehlgeschlagen: %s", exc)


def _release(_exc=None) -> None:
    g.pop("_session_lock_key", None)
    fh = g.pop("_session_lock_file", None)
    if fh is not None:
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()
    lock = g.pop("_session_lock", None)
    if lock is not None:
        lock.release()


def install(app: Flask) -> None:
    """Wrap the session interface installed by Flask-Session."""
    iface = app.session_interface
    orig_open, orig_save = iface.open_session, iface.save_session
    cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")

    def open_session(app_, request):
        sid = request.cookies.get(cookie_name)
        if sid and not request.path.startswith("/static/"):
            _acquire(app_, sid)
        session = orig_open(app_, request)
        g._session_digest = _digest(session) if session is not None else None
        return session

    def save_session(app_, session, response):
        if session and not session.modified:
            before = g.get("_session_digest")
            if before is None or _digest(session) != before:
                session.modified = True  # changed in place (nested dict/list)
            elif time.time() - session.get(_TS_KEY, 0) > REFRESH_AFTER:
                session.modified = True  # keep an active session from expiring
        if session.modified and session:
            session[_TS_KEY] = time.time()
        orig_save(app_, session, response)

    iface.open_session = open_session
    iface.save_session = save_session
    app.teardown_request(_release)
