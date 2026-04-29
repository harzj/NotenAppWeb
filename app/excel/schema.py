"""
Central schema definition for grade Excel files.
All column positions and sheet structures are defined here.
"""

# ── Sheet names ──────────────────────────────────────────────────────────────
SHEET_STAMMDATEN = "Stammdaten"
SHEET_NOTENTABELLE = "Notentabelle"
SHEET_UEBERSICHT_HJ1 = "Noten_HJ1"
SHEET_UEBERSICHT_HJ2 = "Noten_HJ2"
SHEET_UEBERSICHT_JAHR = "Noten_Jahr"

LN_SHEET_PREFIX = "LN_"

# ── Stammdaten sheet rows and columns (1-based) ───────────────────────────────
# Row 1:  class name metadata  ("Klasse:" | "7p")
# Row 2:  column headers
# Row 3+: student data
SD_INFO_ROW = 1
SD_CLASS_NAME_LABEL = "Klasse:"
SD_CLASS_NAME_LABEL_COL = 1
SD_CLASS_NAME_VALUE_COL = 2

SD_HEADER_ROW = 2
SD_DATA_START_ROW = 3

SD_COL_NACHNAME = 1
SD_COL_VORNAME  = 2
SD_COL_STATUS   = 3      # "Aktiv" | "Ausgeschieden"
SD_COL_AUSTRITT = 4      # Date of leaving, may be empty

SD_STATUS_AKTIV = "Aktiv"
SD_STATUS_AUSGESCHIEDEN = "Ausgeschieden"

# ── Leistungsnachweis sheet rows (1-based) ────────────────────────────────────
LN_ROW_HEADER = 1        # "Aufgabe" | 1a | 1b | ... | Gesamt | Note(0-15) | Note(1-6)
LN_ROW_AFB = 2           # "Anforderungsbereich" | I | II | III | ...
LN_ROW_MAX = 3           # "Max. Punkte" | n | n | ... | =SUMME(...) | (empty) | (empty)
LN_DATA_START_ROW = 4    # First student row

# Column offsets inside an LN sheet (relative to col 1)
LN_COL_NAME = 1          # "Mustermann, Max"
LN_COL_TASKS_START = 2   # First sub-task column
# LN_COL_GESAMT  = last_task_col + 1  (dynamic, written by writer)
# LN_COL_NOTE_15 = last_task_col + 2
# LN_COL_NOTE_6  = last_task_col + 3

LN_HEADER_NAME = "Schüler"
LN_HEADER_AFB_LABEL = "Anforderungsbereich"
LN_HEADER_MAX_LABEL = "Max. Punkte"
LN_HEADER_GESAMT = "Gesamt"
LN_HEADER_NOTE_15 = "Note (0-15)"
LN_HEADER_NOTE_6 = "Note (1-6)"

AFB_VALUES = ("I", "II", "III", "")

# ── Overview sheet columns ─────────────────────────────────────────────────
OV_COL_NAME = 1
OV_COL_LN_START = 2      # LN notes start here; last cols = Durchschnitt, Zeugnisnote

# ── Notentabelle sheet (hidden, for Excel XLOOKUP / MATCH) ─────────────────
NT_COL_PERCENT = 1       # lower bound (fraction, e.g. 0.95)
NT_COL_NOTE_15 = 2       # corresponding note 0-15
NT_HEADER_ROW = 1
NT_DATA_START_ROW = 2

# ── Grade scale (percentage → points 0-15) ──────────────────────────────────
# List of (min_percent_inclusive, note_0_15) sorted descending by percent
GRADE_SCALE: list[tuple[float, int]] = [
    (0.95, 15),
    (0.90, 14),
    (0.85, 13),
    (0.80, 12),
    (0.75, 11),
    (0.70, 10),
    (0.65, 9),
    (0.60, 8),
    (0.55, 7),
    (0.50, 6),
    (0.45, 5),
    (0.40, 4),
    (0.33, 3),
    (0.27, 2),
    (0.20, 1),
    (0.0,  0),
]

# Note 0-15 → Note 1-6
NOTE_15_TO_6: dict[int, int] = {
    15: 1, 14: 1, 13: 1,
    12: 2, 11: 2, 10: 2,
    9: 3,  8: 3,  7: 3,
    6: 4,  5: 4,  4: 4,
    3: 5,  2: 5,  1: 5,
    0: 6,
}


def percent_to_note15(achieved: float, maximum: float) -> int:
    """Calculate note (0-15) from achieved points and maximum points."""
    if maximum <= 0:
        return 0
    pct = achieved / maximum
    for threshold, note in GRADE_SCALE:
        if pct >= threshold:
            return note
    return 0


def note15_to_note6(note: int) -> int:
    return NOTE_15_TO_6.get(note, 6)
