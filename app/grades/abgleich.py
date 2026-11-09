"""Abgleich zweier Notendateien derselben Klasse (z. B. wenn versehentlich mit zwei Kopien gearbeitet wurde).

``vergleiche(alt, neu)`` stellt den offenen Stand (alt) und eine importierte Datei (neu) gegenüber:

* Was nur in der importierten Datei steht (neue Schüler, Leistungsnachweise, Noten, Einstellungen), wird
  automatisch übernommen (``auto``).
* Was in beiden steht, aber verschieden ist, wird als ``konflikt`` gemeldet – die Lehrkraft entscheidet je
  Eintrag oder gruppenweise, welcher Wert gilt.

``anwenden(alt, neu, wahl)`` erzeugt daraus den neuen Stand: alle ``auto``-Änderungen plus die Konflikte, für die
``wahl[id] == "neu"`` ist. Die IDs sind stabil (aus Art und Schlüsseln gebildet), damit die Auswahl auch dann
noch passt, wenn der Vergleich beim Übernehmen neu gerechnet wird.

Werte, die nur im offenen Stand stehen, bleiben immer erhalten – der Abgleich löscht nichts.
"""
from __future__ import annotations

import copy
import re

# Noten je Schüler: {name: {schluessel: note}} bzw. {name: note}
NOTEN_STORES = {
    "mdl_noten": "Mündliche Note",
    "sl_noten_actual": "SL-Note",
    "hj_noten": "Halbjahresnote",
    "schuljahr_noten_actual": "Jahresnote",
    "mdl_noten_kurs": "Mündliche Note (Kurs)",
    "verhalten_noten": "Verhalten",
    "mitarbeit_noten": "Mitarbeit",
    "vorherige_noten": "Vorherige Note",
}
# Einstellungen, die als Ganzes verglichen werden
EINSTELLUNGEN = {
    "sl_gewichtung": "Gewichtung SL/HJ",
    "kln_weights": "Gewichte der KLN",
    "mdl_weights": "Gewichte der mündlichen Teilnoten",
    "gln_weights": "Gewichte der GLN",
    "kurs_gewichtung": "Gewichtung Kurs",
    "kurs_typ": "Kurstyp",
    "kurs_stunden": "Wochenstunden",
}
STUDENT_FELDER = ("status", "austritt", "abgang_nach_hj", "aufnahme_ab_hj", "aufnahme_vorherige_noten")
LN_META = ("ln_typ", "hj", "sl_zuordnung", "gln_slot", "nachtermin_von", "noten_runden")
ZEILE_FELDER = ("punkte", "note_15", "note_6", "ignoriert", "kuerzel")


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _leer(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _gleich(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return round(float(a), 4) == round(float(b), 4)
        except (TypeError, ValueError):
            return a == b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_gleich(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        keys = {k for k in set(a) | set(b) if not (_leer(a.get(k)) and _leer(b.get(k)))}
        return all(_gleich(a.get(k), b.get(k)) for k in keys)
    if _leer(a) and _leer(b):
        return True
    return a == b


def _zahl(p) -> str:
    if p is None:
        return "–"
    if isinstance(p, float) and p == int(p):
        p = int(p)
    return str(p).replace(".", ",")


def _note_text(v) -> str:
    return "–" if v is None else f"{int(v):02d}" if isinstance(v, (int, float)) else str(v)


def _zeile_leer(z: dict | None) -> bool:
    if not z:
        return True
    return (all(p is None for p in (z.get("punkte") or [])) and z.get("note_15") is None
            and not z.get("ignoriert") and not z.get("kuerzel"))


def _zeile_text(z: dict | None) -> str:
    if _zeile_leer(z):
        return "–"
    if z.get("ignoriert"):
        return "nicht gewertet"
    teile = []
    punkte = z.get("punkte") or []
    if any(p is not None for p in punkte):
        teile.append(" / ".join(_zahl(p) for p in punkte))
    if z.get("kuerzel"):
        teile.append(str(z["kuerzel"]))
    if z.get("note_15") is not None:
        teile.append(f"→ {_note_text(z['note_15'])} NP")
    return " ".join(teile)


def _schueler_name(s: dict) -> str:
    return f"{s.get('nachname', '')}, {s.get('vorname', '')}"


def _aufgaben_signatur(ln: dict) -> list:
    return [(str(a.get("label", "")), a.get("max_punkte")) for a in ln.get("aufgaben", [])]


def klassen_schluessel(book: dict) -> str:
    """Zum Zuordnen der Klassen zweier Sammlungen: Klassenname ohne Leerzeichen, klein."""
    return re.sub(r"\s+", "", str(book.get("klasse", ""))).lower()


def _item(art, keys, gruppe, gruppe_label, schueler, alt_text, neu_text, **extra) -> dict:
    return {"id": "|".join([art, *map(str, keys)]), "art": art, "keys": list(keys), "gruppe": gruppe,
            "gruppe_label": gruppe_label, "schueler": schueler, "alt": alt_text, "neu": neu_text, **extra}


# ── Vergleich ─────────────────────────────────────────────────────────────────

def vergleiche(alt: dict, neu: dict) -> dict:
    """{"auto": [eintrag], "konflikte": [eintrag]} – siehe Moduldoku."""
    auto: list = []
    konflikte: list = []

    # Stammdaten
    alt_sd = {_schueler_name(s): s for s in alt.get("stammdaten", [])}
    for s in neu.get("stammdaten", []):
        name = _schueler_name(s)
        if name not in alt_sd:
            auto.append(_item("schueler", [name], "stammdaten", "Stammdaten", name, "–", "neu in der Klasse"))
            continue
        a = alt_sd[name]
        abw = [f for f in STUDENT_FELDER if not _gleich(a.get(f), s.get(f))]
        if not abw:
            continue
        fehlt_nur = all(_leer(a.get(f)) for f in abw)
        text = lambda d: ", ".join(f"{f}: {d.get(f) if not _leer(d.get(f)) else '–'}" for f in abw)  # noqa: E731
        (auto if fehlt_nur else konflikte).append(
            _item("schueler_felder", [name], "stammdaten", "Stammdaten", name, text(a), text(s)))

    # Leistungsnachweise
    alt_ln = {ln["sheet_name"]: ln for ln in alt.get("leistungsnachweise", [])}
    for ln in neu.get("leistungsnachweise", []):
        sheet = ln["sheet_name"]
        gruppe = "ln|" + sheet
        label = f"Leistungsnachweis „{ln.get('name', sheet)}“"
        if sheet not in alt_ln:
            n = sum(1 for z in ln.get("schueler", []) if not _zeile_leer(z))
            auto.append(_item("ln", [sheet], gruppe, label, "", "–", f"neu ({n} Einträge)"))
            continue
        a = alt_ln[sheet]
        meta_abw = [f for f in LN_META if not _gleich(a.get(f), ln.get(f))]
        if _aufgaben_signatur(a) != _aufgaben_signatur(ln) or meta_abw:
            def beschreibung(x):
                aufg = ", ".join(f"{lbl} ({_zahl(m)} P)" for lbl, m in _aufgaben_signatur(x)) or "keine Aufgaben"
                meta = "; ".join(f"{f}: {x.get(f)}" for f in meta_abw)
                return aufg + (f" – {meta}" if meta else "")
            konflikte.append(_item("ln_ganz", [sheet], gruppe, label, "(ganzer Leistungsnachweis)",
                                   beschreibung(a), beschreibung(ln)))
            continue
        alt_zeilen = {z.get("name"): z for z in a.get("schueler", [])}
        for z in ln.get("schueler", []):
            name = z.get("name")
            az = alt_zeilen.get(name)
            if _zeile_leer(z) or all(_gleich((az or {}).get(f), z.get(f)) for f in ZEILE_FELDER):
                continue
            eintrag = _item("ln_zeile", [sheet, name], gruppe, label, name, _zeile_text(az), _zeile_text(z))
            (auto if _zeile_leer(az) else konflikte).append(eintrag)

    # Noten je Schüler
    for store, titel in NOTEN_STORES.items():
        a_store, n_store = alt.get(store) or {}, neu.get(store) or {}
        for name, n_val in n_store.items():
            a_val = a_store.get(name)
            if isinstance(n_val, dict):
                for key, nv in n_val.items():
                    av = (a_val or {}).get(key) if isinstance(a_val, dict) else None
                    if nv is None or _gleich(av, nv):
                        continue
                    eintrag = _item("note", [store, name, key], f"{store}|{key}", f"{titel} {key}", name,
                                    _note_text(av), _note_text(nv))
                    (auto if av is None else konflikte).append(eintrag)
            else:
                if n_val is None or _gleich(a_val, n_val):
                    continue
                eintrag = _item("note", [store, name, ""], store, titel, name, _note_text(a_val), _note_text(n_val))
                (auto if a_val is None else konflikte).append(eintrag)

    # Einstellungen
    for key, titel in EINSTELLUNGEN.items():
        a_val, n_val = alt.get(key), neu.get(key)
        if _leer(n_val) or _gleich(a_val, n_val):
            continue
        eintrag = _item("einstellung", [key], "einstellungen", "Einstellungen", titel,
                        "–" if _leer(a_val) else str(a_val), str(n_val))
        (auto if _leer(a_val) else konflikte).append(eintrag)

    # informatik.book-Zuordnung: fehlende Einträge still ergänzen (kein Konflikt – der offene Stand gilt)
    for key in ("buch_zuordnung", "buch_oss_namen", "buch_importiert"):
        fehlend = [k for k in (neu.get(key) or {}) if k not in (alt.get(key) or {})]
        if fehlend:
            auto.append(_item("buch", [key], "einstellungen", "Einstellungen", "informatik.book-Import",
                              "–", f"{len(fehlend)} Einträge"))
    return {"auto": auto, "konflikte": konflikte}


# ── Übernehmen ────────────────────────────────────────────────────────────────

def anwenden(alt: dict, neu: dict, wahl: dict) -> tuple[dict, dict]:
    """Neuer Stand aus alt + allen automatischen Übernahmen + Konflikten mit wahl[id] == "neu".
    Rückgabe (daten, zaehler) mit zaehler = {"auto": n, "neu": n, "alt": n}."""
    ergebnis = vergleiche(alt, neu)
    daten = copy.deepcopy(alt)
    neu = copy.deepcopy(neu)
    zaehler = {"auto": 0, "neu": 0, "alt": 0}
    for eintrag in ergebnis["auto"]:
        _uebernehmen(daten, neu, eintrag)
        zaehler["auto"] += 1
    for eintrag in ergebnis["konflikte"]:
        if wahl.get(eintrag["id"]) == "neu":
            _uebernehmen(daten, neu, eintrag)
            zaehler["neu"] += 1
        else:
            zaehler["alt"] += 1
    return daten, zaehler


def _uebernehmen(daten: dict, neu: dict, eintrag: dict) -> None:
    art, keys = eintrag["art"], eintrag["keys"]
    if art in ("schueler", "schueler_felder"):
        (name,) = keys
        quelle = next(s for s in neu["stammdaten"] if _schueler_name(s) == name)
        sd = daten.setdefault("stammdaten", [])
        for i, s in enumerate(sd):
            if _schueler_name(s) == name:
                sd[i] = quelle
                break
        else:
            sd.append(quelle)
    elif art in ("ln", "ln_ganz"):
        (sheet,) = keys
        quelle = next(ln for ln in neu["leistungsnachweise"] if ln["sheet_name"] == sheet)
        lns = daten.setdefault("leistungsnachweise", [])
        for i, ln in enumerate(lns):
            if ln["sheet_name"] == sheet:
                lns[i] = quelle
                break
        else:
            lns.append(quelle)
    elif art == "ln_zeile":
        sheet, name = keys
        quelle = next(z for ln in neu["leistungsnachweise"] if ln["sheet_name"] == sheet
                      for z in ln.get("schueler", []) if z.get("name") == name)
        ziel = next(ln for ln in daten["leistungsnachweise"] if ln["sheet_name"] == sheet)
        for i, z in enumerate(ziel.setdefault("schueler", [])):
            if z.get("name") == name:
                ziel["schueler"][i] = quelle
                break
        else:
            ziel["schueler"].append(quelle)
    elif art == "note":
        store, name, key = keys
        wert = neu[store][name]
        if key:
            ziel = daten.setdefault(store, {}).setdefault(name, {})
            if not isinstance(ziel, dict):
                ziel = daten[store][name] = {}
            ziel[key] = wert[key]
        else:
            daten.setdefault(store, {})[name] = wert
    elif art == "einstellung":
        (key,) = keys
        daten[key] = neu[key]
    elif art == "buch":
        (key,) = keys
        ziel = daten.setdefault(key, {}) or {}
        for k, v in (neu.get(key) or {}).items():
            ziel.setdefault(k, v)
        daten[key] = ziel


# ── Darstellung ───────────────────────────────────────────────────────────────

def gruppiert(eintraege: list) -> list[dict]:
    """Einträge nach Gruppe zusammengefasst (Reihenfolge des ersten Auftretens)."""
    gruppen: dict = {}
    for e in eintraege:
        g = gruppen.setdefault(e["gruppe"], {"gruppe": e["gruppe"], "label": e["gruppe_label"], "eintraege": []})
        g["eintraege"].append(e)
    return list(gruppen.values())
