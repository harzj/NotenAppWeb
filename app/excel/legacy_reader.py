"""
Legacy Excel gradebook reader (old format, pre-NotenAppWeb).

Sheet structure found in old files:
  GLN1, GLN 1, GLN2…   – Große Leistungsnachweise
  KLN 1, KLN 2…        – Kleine LN sets, each containing multiple sub-tests (HÜ)
  Noten                 – HJ1 summary: MDL1/MDL2, HJ1 Zeugnisnote, SL1/SL2 actuals
  Noten (2)             – full-year summary: MDL3/MDL4, Ganzjahresnote, SL3/SL4 actuals
"""
from __future__ import annotations

import io
import re
from typing import Optional

import msoffcrypto
import openpyxl
from openpyxl.workbook import Workbook

from app.excel import schema as S


# ── helpers ───────────────────────────────────────────────────────────────────

def _open_wb(file_bytes: bytes, password: Optional[str] = None) -> Workbook:
    raw = io.BytesIO(file_bytes)
    try:
        ofd = msoffcrypto.OfficeFile(io.BytesIO(file_bytes))
        if ofd.is_encrypted():
            dec = io.BytesIO()
            ofd.load_key(password=password or "")
            ofd.decrypt(dec)
            dec.seek(0)
            return openpyxl.load_workbook(dec, data_only=True)
    except Exception:
        pass
    return openpyxl.load_workbook(raw, data_only=True)


def _cell_str(ws, row: int, col: int) -> Optional[str]:
    v = ws.cell(row, col).value
    if v is None:
        return None
    s = str(v).strip()
    return s if s and not s.startswith("#") else None


def _cell_num(ws, row: int, col: int) -> Optional[float]:
    v = ws.cell(row, col).value
    if v is None:
        return None
    try:
        f = float(v)
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


