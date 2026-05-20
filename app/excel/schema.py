"""
Central schema definition for grade Excel files.
All column positions and sheet structures are defined here.
"""

# ── Sheet names ──────────────────────────────────────────────────────────────
SHEET_STAMMDATEN = "Stammdaten"
SHEET_NOTENTABELLE = "Notentabelle"
SHEET_UEBERSICHT_HJ1 = "Noten_HJ1"
SHEET_UEBERSICHT_HJ2 = "Noten_HJ2"
SHEET_UEBERSICHT_HJ3 = "Noten_HJ3"
SHEET_UEBERSICHT_HJ4 = "Noten_HJ4"
SHEET_UEBERSICHT_JAHR = "Noten_Jahr"
SHEET_NOTEN_ZUSATZ = "Noten_Zusatz"    # hidden: mdl/sl/hj/sj actual notes
SHEET_EINSTELLUNGEN = "Einstellungen"  # hidden: sl_gewichtung

LN_SHEET_PREFIX = "LN_"
LN_TYP_ABT = "ABT"  # Abiturprüfung

# ── Stammdaten sheet rows and columns (1-based) ───────────────────────────────
# Row 1:  class name metadata  ("Klasse:" | "7p")
# Row 2:  column headers
# Row 3+: student data
SD_INFO_ROW = 1
SD_CLASS_NAME_LABEL = "Klasse:"
SD_CLASS_NAME_LABEL_COL = 1
SD_CLASS_NAME_VALUE_COL = 2
SD_FACH_LABEL = "Fach:"
SD_FACH_LABEL_COL = 3
SD_FACH_VALUE_COL = 4
SD_SJ_LABEL = "Schuljahr:"
SD_SJ_LABEL_COL = 5
SD_SJ_VALUE_COL = 6

SD_HEADER_ROW = 2
SD_DATA_START_ROW = 3

SD_COL_NACHNAME = 1
SD_COL_VORNAME  = 2
SD_COL_STATUS   = 3      # "Aktiv" | "Ausgeschieden"
SD_COL_AUSTRITT = 4      # Date of leaving, may be empty
SD_COL_ABGANG_HJ = 5     # Abgang nach Halbjahr (Kurs mode), e.g. "HJ2"

SD_STATUS_AKTIV = "Aktiv"
SD_STATUS_AUSGESCHIEDEN = "Ausgeschieden"

# ── Leistungsnachweis sheet rows (1-based) ────────────────────────────────────
# New format (v2): row 1 is a metadata row.  Old format has no meta row.
LN_ROW_META = 1          # metadata: LN_TYP | value | HJ | value | SL_ZUORDNUNG | value
LN_ROW_HEADER = 2        # "Aufgabe" | 1a | 1b | ... | Gesamt | Note(0-15) | Note(1-6) | Ignoriert
LN_ROW_AFB = 3           # "Anforderungsbereich" | I | II | III | ...
LN_ROW_MAX = 4           # "Max. Punkte" | n | n | ... | =SUMME(...) | (empty) | (empty)
LN_DATA_START_ROW = 5    # First student row

# LN metadata row labels / column positions
LN_META_TYP_LABEL = "LN_TYP"
LN_META_TYP_COL   = 1
LN_META_TYP_VAL   = 2
LN_META_HJ_LABEL  = "HJ"
LN_META_HJ_COL    = 3
LN_META_HJ_VAL    = 4
LN_META_SL_LABEL  = "SL_ZUORDNUNG"
LN_META_SL_COL    = 5
LN_META_SL_VAL    = 6
LN_META_GSLOT_LABEL = "GLN_SLOT"
LN_META_GSLOT_COL   = 7
LN_META_GSLOT_VAL   = 8
LN_META_NT_LABEL    = "NACHTERMIN_VON"   # sheet name of the parent LN
LN_META_NT_COL      = 9
LN_META_NT_VAL      = 10
LN_META_RUNDEN_LABEL = "NOTEN_RUNDEN"
LN_META_RUNDEN_COL   = 11
LN_META_RUNDEN_VAL   = 12

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
LN_HEADER_IGNORIERT = "Ignoriert"   # per-student ignore flag column (non-ABT)
LN_HEADER_KUERZEL = "Kürzel"       # exam candidate code for ABT sheets

AFB_VALUES = ("I", "II", "III", "")

# ── Overview sheet columns ─────────────────────────────────────────────────
OV_COL_NAME = 1
OV_COL_LN_START = 2      # LN notes start here; last cols = Durchschnitt, Zeugnisnote

