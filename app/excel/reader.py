"""
Read a (possibly password-protected) xlsx file into a structured Python dict.
All processing happens in-memory (BytesIO); the file never touches disk.
"""
from __future__ import annotations

import io
import re
from typing import Any

import msoffcrypto
import openpyxl
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.excel import schema as S


class ExcelReadError(Exception):
    pass


# ── Public entry point ────────────────────────────────────────────────────────

def load_gradebook(file_bytes: bytes, password: str | None = None) -> dict:
    """
    Decrypt (if needed) and parse an xlsx grade file.

    Returns a dict with keys:
        klasse: str
        stammdaten: list[dict]
        leistungsnachweise: list[dict]
        uebersicht_hj1: dict | None
        uebersicht_hj2: dict | None
        uebersicht_jahr: dict | None
    """
    wb = _open_workbook(file_bytes, password)
    return {
        "klasse": _read_class_name(wb),
        "stammdaten": _read_stammdaten(wb),
        "leistungsnachweise": _read_all_ln(wb),
        "uebersicht_hj1": _read_uebersicht(wb, S.SHEET_UEBERSICHT_HJ1),
        "uebersicht_hj2": _read_uebersicht(wb, S.SHEET_UEBERSICHT_HJ2),
        "uebersicht_jahr": _read_uebersicht(wb, S.SHEET_UEBERSICHT_JAHR),
    }


# ── Workbook opening ─────────────────────────────────────────────────────────

def _open_workbook(file_bytes: bytes, password: str | None) -> Workbook:
    buf = io.BytesIO(file_bytes)
    try:
        office_file = msoffcrypto.OfficeFile(buf)
        if office_file.is_encrypted():
            if not password:
                raise ExcelReadError("Die Datei ist passwortgeschützt. Bitte Passwort angeben.")
            decrypted = io.BytesIO()
            office_file.load_key(password=password)
            office_file.decrypt(decrypted)
            decrypted.seek(0)
            source = decrypted
        else:
            buf.seek(0)
            source = buf
    except msoffcrypto.exceptions.InvalidKeyError:
        raise ExcelReadError("Falsches Passwort.")
    except Exception as exc:
        raise ExcelReadError(f"Fehler beim Öffnen der Datei: {exc}") from exc

    try:
        wb = openpyxl.load_workbook(source, data_only=False)
    except Exception as exc:
        raise ExcelReadError(f"Ungültiges Excel-Format: {exc}") from exc
    return wb


# ── Class name ────────────────────────────────────────────────────────────────

def _read_class_name(wb: Workbook) -> str:
    if S.SHEET_STAMMDATEN not in wb.sheetnames:
        return ""
    ws: Worksheet = wb[S.SHEET_STAMMDATEN]
    row = list(ws.iter_rows(
        min_row=S.SD_INFO_ROW, max_row=S.SD_INFO_ROW, values_only=True
    ))[0]
    return _str(row, S.SD_CLASS_NAME_VALUE_COL - 1)


# ── Stammdaten ────────────────────────────────────────────────────────────────

def _read_stammdaten(wb: Workbook) -> list[dict]:
    if S.SHEET_STAMMDATEN not in wb.sheetnames:
        return []
    ws: Worksheet = wb[S.SHEET_STAMMDATEN]
    students = []
    for row in ws.iter_rows(min_row=S.SD_DATA_START_ROW, values_only=True):
        if not any(row):
            continue
        students.append({
            "nachname": _str(row, S.SD_COL_NACHNAME - 1),
            "vorname":  _str(row, S.SD_COL_VORNAME  - 1),
            "status":   _str(row, S.SD_COL_STATUS   - 1) or S.SD_STATUS_AKTIV,
            "austritt": _date_str(row, S.SD_COL_AUSTRITT - 1),
        })
    return students


# ── Leistungsnachweise ────────────────────────────────────────────────────────