def _int_or_none(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return round(float(v))
    except (ValueError, TypeError):
        return None


# ── student extraction ────────────────────────────────────────────────────────

_SKIP_NAMES = {"max punkte", "teilaufgabe", "gewicht"}
_SKIP_KLN_COLS = {"notentabelle", "mw", "mittelwert", "gesamt", "note", "note(15)", "note(6)", "summe"}


def _get_students(wb: Workbook) -> list[str]:
    """Extract ordered student name list from Noten or first available sheet."""
    for sheet_name in ["Noten", "KLN 1", "KLN1", "GLN1", "GLN 1"]:
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        names = []
        for r in range(4, ws.max_row + 1):
            v = ws.cell(r, 1).value
            if not v:
                continue
            name = str(v).strip()
            if not name or name.startswith("#") or name.lower() in _SKIP_NAMES:
                continue
            names.append(name)
        if names:
            return names
    return []


# ── KLN sheet scanning ────────────────────────────────────────────────────────

def _scan_kln_sheet(ws) -> list[dict]:
    """Return list of importable HÜ entries {col, name, max_pts}."""
    hue_list = []
    max_col = ws.max_column or 20
    row1 = [ws.cell(1, c).value for c in range(1, max_col + 1)]
    row3 = [ws.cell(3, c).value for c in range(1, max_col + 1)]

    for i, name in enumerate(row1):
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name.lower() in _SKIP_KLN_COLS:
            continue
        col = i + 1  # 1-based
        raw_max = row3[i] if i < len(row3) else None
        try:
            max_pts = float(raw_max) if raw_max is not None else 0.0
        except (ValueError, TypeError):
            max_pts = 0.0
        if max_pts > 0:
            hue_list.append({"col": col, "name": name, "max_pts": round(max_pts)})
    return hue_list


# ── public: probe file ────────────────────────────────────────────────────────

def probe_legacy_file(file_bytes: bytes, password: Optional[str] = None) -> dict:
    """
    Open the legacy file and return a JSON-serialisable structure description
    for use in the import wizard.
    """
    wb = _open_wb(file_bytes, password)
    students = _get_students(wb)

    kln_sheets: list[dict] = []
    gln_sheets: list[str] = []

    for name in wb.sheetnames:
        if re.match(r"^KLN\s*\d+$", name, re.I):
            hue_list = _scan_kln_sheet(wb[name])
            if hue_list:
                kln_sheets.append({"sheet": name, "hue_list": hue_list})
        elif re.match(r"^GLN\s*\d+$", name, re.I):
            gln_sheets.append(name)

    return {
        "students": students,
        "student_count": len(students),
        "kln_sheets": kln_sheets,
        "gln_sheets": gln_sheets,
        "has_noten": "Noten" in wb.sheetnames,
        "has_noten2": "Noten (2)" in wb.sheetnames,
    }


# ── public: execute import ────────────────────────────────────────────────────

def import_legacy_file(file_bytes: bytes, password: Optional[str], selections: dict) -> dict:
    """
    Execute the import based on user selections from the wizard.
    Returns a dict compatible with the standard gradebook session format.
    """
    wb = _open_wb(file_bytes, password)
    students = _get_students(wb)

    lns: list[dict] = []
    mdl_noten: dict = {}
    sl_noten_actual: dict = {}
    hj_noten: dict = {}
    schuljahr_noten_actual: dict = {}

    # ── KLN imports ───────────────────────────────────────────────────────────
    for sel in selections.get("kln_imports", []):
        ln = _read_kln_entry(wb, sel, students)
        if ln:
            lns.append(ln)

    # ── GLN imports ───────────────────────────────────────────────────────────
    for sel in selections.get("gln_imports", []):
        ln = _read_gln_entry(wb, sel, students)
        if ln:
            lns.append(ln)

    # ── bis_sl controls how much of the Noten sheets to import ─────────────
    bis_sl = selections.get("bis_sl", "SL4")  # "SL1" | "SL2" | "SL3" | "SL4"

    if bis_sl in ("SL1", "SL2", "SL3", "SL4") and "Noten" in wb.sheetnames:
        _read_noten_hj1(wb["Noten"], students, mdl_noten, sl_noten_actual, hj_noten, bis_sl)

    if bis_sl in ("SL3", "SL4") and "Noten (2)" in wb.sheetnames:
        _read_noten_hj2(wb["Noten (2)"], students, mdl_noten, sl_noten_actual, schuljahr_noten_actual, bis_sl)

    # ── determine inactive students (in Noten but not in Noten (2)) ──────────
    ausgeschieden_names: set = set()
    if "Noten (2)" in wb.sheetnames:
        ws2 = wb["Noten (2)"]
        noten2_names: set = set()
        for r2 in range(4, ws2.max_row + 1):
            raw = ws2.cell(r2, 1).value
            if not raw:
                continue
            n2 = str(raw).strip()
            if n2 and not n2.startswith("#") and n2.lower() not in _SKIP_NAMES:
                noten2_names.add(n2)
        if noten2_names:
            ausgeschieden_names = set(students) - noten2_names

    # ── build stammdaten ──────────────────────────────────────────────────────
    stammdaten = []
    for name in students:
        parts = name.split(",", 1)
        nachname = parts[0].strip()
        vorname = parts[1].strip() if len(parts) > 1 else ""
        status = S.SD_STATUS_AUSGESCHIEDEN if name in ausgeschieden_names else S.SD_STATUS_AKTIV
        stammdaten.append({"nachname": nachname, "vorname": vorname, "notizen": "",
                           "status": status, "austritt": ""})

    return {
        "klasse": selections.get("klasse", ""),
        "fach": selections.get("fach", ""),
        "schuljahr": selections.get("schuljahr", ""),
        "stammdaten": stammdaten,
        "leistungsnachweise": lns,
        "mdl_noten": mdl_noten,
        "sl_noten_actual": sl_noten_actual,
        "hj_noten": hj_noten,
        "schuljahr_noten_actual": schuljahr_noten_actual,
        "uebersicht_hj1": None,
        "uebersicht_hj2": None,
        "uebersicht_jahr": None,
        "sl_gewichtung": None,
    }


# ── KLN entry reader ──────────────────────────────────────────────────────────

def _read_kln_entry(wb: Workbook, sel: dict, students: list[str]) -> Optional[dict]:
    sheet_name: str = sel["sheet"]
    col: int = sel["col"]           # 1-based column for the HÜ points
    hue_name: str = sel["name"]
    max_pts: int = sel["max_pts"]
    hj: str = sel["hj"]
    sl: str = sel["sl"]

    if sheet_name not in wb.sheetnames:
        return None
    ws = wb[sheet_name]

    # Unique internal name: e.g. "KLN1-HÜ1"
    ln_name = f"{sheet_name.replace(' ', '')}-{hue_name}"

    schueler = []
    for r in range(4, ws.max_row + 1):
        raw_name = ws.cell(r, 1).value
        if not raw_name:
            continue
        name = str(raw_name).strip()
        if not name or name.startswith("#") or name.lower() in _SKIP_NAMES:
            continue

        pts_raw = ws.cell(r, col).value
        try:
            pts = round(float(pts_raw), 2) if pts_raw is not None else None
        except (ValueError, TypeError):
            pts = None

        schueler.append(
            {
                "name": name,
                "punkte": [pts],
                "note_15": None,
                "note_6": None,
                "ignoriert": False,
            }
        )

    return {
        "sheet_name": f"LN_{ln_name}",
        "name": ln_name,
        "ln_typ": "KLN",
        "hj": hj,
        "sl_zuordnung": sl,
        "aufgaben": [{"label": "Gesamt", "afb": "", "max_punkte": max_pts}],
        "aufgaben_tree": [],
        "schueler": schueler,
    }


# ── GLN entry reader ──────────────────────────────────────────────────────────

def _read_gln_entry(wb: Workbook, sel: dict, students: list[str]) -> Optional[dict]:
    sheet_name: str = sel["sheet"]
    hj: str = sel["hj"]
    sl: Optional[str] = sel.get("sl")

    if sheet_name not in wb.sheetnames:
        return None
    ws = wb[sheet_name]

    # Find "Gesamt" column index in row 2
    max_col = ws.max_column or 25
    gesamt_col: Optional[int] = None
    for c in range(1, max_col + 1):
        v = ws.cell(2, c).value
        if isinstance(v, str) and v.strip() == "Gesamt":
            gesamt_col = c
            break

    # Max points from row 3 col O (or Gesamt col)
    gesamt_max = 100
    if gesamt_col:
        raw = ws.cell(3, gesamt_col).value
        try:
            gesamt_max = round(float(raw)) if raw else 100
        except (ValueError, TypeError):
            gesamt_max = 100

    ln_name = sheet_name.replace(" ", "")
    schueler = []
    for r in range(4, ws.max_row + 1):
        raw_name = ws.cell(r, 1).value
        if not raw_name:
            continue
        name = str(raw_name).strip()
        if not name or name.startswith("#") or name.lower() in _SKIP_NAMES:
            continue

        # Note(15) after Gesamt col: Gesamt+1
        note15: Optional[int] = None
        note6: Optional[int] = None
        if gesamt_col:
            note15 = _int_or_none(ws.cell(r, gesamt_col + 1).value)
            note6 = _int_or_none(ws.cell(r, gesamt_col + 2).value)

        # punkte: try Gesamt column (often None for cross-sheet refs)
        pts: Optional[float] = None
        if gesamt_col:
            pts_raw = ws.cell(r, gesamt_col).value
            try:
                pts = round(float(pts_raw), 2) if pts_raw is not None else None
            except (ValueError, TypeError):
                pts = None

        schueler.append(
            {
                "name": name,
                "punkte": [pts],
                "note_15": note15,
                "note_6": note6,
                "ignoriert": False,
            }
        )

    return {
        "sheet_name": f"LN_{ln_name}",
        "name": ln_name,
        "ln_typ": "GLN",
        "hj": hj,
        "sl_zuordnung": sl,
        "aufgaben": [{"label": "Gesamt", "afb": "", "max_punkte": gesamt_max}],
        "aufgaben_tree": [],
        "schueler": schueler,
    }


# ── Noten sheet readers ───────────────────────────────────────────────────────

def _note_from_cell(ws, row: int, col: int) -> Optional[int]:
    v = ws.cell(row, col).value
    if v is None:
        return None
    try:
        f = float(v)
        if 0 <= f <= 15:
            return round(f)
        return None
    except (ValueError, TypeError):
        return None


def _read_noten_hj1(
    ws,
    students: list[str],
    mdl_noten: dict,
    sl_noten_actual: dict,
    hj_noten: dict,
    bis_sl: str = "SL2",
) -> None:
    """
    Extract from "Noten" sheet (HJ1):
      Col B (2)  = MDL 1  → mdl_noten[name]['SL1']
      Col C (3)  = MDL 2  → mdl_noten[name]['SL2']  (only if bis_sl != 'SL1')
      Col I (9)  = Note (HJ1 Zeugnisnote)            (only if bis_sl != 'SL1')
      Col O (15) = SL 1 end
      Col S (19) = SL2 end                           (only if bis_sl != 'SL1')
    """
    for r in range(4, ws.max_row + 1):
        raw_name = ws.cell(r, 1).value
        if not raw_name:
            continue
        name = str(raw_name).strip()
        if not name or name.startswith("#") or name.lower() in _SKIP_NAMES:
            continue

        mdl1 = _note_from_cell(ws, r, 2)
        sl1_end = _note_from_cell(ws, r, 15)

        if mdl1 is not None:
            mdl_noten.setdefault(name, {})["SL1"] = mdl1
        if sl1_end is not None:
            sl_noten_actual.setdefault(name, {})["SL1"] = sl1_end

        if bis_sl != "SL1":
            mdl2 = _note_from_cell(ws, r, 3)
            hj1_note = _note_from_cell(ws, r, 9)
            sl2_end = _note_from_cell(ws, r, 19)
            if mdl2 is not None:
                mdl_noten.setdefault(name, {})["SL2"] = mdl2
            if hj1_note is not None:
                hj_noten.setdefault(name, {})["HJ1"] = hj1_note
            if sl2_end is not None:
                sl_noten_actual.setdefault(name, {})["SL2"] = sl2_end


def _read_noten_hj2(
    ws,
    students: list[str],
    mdl_noten: dict,
    sl_noten_actual: dict,
    schuljahr_noten_actual: dict,
    bis_sl: str = "SL4",
) -> None:
    """
    Extract from "Noten (2)" sheet (full year):
      Col B (2)  = MDL3  → mdl_noten[name]['SL3']
      Col C (3)  = MDL4  → mdl_noten[name]['SL4']  (only if bis_sl == 'SL4')
      Col I (9)  = Ganzjahresnote                   (only if bis_sl == 'SL4')
      Col P (16) = SL 3 end
      Col T (20) = SL4 end                          (only if bis_sl == 'SL4')
    """
    for r in range(4, ws.max_row + 1):
        raw_name = ws.cell(r, 1).value
        if not raw_name:
            continue
        name = str(raw_name).strip()
        if not name or name.startswith("#") or name.lower() in _SKIP_NAMES:
            continue

        mdl3 = _note_from_cell(ws, r, 2)
        sl3_end = _note_from_cell(ws, r, 16)

        if mdl3 is not None:
            mdl_noten.setdefault(name, {})["SL3"] = mdl3
        if sl3_end is not None:
            sl_noten_actual.setdefault(name, {})["SL3"] = sl3_end

        if bis_sl == "SL4":
            mdl4 = _note_from_cell(ws, r, 3)
            gj_note = _note_from_cell(ws, r, 9)
            sl4_end = _note_from_cell(ws, r, 20)
            if mdl4 is not None:
                mdl_noten.setdefault(name, {})["SL4"] = mdl4
            if gj_note is not None:
                schuljahr_noten_actual[name] = gj_note
            if sl4_end is not None:
                sl_noten_actual.setdefault(name, {})["SL4"] = sl4_end
