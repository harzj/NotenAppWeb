"""Grade computation helpers for SL-, HJ- and Schuljahr-notes."""
from __future__ import annotations

DEFAULT_GEWICHTUNG: dict = {
    "sl_mdl_pct":   80.0,  # % weight of mündliche note in SL note
    "sl_kln_pct":   20.0,  # % weight of KLN mean in SL note
    "sl_mittel_w":   1.0,  # weight of SL-Mittel vs each GLN in HJ note
    # kept for backward compatibility – no longer used in formula:
    "hj_gln_w":      1.0,
    "hj_sl1_w":      1.0,
    "hj_sl2_w":      1.0,
}


def get_gewichtung(data: dict) -> dict:
    g = dict(DEFAULT_GEWICHTUNG)
    g.update(data.get("sl_gewichtung") or {})
    return g


def get_kln_weights(data: dict, sl_key: str) -> dict:
    """Return {sheet_name: weight} for KLN LNs of the given SL slot.
    Weights default to 1.0. Returns raw weights (not normalised)."""
    stored: dict = (data.get("kln_weights") or {}).get(sl_key, {})
    lns = data.get("leistungsnachweise", [])
    result = {}
    for ln in lns:
        if ln.get("ln_typ") != "KLN" or ln.get("sl_zuordnung") != sl_key:
            continue
        if ln.get("nachtermin_von"):
            continue
        result[ln["sheet_name"]] = float(stored.get(ln["sheet_name"], 1.0))
    return result


def get_gln_weights(data: dict, hj_key: str) -> dict:
    """Return {sheet_name: weight} for GLN LNs of the given HJ.
    Weights default to 1.0. Returns raw weights (not normalised)."""
    stored: dict = (data.get("gln_weights") or {}).get(hj_key, {})
    lns = data.get("leistungsnachweise", [])
    result = {}
    for ln in lns:
        if ln.get("ln_typ") != "GLN" or ln.get("hj") != hj_key:
            continue
        if ln.get("nachtermin_von"):
            continue
        result[ln["sheet_name"]] = float(stored.get(ln["sheet_name"], 1.0))
    return result


# ── KLN / GLN note extraction ─────────────────────────────────────────────────

def _effective_note(student_name: str, ln: dict, all_lns: list) -> float | None:
    """Return the effective note for a student in a (parent) LN.

    If the student has no grade in the parent, check if there is a linked
    Nachtermin (NT) LN – and return the NT grade instead.
    Ignores students marked as ignored in either.
    """
    # Look for student in parent LN
    for s in ln.get("schueler", []):
        if s["name"] != student_name:
            continue
        if s.get("ignoriert"):
            return None
        if s.get("note_15") is not None:
            return float(s["note_15"])
        # Student in parent but no grade – check NT
        nt_sheet = ln["sheet_name"] + "_NT"
        for nt in all_lns:
            if nt.get("sheet_name") == nt_sheet:
                for ns in nt.get("schueler", []):
                    if ns["name"] == student_name and not ns.get("ignoriert"):
                        if ns.get("note_15") is not None:
                            return float(ns["note_15"])
        return None
    return None


def kln_notes_for_sl(student_name: str, sl_key: str, lns: list) -> list[float]:
    """Return list of non-ignored KLN note_15 values for student + SL slot.
    NT (Nachtermin) LNs are skipped — their grade feeds the parent LN."""
    notes = []
    for ln in lns:
        if ln.get("ln_typ") != "KLN" or ln.get("sl_zuordnung") != sl_key:
            continue
        if ln.get("nachtermin_von"):   # skip NT – it's not an independent LN
            continue
        # Effective note: use NT grade if student is in NT and not in parent
        effective = _effective_note(student_name, ln, lns)
        if effective is not None:
            notes.append(effective)
    return notes


def kln_mean_for_sl(
    student_name: str,
    sl_key: str,
    lns: list,
    kln_weights: dict | None = None,
) -> float | None:
    """Return weighted mean of KLN notes for student + SL slot.

    *kln_weights* maps sheet_name → float weight (default 1.0 for each).
    """
    pairs: list[tuple[float, float]] = []
    for ln in lns:
        if ln.get("ln_typ") != "KLN" or ln.get("sl_zuordnung") != sl_key:
            continue
        if ln.get("nachtermin_von"):
            continue
        effective = _effective_note(student_name, ln, lns)
        if effective is not None:
            w = float((kln_weights or {}).get(ln["sheet_name"], 1.0))
            pairs.append((effective, w))
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    return sum(n * w for n, w in pairs) / total_w if total_w > 0 else None


