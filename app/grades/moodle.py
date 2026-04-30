"""Parser for Moodle quiz exports (CSV with ';' separator or XLSX).

Supports multi-file merging for A/B test groups where the same test is
distributed across multiple groups with separate Moodle exports.
"""
from __future__ import annotations

import csv
import io
from difflib import SequenceMatcher

import openpyxl


class MoodleParseError(Exception):
    pass


# ── Public API ────────────────────────────────────────────────────────────────

def parse_moodle_file(file_bytes: bytes, filename: str) -> dict:
    """Parse one Moodle export file.

    Returns::

        {
            "tasks":    [{"name": str, "max_punkte": float}, ...],
            "students": [{"nachname": str, "vorname": str,
                          "punkte": {task_name: float | None}}, ...],
        }
    """
    if filename.lower().endswith(".csv"):
        rows, headers = _read_csv(file_bytes)
    else:
        rows, headers = _read_xlsx(file_bytes)
    return _process(rows, headers)


def merge_files(parsed_files: list) -> dict:
    """Merge multiple parsed Moodle files (one per group).

    Task matching across files is done by max_punkte so that A/B exports
    with different question orderings are handled correctly.
    Students are merged: first occurrence per name wins.
    """
    if not parsed_files:
        return {"tasks": [], "students": []}
    if len(parsed_files) == 1:
        return parsed_files[0]

    base = parsed_files[0]

    # Build lookup: max_punkte → [canonical task names] (in order)
    max_to_canonical: dict = {}
    for t in base["tasks"]:
        max_to_canonical.setdefault(t["max_punkte"], []).append(t["name"])

    def _key(s: dict) -> str:
        return f"{s['nachname'].strip().lower()}|{s['vorname'].strip().lower()}"

    merged: dict = {_key(s): s for s in base["students"]}

    for extra in parsed_files[1:]:
        # Map extra task names to canonical names
        used: set = set()
        task_map: dict = {}
        for et in extra["tasks"]:
            candidates = max_to_canonical.get(et["max_punkte"], [])
            for cand in candidates:
                if cand not in used:
                    task_map[et["name"]] = cand
                    used.add(cand)
                    break

        for s in extra["students"]:
            key = _key(s)
            if key in merged:
                continue  # already have this student
            remapped: dict = {t["name"]: None for t in base["tasks"]}
            for et_name, pts in s["punkte"].items():
                canon = task_map.get(et_name)
                if canon:
                    remapped[canon] = pts
            merged[key] = {
                "nachname": s["nachname"],
                "vorname": s["vorname"],
                "punkte": remapped,
            }

    return {"tasks": base["tasks"], "students": list(merged.values())}


def match_students(moodle_students: list, stammdaten: list) -> tuple:
    """Match Moodle students to Stammdaten entries.

    Returns:
        matched   – dict {moodle_idx: stammdaten_idx}
        unmatched – list of moodle student dicts with no match
    """

    def norm(s: str) -> str:
        return s.strip().lower()

    sd_index: dict = {}
    for i, s in enumerate(stammdaten):
        key = (norm(s["nachname"]), norm(s["vorname"]))
        sd_index[key] = i

    matched: dict = {}
    unmatched: list = []

    for m_idx, ms in enumerate(moodle_students):
        key = (norm(ms["nachname"]), norm(ms["vorname"]))
        if key in sd_index:
            matched[m_idx] = sd_index[key]
            continue

        # Fallback: only one student with that last name
        nn = norm(ms["nachname"])
        last_matches = [i for (snn, _), i in sd_index.items() if snn == nn]
        if len(last_matches) == 1:
            matched[m_idx] = last_matches[0]
            continue

        # Fuzzy full-name match (threshold 0.75)
        full_ms = f"{norm(ms['nachname'])} {norm(ms['vorname'])}"
        best_score = 0.0
        best_i = -1
        for (snn, svn), i in sd_index.items():
            score = SequenceMatcher(None, full_ms, f"{snn} {svn}").ratio()
            if score > best_score:
                best_score = score
                best_i = i

        if best_score >= 0.75 and best_i >= 0:
            matched[m_idx] = best_i
        else:
            unmatched.append(ms)

    return matched, unmatched


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_csv(file_bytes: bytes) -> tuple:
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise MoodleParseError("CSV-Datei konnte nicht dekodiert werden.")

    for sep in (";", ",", "\t"):
        reader = csv.DictReader(io.StringIO(text), delimiter=sep)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
        if rows and "Nachname" in fieldnames:
            return rows, fieldnames

    raise MoodleParseError(
        "Spalte 'Nachname' nicht gefunden. Ist das Trennzeichen ';'?"
    )


def _read_xlsx(file_bytes: bytes) -> tuple:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    rows_raw = list(ws.iter_rows(values_only=True))
    if not rows_raw:
        raise MoodleParseError("XLSX-Datei ist leer.")

    headers = [str(c).strip() if c is not None else "" for c in rows_raw[0]]
    rows = []
    for raw in rows_raw[1:]:
        if not any(c for c in raw if c is not None):
            continue
        row_dict = {
            headers[i]: (str(raw[i]).strip() if i < len(raw) and raw[i] is not None else "")
            for i in range(len(headers))
        }
        rows.append(row_dict)

    return rows, headers


def _process(rows: list, headers: list) -> dict:
    if "Nachname" not in headers or "Vorname" not in headers:
        raise MoodleParseError("Spalten 'Nachname' und 'Vorname' nicht gefunden.")

    # Task columns: contain '/' but don't start with 'Bewertung'
    task_cols: list = []  # list of (col_name, task_display_name, max_punkte)
    for col in headers:
        if not isinstance(col, str) or not col.strip():
            continue
        if col.startswith("Bewertung"):
            continue
        if "/" in col:
            parts = col.rsplit("/", 1)
            if len(parts) == 2:
                try:
                    max_pts = float(parts[1].strip().replace(",", "."))
                    task_name = parts[0].strip()
                    task_cols.append((col, task_name, max_pts))
                except ValueError:
                    continue

    tasks = [{"name": name, "max_punkte": mp} for _, name, mp in task_cols]

    skip_names = {"gesamtdurchschnitt", "overall average", ""}
    students = []

    for row in rows:
        nachname = str(row.get("Nachname", "")).strip()
        vorname = str(row.get("Vorname", "")).strip()
        if not nachname or nachname.lower() in skip_names:
            continue

        punkte: dict = {}
        for col, task_name, _ in task_cols:
            raw = str(row.get(col, "")).strip()
            punkte[task_name] = _parse_score(raw)

        students.append({"nachname": nachname, "vorname": vorname, "punkte": punkte})

    return {"tasks": tasks, "students": students}


def _parse_score(raw: str):
    """Parse '7,50 / 10,00' or '7.5' or '-' → float or None."""
    raw = raw.strip()
    if not raw or raw in ("-", "--", ""):
        return None
    raw = raw.split("/")[0].strip()
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None
