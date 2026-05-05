"""Grade computation helpers for SL-, HJ- and Schuljahr-notes."""
from __future__ import annotations

DEFAULT_GEWICHTUNG: dict = {
    "sl_mdl_pct": 70.0,   # % weight of mündliche note in SL note
    "sl_kln_pct": 30.0,   # % weight of KLN mean in SL note
    "hj_gln_w":   1.0,    # relative weight of GLN mean in HJ note
    "hj_sl1_w":   1.0,    # relative weight of SL1/3 in HJ note
    "hj_sl2_w":   1.0,    # relative weight of SL2/4 in HJ note
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

def compute_hj_vorschlag(
    student_name: str,
    hj: str,
    lns: list,
    mdl_noten: dict,
    gewichtung: dict,
    kln_weights: dict | None = None,
    gln_weights: dict | None = None,
) -> float | None:
    """Compute suggested HJ note (float, 0-15 scale) – unrounded.

    Each GLN counts individually with its own weight (default 1.0).
    SL notes count with hj_sl1_w / hj_sl2_w from gewichtung.
    """
    sl1_key, sl2_key = ("SL1", "SL2") if hj == "HJ1" else ("SL3", "SL4")

    components: list[tuple[float, float]] = []

    # Individual GLN components (each with its own weight)
    for ln in lns:
        if ln.get("ln_typ") != "GLN" or ln.get("hj") != hj:
            continue
        if ln.get("nachtermin_von"):
            continue
        effective = _effective_note(student_name, ln, lns)
        if effective is not None:
            w = float((gln_weights or {}).get(ln["sheet_name"], 1.0))
            components.append((effective, w))

    sl1_note = compute_sl_note(student_name, sl1_key, lns, mdl_noten, gewichtung, kln_weights)
    sl2_note = compute_sl_note(student_name, sl2_key, lns, mdl_noten, gewichtung, kln_weights)

    if sl1_note is not None:
        components.append((sl1_note, float(gewichtung.get("hj_sl1_w", 1.0))))
    if sl2_note is not None:
        components.append((sl2_note, float(gewichtung.get("hj_sl2_w", 1.0))))

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
        return round(gln_mean * gln_pct + mdl_mean * mdl_pct, 1)
    if gln_mean is not None:
        return round(gln_mean, 1)
    return None


def student_active_in_hj(student: dict, target_hj: str) -> bool:
    if student.get("status") == "Ausgeschieden":
        abgang = student.get("abgang_nach_hj")
        if abgang is None:
            return False
        if target_hj not in HJ_ORDER or abgang not in HJ_ORDER:
            return False
        return HJ_ORDER.index(target_hj) <= HJ_ORDER.index(abgang)
    return True