def gln_notes_for_hj(student_name: str, hj: str, lns: list) -> list[float]:
    """Return list of non-ignored GLN note_15 values for student + HJ.
    NT LNs are skipped; parent LN automatically falls back to NT grade."""
    notes = []
    for ln in lns:
        if ln.get("ln_typ") != "GLN" or ln.get("hj") != hj:
            continue
        if ln.get("nachtermin_von"):   # skip NT sheets
            continue
        effective = _effective_note(student_name, ln, lns)
        if effective is not None:
            notes.append(effective)
    return notes


def gln_mean_for_hj(student_name: str, hj: str, lns: list) -> float | None:
    notes = gln_notes_for_hj(student_name, hj, lns)
    return sum(notes) / len(notes) if notes else None


# ── SL note ───────────────────────────────────────────────────────────────────

def compute_sl_note(
    student_name: str,
    sl_key: str,
    lns: list,
    mdl_noten: dict,
    gewichtung: dict,
    kln_weights: dict | None = None,
) -> float | None:
    """Compute SL note (float, 0-15 scale) – unrounded."""
    kln_mean = kln_mean_for_sl(student_name, sl_key, lns, kln_weights)
    mdl = mdl_noten.get(student_name, {}).get(sl_key)
    if mdl is not None:
        mdl = float(mdl)

    if mdl is None and kln_mean is None:
        return None
    if mdl is None:
        return kln_mean
    if kln_mean is None:
        return mdl

    mf = float(gewichtung.get("sl_mdl_pct", 70))
    kf = float(gewichtung.get("sl_kln_pct", 30))
    total = mf + kf
    return (mdl * mf + kln_mean * kf) / total


# ── HJ note ───────────────────────────────────────────────────────────────────

def compute_sl_mittel(
    sl1_note: float | None,
    sl2_note: float | None,
) -> float | None:
    """Arithmetic mean of sl1 and sl2 notes (ignores None values)."""
    vals = [v for v in (sl1_note, sl2_note) if v is not None]
    return sum(vals) / len(vals) if vals else None


def compute_hj_vorschlag(
    student_name: str,
    hj: str,
    lns: list,
    mdl_noten: dict,
    gewichtung: dict,
    kln_weights: dict | None = None,
) -> float | None:
    """Compute suggested HJ note (float, 0-15 scale) – unrounded.

    Erlassvorgabe: SL1+SL2 → sl_mittel (one component, weight sl_mittel_w).
    Each GLN is one component with weight 1.0.
    Formula: (gln1 + gln2 + ... + sl_mittel * sl_mittel_w) / (N_gln + sl_mittel_w)
    """
    sl1_key, sl2_key = ("SL1", "SL2") if hj == "HJ1" else ("SL3", "SL4")

    # Each GLN is one component with weight 1.0
    components: list[tuple[float, float]] = []
    for ln in lns:
        if ln.get("ln_typ") != "GLN" or ln.get("hj") != hj:
            continue
        if ln.get("nachtermin_von"):
            continue
        effective = _effective_note(student_name, ln, lns)
        if effective is not None:
            components.append((effective, 1.0))

    # SL-Mittel = mean(SL1, SL2) as one combined component
    sl1_note = compute_sl_note(student_name, sl1_key, lns, mdl_noten, gewichtung, kln_weights)
    sl2_note = compute_sl_note(student_name, sl2_key, lns, mdl_noten, gewichtung, kln_weights)
    sl_mittel = compute_sl_mittel(sl1_note, sl2_note)
    sl_mittel_w = float(gewichtung.get("sl_mittel_w", 1.0))
    if sl_mittel is not None:
        components.append((sl_mittel, sl_mittel_w))

    if not components:
        return None
    total_weight = sum(w for _, w in components)
    if total_weight <= 0:
        return None
    return sum(n * w for n, w in components) / total_weight


# ── Schuljahr note ────────────────────────────────────────────────────────────