# ── Notentabelle sheet (hidden, for Excel XLOOKUP / MATCH) ─────────────────
NT_COL_PERCENT = 1       # lower bound (fraction, e.g. 0.95)
NT_COL_NOTE_15 = 2       # corresponding note 0-15
NT_HEADER_ROW = 1
NT_DATA_START_ROW = 2

# ── Noten_Zusatz sheet columns (per-student notes not in LN sheets) ──────────
NZ_HEADER_ROW = 1
NZ_DATA_START = 2
NZ_COL_NAME       = 1
NZ_COL_MDL_SL1    = 2
NZ_COL_MDL_SL2    = 3
NZ_COL_MDL_SL3    = 4
NZ_COL_MDL_SL4    = 5
NZ_COL_SL_ACT_SL1 = 6
NZ_COL_SL_ACT_SL2 = 7
NZ_COL_SL_ACT_SL3 = 8
NZ_COL_SL_ACT_SL4 = 9
NZ_COL_HJ_ACT_HJ1 = 10
NZ_COL_HJ_ACT_HJ2 = 11
NZ_COL_SJ_ACT     = 12
# Kurs mode extra columns (13-22)
NZ_COL_KURS_MDL_HJ1_1 = 13
NZ_COL_KURS_MDL_HJ1_2 = 14
NZ_COL_KURS_MDL_HJ2_1 = 15
NZ_COL_KURS_MDL_HJ2_2 = 16
NZ_COL_KURS_MDL_HJ3_1 = 17
NZ_COL_KURS_MDL_HJ3_2 = 18
NZ_COL_KURS_MDL_HJ4_1 = 19
NZ_COL_KURS_MDL_HJ4_2 = 20
NZ_COL_KURS_HJ_ACT_HJ3 = 21
NZ_COL_KURS_HJ_ACT_HJ4 = 22
NZ_HEADERS = [
    "Schüler",
    "MDL_SL1", "MDL_SL2", "MDL_SL3", "MDL_SL4",
    "SL_Act_SL1", "SL_Act_SL2", "SL_Act_SL3", "SL_Act_SL4",
    "HJ_Act_HJ1", "HJ_Act_HJ2",
    "SJ_Act",
    "KURS_MDL_HJ1_1", "KURS_MDL_HJ1_2",
    "KURS_MDL_HJ2_1", "KURS_MDL_HJ2_2",
    "KURS_MDL_HJ3_1", "KURS_MDL_HJ3_2",
    "KURS_MDL_HJ4_1", "KURS_MDL_HJ4_2",
    "KURS_HJ_Act_HJ3", "KURS_HJ_Act_HJ4",
]

# ── Einstellungen sheet (key→value rows) ──────────────────────────────────────
ES_HEADER_ROW = 1
ES_DATA_START = 2
ES_COL_KEY   = 1
ES_COL_VALUE = 2
ES_GEWICHTUNG_KEYS = ["sl_mdl_pct", "sl_kln_pct", "hj_gln_w", "hj_sl1_w", "hj_sl2_w"]
ES_KURS_KEYS = ["modus", "kurs_typ", "kurs_stunden", "kurs_gln_pct", "kurs_mdl_pct"]

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


# Grade scale with rounding (P > threshold → note); thresholds are exclusive
GRADE_SCALE_RUNDEN: list[tuple[float, int]] = [
    (0.94, 15),
    (0.89, 14),
    (0.84, 13),
    (0.79, 12),
    (0.74, 11),
    (0.69, 10),
    (0.64, 9),
    (0.59, 8),
    (0.54, 7),
    (0.49, 6),
    (0.44, 5),
    (0.39, 4),
    (0.32, 3),
    (0.26, 2),
    (0.19, 1),
    (0.0,  0),
]


def percent_to_note15(achieved: float, maximum: float, runden: bool = True) -> int:
    """Calculate note (0-15) from achieved points and maximum points.
    
    If *runden* is True (default), rounds up when within 1% of next grade.
    """
    if maximum <= 0:
        return 0
    pct = achieved / maximum
    scale = GRADE_SCALE_RUNDEN if runden else GRADE_SCALE
    if runden:
        # exclusive thresholds: P > threshold
        for threshold, note in scale:
            if pct > threshold:
                return note
        return 0
    else:
        for threshold, note in GRADE_SCALE:
            if pct >= threshold:
                return note
        return 0


def note15_to_note6(note: int) -> int:
    return NOTE_15_TO_6.get(note, 6)
