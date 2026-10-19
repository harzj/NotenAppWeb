"""Gewichtungs-Modell für die UI (Seite „Notenberechnung“ und Gewichtungs-Modals).

Baut aus einer Klasse eine übersichtliche Struktur aller Gewichte mit den daraus
resultierenden Prozentanteilen und übernimmt geänderte Gewichte (nur mergen,
nie ganze Dicts ersetzen).
"""
from __future__ import annotations

from app.grades import berechnung as B

# Global (per class) weight keys that can be edited in the UI
GW_KEYS = ("sl_mdl_pct", "sl_kln_pct", "sl_mittel_w", "sj_hj1_w", "sj_hj2_w")
LN_STORES = {
    "kln_weights": ("KLN", B.SL_KEYS),
    "mdl_weights": (B.LN_TYP_MDL, B.SL_KEYS),
    "gln_weights": ("GLN", ("HJ1", "HJ2")),
}
MAX_WEIGHT = 1000.0


def _pct(part: float, total: float) -> float | None:
    return round(100.0 * part / total, 1) if total > 0 else None


def _fmt_w(w: float) -> str:
    return f"{w:g}".replace(".", ",")


def _items(lns: list, weights: dict) -> list[dict]:
    total = sum(weights.get(ln["sheet_name"], 1.0) for ln in lns)
    return [{
        "sheet": ln["sheet_name"],
        "name": ln["name"],
        "w": weights.get(ln["sheet_name"], 1.0),
        "pct": _pct(weights.get(ln["sheet_name"], 1.0), total),
    } for ln in lns]


def _uniform(items: list[dict]) -> bool:
    return len({it["w"] for it in items}) <= 1


def build_model(data: dict) -> dict:
    """Return all weights of the class, grouped as the grade is computed."""
    lns = data.get("leistungsnachweise", [])
    gw = B.get_gewichtung(data)

    def _kln(sl):
        return [ln for ln in lns if ln.get("ln_typ") == "KLN"
                and ln.get("sl_zuordnung") == sl and not ln.get("nachtermin_von")]

    def _gln(hj):
        return [ln for ln in lns if ln.get("ln_typ") == "GLN"
                and ln.get("hj") == hj and not ln.get("nachtermin_von")]

    mf, kf = float(gw["sl_mdl_pct"]), float(gw["sl_kln_pct"])
    sl = {}
    for sl_key in B.SL_KEYS:
        kln = _items(_kln(sl_key), B.get_kln_weights(data, sl_key))
        mdl = _items(B.mdl_lns_for_sl(lns, sl_key), B.get_mdl_weights(data, sl_key))
        parts = [f"{_pct(mf, mf + kf) or 0:g} % mündl. + {_pct(kf, mf + kf) or 0:g} % KLN-Mittel"]
        if len(kln) >= 2 and not _uniform(kln):
            parts.append("KLN: " + ", ".join(f"{it['name']} ×{_fmt_w(it['w'])}" for it in kln))
        if mdl:
            detail = "" if _uniform(mdl) else " (" + ", ".join(
                f"{it['name']} ×{_fmt_w(it['w'])}" for it in mdl) + ")"
            parts.append(f"mündl. aus {len(mdl)} Teilnote{'n' if len(mdl) != 1 else ''}{detail}")
        sl[sl_key] = {"kln": kln, "mdl": mdl, "formel": " · ".join(parts)}

    hj = {}
    slm_w = float(gw["sl_mittel_w"])
    for hj_key, (sa, sb) in B.HJ_SL_KEYS.items():
        glns = _items(_gln(hj_key), B.get_gln_weights(data, hj_key))
        total = sum(it["w"] for it in glns) + slm_w
        for it in glns:
            it["pct_hj"] = _pct(it["w"], total)
        if glns:
            gln_txt = ", ".join(f"{it['name']} {it['pct_hj']:g} %" for it in glns)
            formel = f"{gln_txt} + SL-Mittel ({sa}/{sb}) {_pct(slm_w, total):g} %"
        else:
            formel = f"nur SL-Mittel ({sa}/{sb}) – noch keine GLN angelegt"
        hj[hj_key] = {"gln": glns, "sl_mittel_pct": _pct(slm_w, total),
                      "sl_keys": (sa, sb), "formel": formel}

    w1, w2 = float(gw["sj_hj1_w"]), float(gw["sj_hj2_w"])
    sj = {"formel": f"{_pct(w1, w1 + w2) or 0:g} % HJ1 + {_pct(w2, w1 + w2) or 0:g} % HJ2",
          "hj1_pct": _pct(w1, w1 + w2), "hj2_pct": _pct(w2, w1 + w2)}

    return {"gw": {k: gw[k] for k in GW_KEYS}, "sl": sl, "hj": hj, "sj": sj}


def _to_weight(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"Ungültige Zahl: {v!r}")
    if f < 0 or f > MAX_WEIGHT:
        raise ValueError(f"Gewicht muss zwischen 0 und {MAX_WEIGHT:g} liegen: {v!r}")
    return f


def apply_payload(data: dict, payload: dict) -> None:
    """Merge weights from *payload* into the class dict. Raises ValueError on bad input.

    payload = {"gewichtung": {key: value},
               "kln_weights": {"SL1": {sheet: w}}, "mdl_weights": {...}, "gln_weights": {"HJ1": {...}}}
    """
    new_gw = {}
    for key, val in (payload.get("gewichtung") or {}).items():
        if key not in GW_KEYS:
            raise ValueError(f"Unbekannte Gewichtung: {key}")
        w = _to_weight(val)
        if w is not None:
            new_gw[key] = w
    merged = {**B.get_gewichtung(data), **new_gw}
    if float(merged["sl_mdl_pct"]) + float(merged["sl_kln_pct"]) <= 0:
        raise ValueError("Mündlich und KLN dürfen nicht beide 0 sein.")
    if float(merged["sj_hj1_w"]) + float(merged["sj_hj2_w"]) <= 0:
        raise ValueError("HJ1 und HJ2 dürfen nicht beide 0 sein.")

    lns = data.get("leistungsnachweise", [])
    new_ln: dict = {}
    for store, (typ, slots) in LN_STORES.items():
        for slot, weights in (payload.get(store) or {}).items():
            if slot not in slots:
                raise ValueError(f"Ungültige Zuordnung: {slot}")
            slot_field = "hj" if typ == "GLN" else "sl_zuordnung"
            valid = {ln["sheet_name"] for ln in lns
                     if ln.get("ln_typ") == typ and ln.get(slot_field) == slot}
            for sheet, val in (weights or {}).items():
                if sheet not in valid:
                    raise ValueError(f"Unbekannter Leistungsnachweis: {sheet}")
                w = _to_weight(val)
                if w is not None:
                    new_ln.setdefault(store, {}).setdefault(slot, {})[sheet] = w

    # Validation passed → merge
    data.setdefault("sl_gewichtung", {}).update(new_gw)
    for store, slots in new_ln.items():
        target = data.setdefault(store, {})
        for slot, weights in slots.items():
            target.setdefault(slot, {}).update(weights)
