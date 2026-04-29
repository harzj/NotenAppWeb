"""
Generate a sample grade Excel file for class 7p.

Usage:
    python create_sample.py
    python create_sample.py --password geheim  (with encryption)

Output: Notendatei_7p.xlsx  (in the current directory)
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.excel.writer import build_gradebook
from app.excel import schema as S

# ── Configuration ─────────────────────────────────────────────────────────────
KLASSE      = "7p"
OUTPUT_FILE = "Notendatei_7p.xlsx"

# ── Students ──────────────────────────────────────────────────────────────────
# (nachname, vorname, status, austritt)
_STUDENTS_RAW = [
    ("Bauer",     "Anna",        S.SD_STATUS_AKTIV,           ""),
    ("Fischer",   "Lukas",       S.SD_STATUS_AKTIV,           ""),
    ("Hoffmann",  "Sophie",      S.SD_STATUS_AKTIV,           ""),
    ("Klein",     "Maximilian",  S.SD_STATUS_AKTIV,           ""),
    ("Koch",      "Emma",        S.SD_STATUS_AKTIV,           ""),
    ("Lehmann",   "Jonas",       S.SD_STATUS_AUSGESCHIEDEN,   "31.01.2026"),   # left at Halbjahr
    ("Meyer",     "Lena",        S.SD_STATUS_AKTIV,           ""),
    ("Müller",    "Felix",       S.SD_STATUS_AKTIV,           ""),
    ("Neumann",   "Clara",       S.SD_STATUS_AKTIV,           ""),
    ("Peters",    "Tobias",      S.SD_STATUS_AKTIV,           ""),
    ("Richter",   "Laura",       S.SD_STATUS_AKTIV,           ""),
    ("Schmidt",   "Noah",        S.SD_STATUS_AKTIV,           ""),
    ("Schneider", "Marie",       S.SD_STATUS_AKTIV,           ""),
    ("Wagner",    "Paul",        S.SD_STATUS_AKTIV,           ""),
    ("Weber",     "Julia",       S.SD_STATUS_AKTIV,           ""),
]

STUDENTS = [
    {"nachname": n, "vorname": v, "status": st, "austritt": a}
    for n, v, st, a in _STUDENTS_RAW
]

def _full_name(s):
    return f"{s['nachname']}, {s['vorname']}"

# ── LN 1: Klausur 1 (vor Halbjahr, alle 15 Schüler) ──────────────────────────
LN1_AUFGABEN = [
    {"label": "1a", "afb": "I",   "max_punkte": 4},
    {"label": "1b", "afb": "I",   "max_punkte": 4},
    {"label": "2a", "afb": "II",  "max_punkte": 6},
    {"label": "2b", "afb": "II",  "max_punkte": 4},
    {"label": "2c", "afb": "II",  "max_punkte": 4},
    {"label": "3",  "afb": "III", "max_punkte": 8},
]  # max 30

# One score-list per student (same order as STUDENTS)
LN1_PUNKTE = [
    [4, 3, 5, 4, 3, 7],  # Bauer, Anna       26/30 = 87% → 13
    [3, 4, 4, 3, 3, 5],  # Fischer, Lukas    22/30 = 73% → 10
    [4, 4, 6, 4, 4, 8],  # Hoffmann, Sophie  30/30 = 100% → 15
    [3, 3, 3, 3, 2, 4],  # Klein, Max        18/30 = 60% → 8
    [4, 4, 5, 4, 4, 7],  # Koch, Emma        28/30 = 93% → 14
    [3, 2, 3, 2, 2, 4],  # Lehmann, Jonas    16/30 = 53% → 6
    [4, 3, 4, 3, 4, 6],  # Meyer, Lena       24/30 = 80% → 12
    [2, 3, 3, 2, 2, 3],  # Müller, Felix     15/30 = 50% → 6
    [4, 4, 5, 3, 3, 7],  # Neumann, Clara    26/30 = 87% → 13
    [3, 3, 4, 3, 3, 5],  # Peters, Tobias    21/30 = 70% → 10
    [4, 4, 6, 4, 3, 7],  # Richter, Laura    28/30 = 93% → 14
    [2, 2, 2, 2, 1, 3],  # Schmidt, Noah     12/30 = 40% → 4
    [3, 4, 4, 4, 3, 6],  # Schneider, Marie  24/30 = 80% → 12
    [1, 2, 2, 1, 1, 2],  # Wagner, Paul       9/30 = 30% → 2
    [3, 3, 5, 3, 3, 6],  # Weber, Julia      23/30 = 77% → 11
]

# ── LN 2: Kurztest 1 (vor Halbjahr, alle 15 Schüler) ─────────────────────────
LN2_AUFGABEN = [
    {"label": "1", "afb": "I",   "max_punkte": 6},
    {"label": "2", "afb": "II",  "max_punkte": 8},
    {"label": "3", "afb": "III", "max_punkte": 6},
]  # max 20

LN2_PUNKTE = [
    [6, 7, 5],  # Bauer, Anna       18/20 = 90% → 14
    [5, 5, 3],  # Fischer, Lukas    13/20 = 65% → 9
    [6, 8, 6],  # Hoffmann, Sophie  20/20 = 100% → 15
    [4, 4, 2],  # Klein, Max        10/20 = 50% → 6
    [5, 7, 5],  # Koch, Emma        17/20 = 85% → 13
    [4, 4, 3],  # Lehmann, Jonas    11/20 = 55% → 7
    [5, 6, 4],  # Meyer, Lena       15/20 = 75% → 11
    [3, 4, 2],  # Müller, Felix      9/20 = 45% → 5
    [6, 7, 5],  # Neumann, Clara    18/20 = 90% → 14
    [5, 5, 4],  # Peters, Tobias    14/20 = 70% → 10
    [6, 7, 5],  # Richter, Laura    18/20 = 90% → 14
    [3, 3, 2],  # Schmidt, Noah      8/20 = 40% → 4
    [5, 6, 4],  # Schneider, Marie  15/20 = 75% → 11
    [2, 2, 1],  # Wagner, Paul       5/20 = 25% → 1
    [5, 6, 4],  # Weber, Julia      15/20 = 75% → 11
]

# ── LN 3: Klausur 2 (nach Halbjahr, ohne Lehmann) ────────────────────────────
LN3_AUFGABEN = [
    {"label": "1a", "afb": "I",   "max_punkte": 4},
    {"label": "1b", "afb": "I",   "max_punkte": 4},
    {"label": "2",  "afb": "II",  "max_punkte": 10},
    {"label": "3a", "afb": "II",  "max_punkte": 4},
    {"label": "3b", "afb": "III", "max_punkte": 8},
]  # max 30

# Lehmann (index 5) is not present — 14 students only
_LN3_NAMES_PUNKTE = [
    ("Bauer, Anna",        [4, 4, 9,  4, 7]),   # 28/30 = 93% → 14
    ("Fischer, Lukas",     [3, 3, 6,  3, 4]),   # 19/30 = 63% → 9
    ("Hoffmann, Sophie",   [4, 4, 10, 4, 8]),   # 30/30 = 100% → 15
    ("Klein, Maximilian",  [3, 2, 4,  2, 3]),   # 14/30 = 47% → 5
    ("Koch, Emma",         [4, 4, 8,  4, 7]),   # 27/30 = 90% → 14
    ("Meyer, Lena",        [4, 3, 7,  3, 6]),   # 23/30 = 77% → 11
    ("Müller, Felix",      [2, 2, 4,  2, 3]),   # 13/30 = 43% → 4
    ("Neumann, Clara",     [4, 4, 9,  4, 6]),   # 27/30 = 90% → 14
    ("Peters, Tobias",     [3, 3, 6,  3, 5]),   # 20/30 = 67% → 9
    ("Richter, Laura",     [4, 4, 9,  4, 7]),   # 28/30 = 93% → 14
    ("Schmidt, Noah",      [2, 1, 3,  1, 2]),   #  9/30 = 30% → 2
    ("Schneider, Marie",   [3, 4, 7,  3, 6]),   # 23/30 = 77% → 11
    ("Wagner, Paul",       [1, 1, 2,  1, 1]),   #  6/30 = 20% → 1
    ("Weber, Julia",       [3, 4, 7,  3, 5]),   # 22/30 = 73% → 10
]


# ── Build data dict ───────────────────────────────────────────────────────────

def _make_schueler(students, punkte_list, aufgaben, max_total):
    result = []
    for s, punkte in zip(students, punkte_list):
        total = sum(punkte)
        note15 = S.percent_to_note15(total, max_total)
        result.append({
            "name":    _full_name(s),
            "punkte":  [float(p) for p in punkte],
            "note_15": note15,
            "note_6":  S.note15_to_note6(note15),
        })
    return result


def _make_schueler_named(named_punkte, aufgaben, max_total):
    result = []
    for name, punkte in named_punkte:
        total = sum(punkte)
        note15 = S.percent_to_note15(total, max_total)
        result.append({
            "name":    name,
            "punkte":  [float(p) for p in punkte],
            "note_15": note15,
            "note_6":  S.note15_to_note6(note15),
        })
    return result


def build_sample_data() -> dict:
    ln1_max = sum(a["max_punkte"] for a in LN1_AUFGABEN)
    ln2_max = sum(a["max_punkte"] for a in LN2_AUFGABEN)
    ln3_max = sum(a["max_punkte"] for a in LN3_AUFGABEN)

    return {
        "klasse": KLASSE,
        "stammdaten": STUDENTS,
        "leistungsnachweise": [
            {
                "sheet_name": f"{S.LN_SHEET_PREFIX}Klausur 1",
                "name": "Klausur 1",
                "aufgaben": LN1_AUFGABEN,
                "schueler": _make_schueler(STUDENTS, LN1_PUNKTE, LN1_AUFGABEN, ln1_max),
            },
            {
                "sheet_name": f"{S.LN_SHEET_PREFIX}Kurztest 1",
                "name": "Kurztest 1",
                "aufgaben": LN2_AUFGABEN,
                "schueler": _make_schueler(STUDENTS, LN2_PUNKTE, LN2_AUFGABEN, ln2_max),
            },
            {
                "sheet_name": f"{S.LN_SHEET_PREFIX}Klausur 2",
                "name": "Klausur 2",
                "aufgaben": LN3_AUFGABEN,
                "schueler": _make_schueler_named(_LN3_NAMES_PUNKTE, LN3_AUFGABEN, ln3_max),
            },
        ],
        "uebersicht_hj1": None,
        "uebersicht_hj2": None,
        "uebersicht_jahr": None,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Beispiel-Notendatei generieren")
    parser.add_argument("--password", "-p", default="", help="Excel-Passwort (leer = ungeschützt)")
    parser.add_argument("--output", "-o", default=OUTPUT_FILE, help="Ausgabedatei")
    args = parser.parse_args()

    data = build_sample_data()
    password = args.password or None
    file_bytes = build_gradebook(data, password=password)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.output)
    with open(out_path, "wb") as f:
        f.write(file_bytes)

    print(f"Datei erstellt: {out_path}")
    if password:
        print(f"Passwort: {password}")
    print()
    print("Klasse 7p – Schüler:")
    for s in data["stammdaten"]:
        status = f"  [{s['status']}]" if s["status"] == S.SD_STATUS_AUSGESCHIEDEN else ""
        print(f"  {s['nachname']}, {s['vorname']}{status}")
    print()
    print("Leistungsnachweise:")
    for ln in data["leistungsnachweise"]:
        max_p = sum(a["max_punkte"] for a in ln["aufgaben"])
        print(f"  {ln['name']:20s}  {len(ln['schueler'])} Schüler  Max. {int(max_p)} Punkte")


if __name__ == "__main__":
    main()