def compute_schuljahr_note(student_name: str, hj_noten: dict) -> float | None:
    """1/3 HJ1 + 2/3 HJ2 (float, unrounded)."""
    hj1 = hj_noten.get(student_name, {}).get("HJ1")
    hj2 = hj_noten.get(student_name, {}).get("HJ2")
    if hj1 is None and hj2 is None:
        return None
    if hj1 is None:
        return float(hj2)
    if hj2 is None:
        return float(hj1)
    return (1.0 / 3) * float(hj1) + (2.0 / 3) * float(hj2)


def compute_schuljahr_note_klasse(
    student_name: str,
    hj_noten: dict,
    aufnahme_ab_hj: str | None,
    vorherige_noten: dict | None,
) -> float | None:
    """Schuljahrnote for Klasse mode, respecting mid-year enrollment.

    If the student was enrolled mid-year (aufnahme_ab_hj == 'HJ2'):
    - No previous note: SJ = HJ2 directly
    - Previous HJ1 note provided: SJ = 1/3 * vorherige_hj1 + 2/3 * HJ2 (normal weighting)

    Otherwise falls back to the standard 1/3 HJ1 + 2/3 HJ2 formula.
    """
    if aufnahme_ab_hj == "HJ2":
        hj2 = hj_noten.get(student_name, {}).get("HJ2")
        if hj2 is None:
            return None
        vorherige_hj1 = (vorherige_noten or {}).get("HJ1")
        if vorherige_hj1 is not None:
            return (1.0 / 3) * float(vorherige_hj1) + (2.0 / 3) * float(hj2)
        return float(hj2)
    return compute_schuljahr_note(student_name, hj_noten)


# ── Utility ───────────────────────────────────────────────────────────────────

def round_note15(x: float | None) -> int | None:
    """Clamp and round a float note to int 0-15."""
    if x is None:
        return None
    return max(0, min(15, round(x)))


# ── Kurs mode ─────────────────────────────────────────────────────────────────

HJ_ORDER = ["HJ1", "HJ2", "HJ3", "HJ4"]
_GLN_TO_HJ = {
    "GLN1": "HJ1", "GLN2": "HJ1",
    "GLN3": "HJ2", "GLN4": "HJ2",
    "GLN5": "HJ3", "GLN6": "HJ3",
    "GLN7": "HJ4", "GLN8": "HJ4",
}
_HJ_TO_GLN_SLOTS = {
    "HJ1": ("GLN1", "GLN2"),
    "HJ2": ("GLN3", "GLN4"),
    "HJ3": ("GLN5", "GLN6"),
    "HJ4": ("GLN7", "GLN8"),
}
DEFAULT_KURS_GEWICHTUNG = {"hj_gln_pct": 70.0, "hj_mdl_pct": 30.0}


def get_kurs_gewichtung(data: dict) -> dict:
    g = dict(DEFAULT_KURS_GEWICHTUNG)
    g.update(data.get("kurs_gewichtung") or {})
    return g


def gln_slot_to_hj(gln_slot: str) -> str | None:
    return _GLN_TO_HJ.get(gln_slot)


def valid_gln_slots(kurs_typ: str, kurs_stunden: int) -> list[str]:
    """GK with 2 or 3 hours: only 7 GLNs (HJ4 gets only 1 Klausur)."""
    if kurs_typ == "GK" and kurs_stunden in (2, 3):
        return ["GLN1", "GLN2", "GLN3", "GLN4", "GLN5", "GLN6", "GLN7"]
    return ["GLN1", "GLN2", "GLN3", "GLN4", "GLN5", "GLN6", "GLN7", "GLN8"]


def gln_notes_for_hj_kurs(student_name: str, hj: str, lns: list) -> list[float]:
    slots = _HJ_TO_GLN_SLOTS.get(hj, ())
    notes = []
    for ln in lns:
        if ln.get("ln_typ") != "GLN" or ln.get("gln_slot") not in slots:
            continue
        if ln.get("nachtermin_von"):   # skip NT sheets
            continue
        effective = _effective_note(student_name, ln, lns)
        if effective is not None:
            notes.append(effective)
    return notes


def gln_mean_for_hj_kurs(student_name: str, hj: str, lns: list) -> float | None:
    notes = gln_notes_for_hj_kurs(student_name, hj, lns)
    return sum(notes) / len(notes) if notes else None


