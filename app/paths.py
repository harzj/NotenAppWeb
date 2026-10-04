"""Where the app keeps its files.

Running from source (development, Landkreis server): everything stays in the
repository (instance/ next to app/), exactly as before.

Running as PyInstaller exe (tray / Notfall-Build): data lives in a fixed
per-machine folder so that a new build in a new dist/ folder still finds the
users, keys and sessions. Default %LOCALAPPDATA%\\NotenApp, override with the
environment variable NOTENAPP_DATA_DIR.
"""
from __future__ import annotations

import os
import sys

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> str:
    return os.path.dirname(sys.executable)


def data_dir() -> str:
    """Base folder for instance/ and the key files."""
    if not is_frozen():
        return REPO_DIR
    custom = os.environ.get("NOTENAPP_DATA_DIR")
    if custom:
        return os.path.abspath(custom)
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "NotenApp")


def instance_dir() -> str:
    return os.path.join(data_dir(), "instance")


def data_file(name: str) -> str:
    """Path of a file directly in the data folder (e.g. secret_key, dateilogin.key)."""
    return os.path.join(data_dir(), name)
