"""Where the app keeps its files.

Running from source (development, Landkreis server): everything stays in the
repository (instance/ next to app/), exactly as before.

Running as PyInstaller exe (tray / Notfall-Build): data lives in a fixed
per-machine folder so that a new build in a new dist/ folder still finds the
users, keys and sessions. Default %LOCALAPPDATA%\\NotenApp, override with the
environment variable NOTENAPP_DATA_DIR.

Running from source as Notfallserver (Windows-Dienst mit Auto-Update, see
deploy/): NOTENAPP_NOTFALL=1 switches on the same behaviour as the Notfall-exe;
NOTENAPP_DATA_DIR then points to the data folder.
"""
from __future__ import annotations

import os
import sys

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _env_true(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def is_notfall_server() -> bool:
    """Notfall-Server: Notfall-exe, or running from source with NOTENAPP_NOTFALL=1."""
    if _env_true("NOTENAPP_NOTFALL"):
        return True
    if not is_frozen():
        return False
    try:
        from app._build_profile import EMERGENCY_MODE
    except ImportError:
        return False
    return bool(EMERGENCY_MODE)


def uses_data_dir() -> bool:
    """Whether data, keys and the secret live in the data folder (exe or Notfallserver)."""
    return is_frozen() or _env_true("NOTENAPP_NOTFALL")


def exe_dir() -> str:
    return os.path.dirname(sys.executable)


def data_dir() -> str:
    """Base folder for instance/ and the key files."""
    custom = os.environ.get("NOTENAPP_DATA_DIR")
    if custom and uses_data_dir():
        return os.path.abspath(custom)
    if not is_frozen():
        return REPO_DIR
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "NotenApp")


def instance_dir() -> str:
    return os.path.join(data_dir(), "instance")


def data_file(name: str) -> str:
    """Path of a file directly in the data folder (e.g. secret_key, dateilogin.key)."""
    return os.path.join(data_dir(), name)
