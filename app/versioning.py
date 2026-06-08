import json
import sys
from pathlib import Path


DEFAULT_VERSION = {
    "major": 1,
    "minor": 0,
    "patch": 0,
    "build": 0,
}


def _candidate_paths() -> list[Path]:
    here = Path(__file__).resolve()
    paths = [here.parents[1] / "version.json"]

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            paths.insert(0, Path(meipass) / "version.json")
        paths.append(Path(sys.executable).resolve().parent / "version.json")

    return paths


def load_version_data() -> dict:
    for path in _candidate_paths():
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            return {
                "major": int(data.get("major", DEFAULT_VERSION["major"])),
                "minor": int(data.get("minor", DEFAULT_VERSION["minor"])),
                "patch": int(data.get("patch", DEFAULT_VERSION["patch"])),
                "build": int(data.get("build", DEFAULT_VERSION["build"])),
            }

    return DEFAULT_VERSION.copy()


def format_version(version: dict | None = None) -> str:
    current = version or load_version_data()
    parts = [str(current["major"]), str(current["minor"])]

    if current["patch"] > 0 or current["build"] > 0:
        parts.append(str(current["patch"]))

    if current["build"] > 0:
        parts.append(str(current["build"]))

    return ".".join(parts)


def bump_version(version: dict, release_type: str) -> dict:
    updated = {
        "major": int(version.get("major", DEFAULT_VERSION["major"])),
        "minor": int(version.get("minor", DEFAULT_VERSION["minor"])),
        "patch": int(version.get("patch", DEFAULT_VERSION["patch"])),
        "build": int(version.get("build", DEFAULT_VERSION["build"])),
    }

    if release_type == "major-update":
        updated["minor"] += 1
        updated["patch"] = 0
        updated["build"] = 0
        return updated

    if release_type == "minor-update":
        updated["patch"] += 1
        updated["build"] = 0
        return updated

    if release_type == "build":
        updated["build"] += 1
        return updated

    raise ValueError(f"Unbekannter Release-Typ: {release_type}")