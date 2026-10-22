"""Statistik zu den einzelnen Aufgaben eines Leistungsnachweises.

Gezählt werden alle nicht ignorierten Schüler, für die mindestens eine Punktzahl
eingetragen ist. Ein leeres Aufgabenfeld zählt bei diesen Schülern als 0 Punkte –
genauso wie bei der Gesamtpunktzahl.
"""
from __future__ import annotations

import math
from statistics import mean, median

# Lösungsquote (Ø Punkte / Max) ab der eine Aufgabe als gut bzw. schwach gelöst gilt
QUOTE_GUT = 0.75
QUOTE_SCHWACH = 0.5


def _r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)


def _p(q: float) -> str:
    """Whole percent, rounded half up like the browser (0.725 → "73 %")."""
    return f"{math.floor(q * 100 + 0.5 + 1e-9)} %"


def _korrelation(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; None if one side has no variance or too few values."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def aufgaben_statistik(ln: dict) -> dict:
    """Per-task statistics and a short analysis for one LN.

    Returns {"n": number of students counted, "aufgaben": [...], "analyse": {...}}.
    """
    aufgaben = ln.get("aufgaben", [])
    rows: list[list[float]] = []
    for s in ln.get("schueler", []):
        if s.get("ignoriert"):
            continue
        punkte = list(s.get("punkte") or [])
        if not any(p is not None for p in punkte):
            continue
        punkte += [None] * (len(aufgaben) - len(punkte))
        rows.append([float(p) if p is not None else 0.0 for p in punkte[:len(aufgaben)]])

    totals = [sum(r) for r in rows]
    result = []
    for i, task in enumerate(aufgaben):
        max_p = float(task.get("max_punkte") or 0)
        werte = [r[i] for r in rows]
        entry = {
            "label": task.get("label") or f"Aufgabe {i + 1}",
            "afb": task.get("afb") or "",
            "max": max_p,
            "n": len(werte),
            "mittel": None, "median": None, "min": None, "max_erreicht": None,
            "quote": None, "anteil_voll": None, "anteil_null": None, "trennschaerfe": None,
        }
        if werte:
            entry.update({
                "mittel": _r(mean(werte)),
                "median": _r(median(werte)),
                "min": min(werte),
                "max_erreicht": max(werte),
                "anteil_voll": _r(sum(1 for w in werte if max_p > 0 and w >= max_p) / len(werte), 3),
                "anteil_null": _r(sum(1 for w in werte if w <= 0) / len(werte), 3),
            })
            if max_p > 0:
                entry["quote"] = _r(mean(werte) / max_p, 3)
            # Discrimination: correlation of the task with the rest of the test
            rest = [t - w for t, w in zip(totals, werte)]
            entry["trennschaerfe"] = _r(_korrelation(werte, rest))
        result.append(entry)

    mit_quote = [a for a in result if a["quote"] is not None]
    ranked = sorted(mit_quote, key=lambda a: a["quote"], reverse=True)
    analyse = {
        "beste": ranked[0]["label"] if len(ranked) >= 2 else None,
        "schlechteste": ranked[-1]["label"] if len(ranked) >= 2 else None,
        "gut": [a["label"] for a in ranked if a["quote"] >= QUOTE_GUT],
        "schwach": [a["label"] for a in reversed(ranked) if a["quote"] < QUOTE_SCHWACH],
        "quote_gut": QUOTE_GUT,
        "quote_schwach": QUOTE_SCHWACH,
    }
    gesamt_max = sum(float(t.get("max_punkte") or 0) for t in aufgaben)
    return {
        "n": len(rows),
        "gesamt": {
            "max": gesamt_max,
            "mittel": _r(mean(totals)) if totals else None,
            "median": _r(median(totals)) if totals else None,
            "quote": _r(mean(totals) / gesamt_max, 3) if totals and gesamt_max > 0 else None,
        },
        "aufgaben": result,
        "analyse": analyse,
    }


# ── Anforderungsbereiche ──────────────────────────────────────────────────────

AFB_KEYS = ("I", "II", "III")
QUOTE_AFB1_MIN = 0.75     # AFB I should be solved by most students
QUOTE_AFB3_MAX = 0.5      # AFB III should be solved rarely
AFB3_GELOEST = 0.5        # a student "solved" AFB III with at least this share of its points
AFB12_STARK = 0.8         # strong in AFB I+II: upper third of the class or at least this share


def afb_statistik(ln: dict) -> dict:
    """Statistics per Anforderungsbereich and a plausibility check of the AFB levels.

    AFB III should be solved rarely – and if so, by students who are strong in
    AFB I+II (upper third of the class or at least AFB12_STARK). A student who
    solves AFB III without being strong in AFB I+II hints that AFB III was too
    easy (or the AFB assignment is off).
    """
    aufgaben = ln.get("aufgaben", [])
    idx = {k: [i for i, t in enumerate(aufgaben) if (t.get("afb") or "") == k] for k in AFB_KEYS}
    if not any(idx.values()):
        return {"vorhanden": False}
    maxima = {k: sum(float(aufgaben[i].get("max_punkte") or 0) for i in idx[k]) for k in AFB_KEYS}

    schueler = []
    for s in ln.get("schueler", []):
        if s.get("ignoriert"):
            continue
        punkte = list(s.get("punkte") or [])
        if not any(p is not None for p in punkte):
            continue
        pts = {k: sum(float(punkte[i]) for i in idx[k] if i < len(punkte) and punkte[i] is not None)
               for k in AFB_KEYS}
        schueler.append({"name": s.get("name", ""), "note_15": s.get("note_15"), "punkte": pts})

    bereiche = []
    quoten = {}
    for k in AFB_KEYS:
        if not idx[k]:
            continue
        werte = [s["punkte"][k] for s in schueler]
        q = mean(werte) / maxima[k] if werte and maxima[k] > 0 else None
        quoten[k] = q
        bereiche.append({"afb": k, "aufgaben": [aufgaben[i].get("label") for i in idx[k]],
                         "max": maxima[k], "mittel": _r(mean(werte)) if werte else None, "quote": _r(q, 3)})

    checks = []
    if quoten.get("I") is not None:
        q = quoten["I"]
        checks.append({"ok": q >= QUOTE_AFB1_MIN, "text":
                       f"AFB I wurde zu {_p(q)} gelöst – " +
                       ("wie erwartet häufig." if q >= QUOTE_AFB1_MIN else
                        f"erwartet sind mindestens {_p(QUOTE_AFB1_MIN)}. Grundlagen sitzen nicht oder AFB I war zu schwer.")})
    if quoten.get("III") is not None:
        q = quoten["III"]
        checks.append({"ok": q <= QUOTE_AFB3_MAX, "text":
                       f"AFB III wurde zu {_p(q)} gelöst – " +
                       ("wie erwartet eher selten." if q <= QUOTE_AFB3_MAX else
                        f"erwartet sind höchstens {_p(QUOTE_AFB3_MAX)}. AFB III war möglicherweise zu leicht.")})
    vorh = [k for k in AFB_KEYS if quoten.get(k) is not None]
    if len(vorh) >= 2:
        steigend = [f"AFB {a} ({_p(quoten[a])}) < AFB {b} ({_p(quoten[b])})"
                    for a, b in zip(vorh, vorh[1:]) if quoten[a] < quoten[b]]
        checks.append({"ok": not steigend, "text":
                       "Die Lösungsquote sinkt von AFB zu AFB wie erwartet." if not steigend else
                       "Ungewöhnliche Reihenfolge: " + "; ".join(steigend) + "."})

    afb3 = None
    max12 = maxima["I"] + maxima["II"]
    if idx["III"] and maxima["III"] > 0 and max12 > 0 and schueler:
        for s in schueler:
            s["q12"] = (s["punkte"]["I"] + s["punkte"]["II"]) / max12
            s["q3"] = s["punkte"]["III"] / maxima["III"]
        ranked = sorted((s["q12"] for s in schueler), reverse=True)
        grenze = ranked[max(0, -(-len(ranked) // 3) - 1)]   # upper third (rounded up)
        loeser = [s for s in schueler if s["q3"] >= AFB3_GELOEST]
        stark_ab = min(grenze, AFB12_STARK)
        # compared in whole percent, as displayed
        auffaellig = [s for s in loeser if round(s["q12"], 2) < round(stark_ab, 2)]
        korr = _korrelation([s["q12"] for s in schueler], [s["q3"] for s in schueler])
        if not loeser:
            checks.append({"ok": None, "text":
                           f"Niemand hat AFB III zu mindestens {_p(AFB3_GELOEST)} gelöst."})
        elif not auffaellig:
            checks.append({"ok": True, "text":
                           f"AFB III haben {len(loeser)} Schüler gelöst – alle stark bei AFB I+II."})
        else:
            checks.append({"ok": False, "text":
                           f"AFB III haben {len(loeser)} Schüler gelöst, davon {len(auffaellig)} ohne starke "
                           "Leistung bei AFB I+II. Wer die Anwendung nicht kann, AFB III aber schon, spricht dafür, "
                           "dass AFB III zu leicht war oder Aufgaben falsch zugeordnet sind."})
        if korr is not None and korr < 0.3:
            checks.append({"ok": False, "text":
                           f"AFB III hängt kaum mit AFB I+II zusammen (Korrelation {korr:.2f}). "
                           "Bei passenden Anforderungen lösen vor allem die Stärkeren AFB III."})
        afb3 = {
            "stark_ab": _r(stark_ab, 3),
            "geloest_ab": AFB3_GELOEST,
            "korrelation": _r(korr),
            "schueler": [{"name": s["name"], "note_15": s["note_15"], "q12": _r(s["q12"], 3), "q3": _r(s["q3"], 3),
                          "auffaellig": any(s is a for a in auffaellig)} for s in schueler],
            "auffaellig": [{"name": s["name"], "note_15": s["note_15"], "q12": _r(s["q12"], 3), "q3": _r(s["q3"], 3)}
                           for s in sorted(auffaellig, key=lambda s: s["q12"])],
        }

    ohne = [t.get("label") for t in aufgaben if (t.get("afb") or "") not in AFB_KEYS]
    return {"vorhanden": True, "bereiche": bereiche, "checks": checks, "afb3": afb3, "ohne_afb": ohne}
