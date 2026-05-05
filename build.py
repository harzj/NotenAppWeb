"""
Build-Skript für NotenApp Windows-Distribution.

Erstellt eine einzelne NotenApp.exe (onefile, no console).
Die exe startet Flask lokal auf Port 5000 und öffnet den Browser automatisch.

Verwendung:
    python build.py
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
VERSION_FILE = ROOT / "version.json"
DIST_DIR = ROOT / "dist"
SPEC_FILE = ROOT / "NotenApp.spec"


def _read_version() -> dict:
    if VERSION_FILE.exists():
        with open(VERSION_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"major": 1, "minor": 0, "patch": 0, "build": 0}


def _write_version(v: dict) -> None:
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(v, f, indent=2)


def _version_str(v: dict) -> str:
    return f"{v['major']}.{v['minor']}.{v['patch']}.{v['build']}"


def main() -> None:
    # Version einlesen und Build-Nummer erhöhen
    v = _read_version()
    v["build"] += 1
    version = _version_str(v)
    _write_version(v)
    print(f"Build-Version: {version}")

    # Ausgabeverzeichnis mit Zeitstempel
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = DIST_DIR / f"NotenApp_v{version}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # PyInstaller aufrufen
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        f"--distpath={out_dir}",
        str(SPEC_FILE),
    ]
    print("Starte PyInstaller …")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("FEHLER: PyInstaller fehlgeschlagen.")
        sys.exit(1)

    exe_path = out_dir / "NotenApp.exe"
    if not exe_path.exists():
        print("FEHLER: NotenApp.exe wurde nicht gefunden.")
        sys.exit(1)

    # build_info.json ablegen
    build_info = {
        "version": version,
        "timestamp": timestamp,
        "python": sys.version,
    }
    with open(out_dir / "build_info.json", "w", encoding="utf-8") as f:
        json.dump(build_info, f, indent=2)

    # "latest"-Symlink / Kopie aktualisieren
    latest = DIST_DIR / "NotenApp_latest.exe"
    if latest.exists():
        latest.unlink()
    shutil.copy2(exe_path, latest)

    print(f"\nFertig! Ausgabe: {exe_path}")
    print(f"Neueste Version: {latest}")
    print(
        "\nHinweis: Die .exe ist eine Standalone-Datei. "
        "Beim ersten Start wird 'instance/' neben der .exe erstellt "
        "(Datenbank und Sessions)."
    )


if __name__ == "__main__":
    main()
