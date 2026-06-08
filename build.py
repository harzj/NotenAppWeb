"""
Build-Skript für NotenApp Windows-Distribution.

Erstellt eine einzelne NotenApp.exe und fragt vor dem Build,
welcher Teil der Versionsnummer erhöht werden soll.

Verwendung:
    python build.py
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.versioning import bump_version, format_version, load_version_data

ROOT = Path(__file__).parent
VERSION_FILE = ROOT / "version.json"
DIST_DIR = ROOT / "dist"
SPEC_FILE = ROOT / "NotenApp.spec"

RELEASE_TYPES = {
    "1": "major-update",
    "2": "minor-update",
    "3": "build",
}


def _read_version() -> dict:
    return load_version_data()


def _write_version(v: dict) -> None:
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(v, f, indent=2)
        f.write("\n")


def _version_str(v: dict) -> str:
    return format_version(v)


def _prompt_release_type(current_version: str) -> str:
    print(f"Aktuelle Version: {current_version}")
    print("Welche Art von neuer Version soll erstellt werden?")
    print("  [1] major-update  -> neue Features, z.B. 1.1 -> 1.2")
    print("  [2] minor-update  -> Bugfix, z.B. 1.1 -> 1.1.1")
    print("  [3] build         -> nur Build-Nummer erhöhen")

    while True:
        selection = input("Auswahl [1/2/3]: ").strip()
        release_type = RELEASE_TYPES.get(selection)
        if release_type:
            return release_type
        print("Ungültige Eingabe. Bitte 1, 2 oder 3 eingeben.")


def main() -> None:
    current_version_data = _read_version()
    current_version = _version_str(current_version_data)
    release_type = _prompt_release_type(current_version)
    next_version_data = bump_version(current_version_data, release_type)
    version = _version_str(next_version_data)
    print(f"Neue Version: {version}")

    # Ausgabeverzeichnis nach Versionsnummer
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = DIST_DIR / f"NotenApp_v{version}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # PyInstaller aufrufen
    _write_version(next_version_data)
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
        _write_version(current_version_data)
        print("FEHLER: PyInstaller fehlgeschlagen.")
        sys.exit(1)

    exe_path = out_dir / "NotenApp.exe"
    if not exe_path.exists():
        print("FEHLER: NotenApp.exe wurde nicht gefunden.")
        sys.exit(1)

    # build_info.json ablegen
    build_info = {
        "version": version,
        "release_type": release_type,
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
