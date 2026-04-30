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


# ── KLN / GLN note extraction ─────────────────────────────────────────────────

def kln_notes_for_sl(student_name: str, sl_key: str, lns: list) -> list[float]:
    """Return list of non-ignored KLN note_15 values for student + SL slot."""
    notes = []
    for ln in lns:
        if ln.get("ln_typ") != "KLN" or ln.get("sl_zuordnung") != sl_key:
            continue
        for s in ln.get("schueler", []):
            if s["name"] == student_name:
                if not s.get("ignoriert") and s.get("note_15") is not None:
                    notes.append(float(s["note_15"]))
                break
    return notes


def kln_mean_for_sl(student_name: str, sl_key: str, lns: list) -> float | None:
    notes = kln_notes_for_sl(student_name, sl_key, lns)
    return sum(notes) / len(notes) if notes else None


def gln_notes_for_hj(student_name: str, hj: str, lns: list) -> list[float]:
    """Return list of non-ignored GLN note_15 values for student + HJ."""
    notes = []
    for ln in lns:
        if ln.get("ln_typ") != "GLN" or ln.get("hj") != hj:
            continue
        for s in ln.get("schueler", []):
            if s["name"] == student_name:
                if not s.get("ignoriert") and s.get("note_15") is not None:
                    notes.append(float(s["note_15"]))
                break
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
) -> float | None:
    """Compute SL note (float, 0-15 scale) – unrounded."""
    kln_mean = kln_mean_for_sl(student_name, sl_key, lns)
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
) -> float | None:
    """Compute suggested HJ note (float, 0-15 scale) – unrounded."""
    sl1_key, sl2_key = ("SL1", "SL2") if hj == "HJ1" else ("SL3", "SL4")

    gln_mean = gln_mean_for_hj(student_name, hj, lns)
    sl1_note = compute_sl_note(student_name, sl1_key, lns, mdl_noten, gewichtung)
    sl2_note = compute_sl_note(student_name, sl2_key, lns, mdl_noten, gewichtung)

    components: list[tuple[float, float]] = []
    if gln_mean is not None:
        components.append((gln_mean, float(gewichtung.get("hj_gln_w", 1.0))))
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
