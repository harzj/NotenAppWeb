"""Background check whether a newer NotenApp version has been published.

The latest version is read from a small JSON file (default: latest_version.json in the
GitHub repository). The check runs in a background thread and is cached, so page
requests never wait for the network. Without network access no banner is shown.
"""
import json
import threading
import time
import urllib.request

from app.versioning import load_version_data

_lock = threading.Lock()
_state = {"checked_at": 0.0, "running": False, "info": None}


def _parse_version(text: str) -> tuple[int, ...]:
    parts = [int(p) for p in str(text).strip().lstrip("vV").split(".") if p.strip()]
    return tuple((parts + [0, 0, 0, 0])[:4])


def _current_version() -> tuple[int, ...]:
    v = load_version_data()
    return (v["major"], v["minor"], v["patch"], v["build"])


def _fetch(url: str, emergency_mode: bool) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "NotenApp-UpdateCheck"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # Notfall-Builds haben eine eigene Versionslinie (Abschnitt "notfall").
    if emergency_mode:
        data = data.get("notfall") or {}

    latest = str(data.get("version", "")).strip()
    if not latest or _parse_version(latest) <= _current_version():
        return None

    return {
        "version": latest,
        "download_url": data.get("download_url", ""),
        "hinweis": data.get("hinweis", ""),
    }


def _run_check(url: str, emergency_mode: bool) -> None:
    try:
        info = _fetch(url, emergency_mode)
    except Exception:  # noqa: BLE001 – offline, timeout, bad JSON: just no banner
        info = _state["info"]
    with _lock:
        _state["info"] = info
        _state["checked_at"] = time.time()
        _state["running"] = False


def get_update_info(app) -> dict | None:
    """Return info about a newer version, or None. Triggers a refresh when stale."""
    if not app.config.get("UPDATE_CHECK") or not app.config.get("UPDATE_CHECK_URL"):
        return None

    interval = app.config.get("UPDATE_CHECK_INTERVAL_HOURS", 6) * 3600
    with _lock:
        stale = time.time() - _state["checked_at"] > interval
        if stale and not _state["running"]:
            _state["running"] = True
            from app._build_profile import EMERGENCY_MODE

            threading.Thread(
                target=_run_check,
                args=(app.config["UPDATE_CHECK_URL"], EMERGENCY_MODE),
                daemon=True,
            ).start()
        return _state["info"]
