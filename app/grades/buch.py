"""Import aus dem informatik.book (Prüfmodus des Lernbuchs und von ProgVenture).

Das Buch exportiert je Klasse eine CSV (Semikolon, UTF-8 mit BOM) im Format ``informatik.book/1``: eine Zeile
je Schüler, Test und Aufgabe mit Punkten, aber ohne Noten – die rechnet die NotenApp nach ihren Regeln.

Schüler stehen im Buch nur mit ihrem OSS-Namen (meist ``vorname.nachname``, ggf. ``_1`` o. ä., manchmal
vertippt). Die Zuordnung zu den Stammdaten wird einmal von Hand geprüft und dann in der Notendatei gespeichert
(``data["buch_zuordnung"]``: Buch-Schüler-ID → "Nachname, Vorname" bzw. "" = nicht zuordnen), ebenso welche
Tests schon importiert sind (``data["buch_importiert"]``: Test-ID → Blattname des Leistungsnachweises).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from difflib import SequenceMatcher

FORMAT = "informatik.book/1"
PFLICHT_SPALTEN = ("format", "test_id", "test", "schueler_id", "oss_name", "status",
                   "aufgabe_nr", "aufgabe", "max", "punkte")

# Ab dieser Ähnlichkeit wird ein Vorschlag gemacht. „Erkannt“ (statt Vorschlag) nur bei exaktem Treffer
# (SICHER) und wenn kein anderer Stammdaten-Name fast genauso gut passt (ABSTAND).
SCHWELLE = 0.6
SICHER = 1.0
ABSTAND = 0.08


class BuchParseError(Exception):
    pass


# ── CSV einlesen ──────────────────────────────────────────────────────────────

def _dekodieren(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise BuchParseError("Datei konnte nicht gelesen werden.")


def _zahl(text: str):
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_buch_csv(raw: bytes) -> dict:
    """Liest den Export des Buchs.

    Rückgabe::

        {"klasse": str,
         "schueler": {sid: oss_name},                       # in Reihenfolge der Datei
         "tests": [{"key", "titel", "anwendung", "datum",
                    "aufgaben": [{"nr", "titel", "max"}],
                    "ergebnisse": {sid: {"punkte": {nr: float|None}, "offen": [nr]}}}]}
    """
    text = _dekodieren(raw)
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    spalten = [s.strip() for s in (reader.fieldnames or [])]
    fehlend = [s for s in PFLICHT_SPALTEN if s not in spalten]
    if fehlend:
        raise BuchParseError(
            "Keine Exportdatei des informatik.book (es fehlen Spalten: " + ", ".join(fehlend) + ")."
        )

    klasse = ""
    schueler: dict = {}
    tests: dict = {}
    for zeile in reader:
        zeile = {(k or "").strip(): (v or "").strip() for k, v in zeile.items()}
        if not zeile.get("test_id"):
            continue
        if zeile.get("format") != FORMAT:
            raise BuchParseError(f"Unbekanntes Exportformat „{zeile.get('format')}“ (erwartet {FORMAT}).")
        klasse = klasse or zeile.get("klasse", "")
        sid = zeile["schueler_id"]
        if not sid:
            continue
        schueler.setdefault(sid, zeile["oss_name"])
        test = tests.setdefault(zeile["test_id"], {
            "key": zeile["test_id"], "titel": zeile["test"], "anwendung": zeile.get("anwendung", ""),
            "datum": zeile.get("datum", ""), "aufgaben": {}, "ergebnisse": {},
        })
        if zeile["status"] != "abgegeben" or not zeile["aufgabe_nr"]:
            continue
        try:
            nr = int(zeile["aufgabe_nr"])
        except ValueError:
            raise BuchParseError(f"Ungültige Aufgabennummer „{zeile['aufgabe_nr']}“.")
        test["aufgaben"].setdefault(nr, {"nr": nr, "titel": zeile["aufgabe"] or f"Aufgabe {nr}",
                                         "max": _zahl(zeile["max"]) or 0.0})
        erg = test["ergebnisse"].setdefault(sid, {"punkte": {}, "offen": []})
        erg["punkte"][nr] = _zahl(zeile["punkte"])
        if zeile.get("offen") == "1":
            erg["offen"].append(nr)

    if not tests:
        raise BuchParseError("Die Datei enthält keine Leistungsnachweise.")
    liste = []
    for t in tests.values():
        t["aufgaben"] = [t["aufgaben"][nr] for nr in sorted(t["aufgaben"])]
        liste.append(t)
    liste.sort(key=lambda t: (t["datum"], t["key"]))
    return {"klasse": klasse, "schueler": schueler, "tests": liste}


# ── Namen zuordnen ────────────────────────────────────────────────────────────

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _woerter(text: str) -> list[str]:
    """'Anna-Lena Müller' → ['anna', 'lena', 'mueller']; Ziffern und Trenner fallen weg."""
    text = (text or "").lower().translate(_UMLAUTE)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return [w for w in re.split(r"[^a-z]+", text) if w]


def _aehnlich(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def name_score(oss_name: str, nachname: str, vorname: str) -> float:
    """Ähnlichkeit 0–1 zwischen OSS-Name (vorname.nachname_1) und Stammdaten-Namen."""
    oss = _woerter(oss_name)
    vn, nn = _woerter(vorname), _woerter(nachname)
    if not oss or not (vn or nn):
        return 0.0
    o = "".join(oss)
    besten = max(_aehnlich(o, "".join(vn + nn)), _aehnlich(o, "".join(nn + vn)))
    if len(oss) == 1 and nn:
        # nur ein Wort, z. B. 'mueller' oder 'amueller' – mit dem Nachnamen allein etwas weniger sicher
        besten = max(besten, 0.9 * _aehnlich(o, "".join(nn)))
    if len(oss) >= 2 and nn and vn:
        # Initiale statt Vorname: 'a.mueller'
        if len(oss[0]) == 1 and oss[0] == vn[0][0]:
            besten = max(besten, 0.9 * _aehnlich("".join(oss[1:]), "".join(nn)))
    return round(besten, 3)


def zuordnen(schueler: dict, namen: list[str], gespeichert: dict) -> dict:
    """Vorschlag je Buch-Schüler.

    schueler:    {sid: oss_name}
    namen:       ["Nachname, Vorname", ...] aus den Stammdaten
    gespeichert: {sid: "Nachname, Vorname" | ""} – früher geprüfte Zuordnung

    Rückgabe {sid: {"name": str ("" = keine), "art": "gespeichert"|"sicher"|"vorschlag"|"keine", "score": float}}.
    Jeder Stammdaten-Name wird höchstens einmal vergeben; gespeicherte Zuordnungen gehen vor.
    """
    ergebnis: dict = {}
    vergeben: set = set()
    for sid in schueler:
        if sid in gespeichert and (gespeichert[sid] == "" or gespeichert[sid] in namen):
            ergebnis[sid] = {"name": gespeichert[sid], "art": "gespeichert", "score": 1.0}
            if gespeichert[sid]:
                vergeben.add(gespeichert[sid])

    paare = []
    zweitbester: dict = {}
    for sid, oss in schueler.items():
        if sid in ergebnis:
            continue
        scores = []
        for name in namen:
            if name in vergeben:
                continue
            nachname, _, vorname = name.partition(", ")
            score = name_score(oss, nachname, vorname)
            scores.append(score)
            if score >= SCHWELLE:
                paare.append((score, sid, name))
        scores.sort(reverse=True)
        zweitbester[sid] = scores[1] if len(scores) > 1 else 0.0
    # Beste Paare zuerst – so bekommt bei zwei ähnlichen OSS-Namen der passendere den Schüler
    for score, sid, name in sorted(paare, key=lambda p: -p[0]):
        if sid in ergebnis or name in vergeben:
            continue
        eindeutig = score >= SICHER and score - zweitbester[sid] >= ABSTAND
        ergebnis[sid] = {"name": name, "art": "sicher" if eindeutig else "vorschlag", "score": score}
        vergeben.add(name)
    for sid in schueler:
        ergebnis.setdefault(sid, {"name": "", "art": "keine", "score": 0.0})
    return ergebnis


# ── Leistungsnachweis-Vorgaben ───────────────────────────────────────────────

def vorschlag_einordnung(datum: str) -> dict:
    """Typ/Halbjahr/SL aus dem Datum raten (wird auf der Prüfseite angezeigt und ist änderbar).
    Aug–Okt → SL1, Nov–Jan → SL2, Feb–Apr → SL3, Mai–Jul → SL4."""
    try:
        monat = int(datum[5:7])
    except (TypeError, ValueError):
        monat = 9
    sl = {8: "SL1", 9: "SL1", 10: "SL1", 11: "SL2", 12: "SL2", 1: "SL2",
          2: "SL3", 3: "SL3", 4: "SL3"}.get(monat, "SL4")
    hj = "HJ1" if sl in ("SL1", "SL2") else "HJ2"
    return {"ln_typ": "KLN", "hj": hj, "sl_zuordnung": sl}
