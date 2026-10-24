"""
Build-Skript für NotenApp Windows-Distribution.

Erstellt mit derselben Versionsnummer zwei NotenApp.exe: einen lokalen Build und einen
Notfall-Build (Tray + ngrok). Vor dem Build wird gefragt, welcher Teil der Versionsnummer
erhöht werden soll. Die lokale exe wird in den Checkout von main kopiert; dort werden
der Download-Link in README.md und latest_version.json (Update-Hinweis) angepasst.

Verwendung:
    python build.py
"""

import json
import re
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
BUILD_VERSION_MODULE = ROOT / "app" / "_build_version.py"
BUILD_PROFILE_MODULE = ROOT / "app" / "_build_profile.py"
NGROK_EXE_SOURCE = ROOT / "ngrok.exe"
DOWNLOAD_BASE_URL = "https://github.com/harzj/NotenAppWeb/raw/main/dist"

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


def _write_build_version_module(v: dict) -> None:
    lines = [
        "VERSION = {",
        f'    "major": {int(v["major"])},',
        f'    "minor": {int(v["minor"])},',
        f'    "patch": {int(v["patch"])},',
        f'    "build": {int(v["build"])}',
        "}\n",
    ]
    with open(BUILD_VERSION_MODULE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_build_profile_module(emergency_mode: bool) -> None:
    with open(BUILD_PROFILE_MODULE, "w", encoding="utf-8") as f:
        f.write(f"EMERGENCY_MODE = {emergency_mode}\n")


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


def _find_main_worktree() -> Path:
    """Checkout von main, in dem die lokale exe, README und latest_version.json liegen."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(ROOT), capture_output=True, text=True, check=True,
    )
    path = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line == "branch refs/heads/main" and path is not None:
            return path
    raise RuntimeError("Kein Checkout von main gefunden (git worktree list).")


def _build_exe(version: str, emergency_mode: bool, build_info: dict) -> Path:
    # Der Ordnername macht die vorgesehene Betriebsart der .exe sichtbar.
    build_kind = "Notfall" if emergency_mode else "Lokal"
    out_dir = DIST_DIR / f"NotenApp_{build_kind}_v{version}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_build_profile_module(emergency_mode)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        f"--distpath={out_dir}",
        str(SPEC_FILE),
    ]
    print(f"Starte PyInstaller ({build_kind}) …")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        raise RuntimeError(f"PyInstaller fehlgeschlagen ({build_kind}).")

    exe_path = out_dir / "NotenApp.exe"
    if not exe_path.exists():
        raise RuntimeError(f"NotenApp.exe wurde nicht gefunden ({build_kind}).")

    # Notfall-Build: ngrok.exe mit ausliefern, da tray.py sie neben der .exe erwartet
    if emergency_mode and NGROK_EXE_SOURCE.exists():
        shutil.copy2(NGROK_EXE_SOURCE, out_dir / "ngrok.exe")

    with open(out_dir / "build_info.json", "w", encoding="utf-8") as f:
        json.dump({**build_info, "emergency_mode": emergency_mode}, f, indent=2)
    return out_dir


def _publish_local_build(local_dir: Path, version: str) -> Path:
    """Lokale exe nach main kopieren und README-Link sowie latest_version.json anpassen."""
    main_dir = _find_main_worktree()
    target = main_dir / "dist" / local_dir.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(local_dir, target)

    download_url = f"{DOWNLOAD_BASE_URL}/{local_dir.name}/NotenApp.exe"

    readme = main_dir / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = re.sub(r"Version [\d.]+, lokal", f"Version {version}, lokal", text)
    text = re.sub(r"NotenApp_Lokal_v[\d.]+/NotenApp\.exe", f"{local_dir.name}/NotenApp.exe", text)
    readme.write_text(text, encoding="utf-8")

    latest_file = main_dir / "latest_version.json"
    try:
        latest = json.loads(latest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        latest = {"hinweis": ""}
    latest.update({"version": version, "download_url": download_url})
    latest_file.write_text(json.dumps(latest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return main_dir


def main() -> None:
    current_version_data = _read_version()
    current_version = _version_str(current_version_data)
    release_type = _prompt_release_type(current_version)
    next_version_data = bump_version(current_version_data, release_type)
    version = _version_str(next_version_data)
    print(f"Neue Version: {version} (es werden Lokal- und Notfall-Build erzeugt)")

    build_info = {
        "version": version,
        "release_type": release_type,
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "python": sys.version,
    }

    _write_version(next_version_data)
    _write_build_version_module(next_version_data)
    try:
        local_dir = _build_exe(version, False, build_info)
        emergency_dir = _build_exe(version, True, build_info)
    except RuntimeError as exc:
        _write_version(current_version_data)
        _write_build_version_module(current_version_data)
        print(f"FEHLER: {exc}")
        sys.exit(1)
    finally:
        # Repo-Default zurücksetzen: die .exe hat das Flag bereits eingebettet, Quelltext bleibt sicher/aus
        _write_build_profile_module(False)

    # "latest"-Kopie zeigt auf den Notfall-Build, den der Admin selbst betreibt
    latest = DIST_DIR / "NotenApp_latest.exe"
    if latest.exists():
        latest.unlink()
    shutil.copy2(emergency_dir / "NotenApp.exe", latest)

    main_dir = _publish_local_build(local_dir, version)

    print(f"\nFertig! Lokal:   {local_dir / 'NotenApp.exe'}")
    print(f"         Notfall: {emergency_dir / 'NotenApp.exe'}")
    print(f"Neueste Notfall-Version: {latest}")
    print(
        f"\nLokale exe nach {main_dir / 'dist' / local_dir.name} kopiert, "
        "README.md und latest_version.json angepasst.\n"
        "Bitte in main committen und pushen, damit Link und Update-Hinweis wirken."
    )
    print(
        "\nHinweis: Die .exe ist eine Standalone-Datei. "
        "Beim ersten Start wird 'instance/' neben der .exe erstellt "
        "(Datenbank und Sessions)."
    )


if __name__ == "__main__":
    main()