def _read_all_ln(wb: Workbook) -> list[dict]:
    sd_ws = wb[S.SHEET_STAMMDATEN] if S.SHEET_STAMMDATEN in wb.sheetnames else None
    result = []
    for name in wb.sheetnames:
        if name.startswith(S.LN_SHEET_PREFIX):
            result.append(_read_ln_sheet(wb[name], name, stammdaten_ws=sd_ws))
    return result


def _read_ln_sheet(ws: Worksheet, sheet_name: str, stammdaten_ws: Worksheet | None = None) -> dict:
    ln_name = sheet_name[len(S.LN_SHEET_PREFIX):]

    header_row = list(ws.iter_rows(min_row=S.LN_ROW_HEADER, max_row=S.LN_ROW_HEADER, values_only=True))[0]
    afb_row = list(ws.iter_rows(min_row=S.LN_ROW_AFB, max_row=S.LN_ROW_AFB, values_only=True))[0]
    max_row = list(ws.iter_rows(min_row=S.LN_ROW_MAX, max_row=S.LN_ROW_MAX, values_only=True))[0]

    # Detect task columns: between col 2 and "Gesamt" column
    task_cols: list[dict] = []
    gesamt_col_idx = None
    for i, val in enumerate(header_row):
        if i == 0:
            continue  # name column
        if isinstance(val, str) and val.strip() == S.LN_HEADER_GESAMT:
            gesamt_col_idx = i
            break
        task_cols.append({
            "label": _str(header_row, i) or f"Aufgabe{i}",
            "afb": _str(afb_row, i),
            "max_punkte": _num(max_row, i),
        })

    # Read student rows
    students = []
    for row in ws.iter_rows(min_row=S.LN_DATA_START_ROW, values_only=True):
        raw_name = row[0]
        if not raw_name:
            continue
        if isinstance(raw_name, str) and raw_name.startswith("=") and stammdaten_ws is not None:
            # Formula like =Stammdaten!A3&", "&Stammdaten!B3 — resolve directly from sheet
            m = re.search(r'!A(\d+)', raw_name)
            if m:
                sd_row = int(m.group(1))
                nn = stammdaten_ws.cell(sd_row, S.SD_COL_NACHNAME).value or ""
                vn = stammdaten_ws.cell(sd_row, S.SD_COL_VORNAME).value or ""
                student_name = f"{nn}, {vn}".strip(", ") if (nn or vn) else _str(row, 0)
            else:
                student_name = _str(row, 0)
        else:
            student_name = _str(row, 0)
        punkte = []
        for t_idx in range(len(task_cols)):
            col_i = S.LN_COL_TASKS_START - 1 + t_idx
            punkte.append(_num(row, col_i))

        note15 = None
        note6 = None
        if gesamt_col_idx is not None:
            note15 = _num(row, gesamt_col_idx + 1)
            note6 = _num(row, gesamt_col_idx + 2)

        students.append({
            "name": student_name,
            "punkte": punkte,
            "note_15": int(note15) if note15 is not None else None,
            "note_6": int(note6) if note6 is not None else None,
        })

    return {
        "sheet_name": sheet_name,
        "name": ln_name,
        "aufgaben": task_cols,
        "schueler": students,
    }


# ── Übersichten ───────────────────────────────────────────────────────────────

def _read_uebersicht(wb: Workbook, sheet_name: str) -> dict | None:
    if sheet_name not in wb.sheetnames:
        return None
    ws: Worksheet = wb[sheet_name]
    header_row = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))[0]
    columns = [v for v in header_row if v is not None]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        rows.append(list(row[: len(columns)]))
    return {"columns": columns, "rows": rows}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _str(row: tuple, idx: int) -> str:
    try:
        v = row[idx]
        return str(v).strip() if v is not None else ""
    except IndexError:
        return ""


def _num(row: tuple, idx: int) -> float | None:
    try:
        v = row[idx]
        if v is None:
            return None
        return float(v)
    except (IndexError, TypeError, ValueError):
        return None


def _date_str(row: tuple, idx: int) -> str:
    try:
        v = row[idx]
        if v is None:
            return ""
        if hasattr(v, "strftime"):
            return v.strftime("%d.%m.%Y")
        return str(v).strip()
    except IndexError:
        return ""