def compute_hj_vorschlag_kurs(
    student_name: str,
    hj: str,
    lns: list,
    mdl_noten_kurs: dict,
    gewichtung: dict,
) -> float | None:
    gln_mean = gln_mean_for_hj_kurs(student_name, hj, lns)
    kn = mdl_noten_kurs.get(student_name, {})
    mdl1 = kn.get(f"{hj}_mdl1")
    mdl2 = kn.get(f"{hj}_mdl2")
    mdl_vals = [v for v in [mdl1, mdl2] if v is not None]
    mdl_mean = sum(mdl_vals) / len(mdl_vals) if mdl_vals else None
    gln_pct = gewichtung.get("hj_gln_pct", 70.0) / 100.0
    mdl_pct = gewichtung.get("hj_mdl_pct", 30.0) / 100.0
    if gln_mean is not None and mdl_mean is not None:
        return gln_mean * gln_pct + mdl_mean * mdl_pct
    if gln_mean is not None:
        return gln_mean
    return None


def student_active_in_hj(student: dict, target_hj: str) -> bool:
    # Check mid-year enrollment: student is only active from aufnahme_ab_hj onwards
    aufnahme = student.get("aufnahme_ab_hj")
    if aufnahme and aufnahme in HJ_ORDER and target_hj in HJ_ORDER:
        if HJ_ORDER.index(target_hj) < HJ_ORDER.index(aufnahme):
            return False
    # Check mid-year unenrollment: student is only active up to abgang_nach_hj
    if student.get("status") == "Ausgeschieden":
        abgang = student.get("abgang_nach_hj")
        if abgang is None:
            return False
        if target_hj not in HJ_ORDER or abgang not in HJ_ORDER:
            return False
        return HJ_ORDER.index(target_hj) <= HJ_ORDER.index(abgang)
    return True


# ── Abiturprüfung (ABT) ───────────────────────────────────────────────────────

from app.excel.schema import GRADE_SCALE


def compute_abt_vorhersage(punkte_list: list, aufgaben: list) -> int | None:
    """
    Hochrechnung: Punkte bisher / Max bisher → gleicher Prozentsatz auf Gesamtmax → Note.
    Gibt None zurück wenn keine Punkte eingetragen sind.
    """
    max_bisher = 0.0
    punkte_bisher = 0.0
    gesamtmax = sum(float(a.get("max_punkte", 0)) for a in aufgaben)

    for i, aufgabe in enumerate(aufgaben):
        if i >= len(punkte_list):
            continue
        p = punkte_list[i]
        if p is not None:
            max_bisher += float(aufgabe.get("max_punkte", 0))
            punkte_bisher += float(p)

    if max_bisher <= 0 or gesamtmax <= 0:
        return None

    pct = punkte_bisher / max_bisher
    # Convert to note using the grade scale (no rounding / exact thresholds)
    for threshold, note in GRADE_SCALE:
        if pct >= threshold:
            return note
    return 0


def is_abt_grenzfall(punkte_list: list, aufgaben: list) -> tuple[bool, str]:
    """
    Check if the current score is within 1% below a grade boundary.
    Returns (is_grenzfall, next_note_label).
    """
    max_bisher = 0.0
    punkte_bisher = 0.0

    for i, aufgabe in enumerate(aufgaben):
        if i >= len(punkte_list):
            continue
        p = punkte_list[i]
        if p is not None:
            max_bisher += float(aufgabe.get("max_punkte", 0))
            punkte_bisher += float(p)

    if max_bisher <= 0:
        return False, ""

    pct = punkte_bisher / max_bisher
    # Check if within 1% below any threshold
    for threshold, note in GRADE_SCALE:
        if threshold > 0 and pct < threshold and (threshold - pct) < 0.01:
            return True, str(note)

    return False, ""


def compute_abt_hj_schnitt(student_name: str, hj_noten: dict) -> float | None:
    """
    Arithmetic mean of all HJ notes (HJ1-HJ4) for the given student.
    """
    student_noten = hj_noten.get(student_name, {})
    vals = [float(v) for v in student_noten.values() if v is not None]
    return sum(vals) / len(vals) if vals else None


def compute_abt_nachpruefung(abt_note15: int | None, hj_schnitt: float | None) -> bool:
    """
    Returns True if the Abitur grade deviates by >= 4 points from the HJ average.
    """
    if abt_note15 is None or hj_schnitt is None:
        return False
    return abs(float(abt_note15) - hj_schnitt) >= 4.0
