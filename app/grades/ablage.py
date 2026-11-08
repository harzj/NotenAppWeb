"""Server-Ablage: Admins speichern ihre Sammlung verschlüsselt auf dem Notfallserver.

Nur auf dem selbst betriebenen Notfallserver aus dem Quellcode (deploy/, Dienst mit
Auto-Update) und nur, wenn dort NOTENAPP_SERVER_ABLAGE=1 gesetzt ist. Beim Landkreis und
in den exe-Builds ist die Ablage immer aus – dort dürfen keine Schülerdaten liegen bleiben.

Gespeichert wird dieselbe Datei wie beim Download: ein Zip mit einer Excel-Datei je
Klasse, jede mit dem Datei-Passwort verschlüsselt. Ablage:
    <Datenordner>/ablage/user_<id>/sammlung_<JJJJMMTT-HHMMSS>.zip
Jede Speicherung ist eine neue Version; alte werden nach festen Regeln aufgeräumt.

Automatisches Speichern: Nach jedem Request wird geprüft, ob sich die offenen Klassen
seit der letzten Speicherung geändert haben. Wenn ja, schreibt ein Hintergrund-Timer
nach VERZOEGERUNG Sekunden den dann aktuellen Stand – auch wenn danach keine Anfrage
mehr kommt. Aktiv ist das, sobald in der Sitzung ein Ablage-Passwort bekannt ist
(nach dem Öffnen aus der Ablage oder dem ersten Speichern).
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import io
import json
import logging
import os
import pickle
import threading
import zipfile

from flask import current_app, request, session
from flask_login import current_user

from app import paths

log = logging.getLogger(__name__)

PW_KEY = "_ablage_pw"             # Datei-Passwort der Ablage in der (serverseitigen) Sitzung
VERZOEGERUNG = 30.0               # Sekunden zwischen Änderung und automatischem Speichern
BEHALTEN = 30                     # neueste Versionen immer behalten …
TAGE = 60                         # … plus die neueste je Tag der letzten TAGE Tage
PRAEFIX = "sammlung_"

_lock = threading.Lock()          # schützt _pending/_timers/_gespeichert
_schreib_lock = threading.Lock()  # nur eine Speicherung gleichzeitig
_pending: dict[int, tuple[list, str, str]] = {}
_timers: dict[int, threading.Timer] = {}
_gespeichert: dict[int, str] = {}  # user_id -> Prüfsumme des zuletzt gespeicherten Stands


# ── Freischaltung ─────────────────────────────────────────────────────────────

def aktiviert(app=None) -> bool:
    """Ablage auf diesem Server eingeschaltet? (Notfallserver aus Quellcode + Schalter)"""
    app = app or current_app
    return (bool(app.config.get("SERVER_ABLAGE"))
            and not paths.is_frozen()
            and paths.is_notfall_server())


def verfuegbar() -> bool:
    """Für den angemeldeten Benutzer nutzbar (nur Admins)."""
    return (aktiviert() and current_user.is_authenticated
            and bool(getattr(current_user, "is_admin", False)))


# ── Dateien ───────────────────────────────────────────────────────────────────

def ordner(user_id: int) -> str:
    return os.path.join(paths.data_dir(), "ablage", f"user_{int(user_id)}")


def versionen(user_id: int) -> list[dict]:
    """Gespeicherte Versionen, neueste zuerst."""
    d = ordner(user_id)
    if not os.path.isdir(d):
        return []
    namen = sorted((n for n in os.listdir(d) if n.startswith(PRAEFIX) and n.endswith(".zip")),
                   reverse=True)
    out = []
    for n in namen:
        p = os.path.join(d, n)
        try:
            with zipfile.ZipFile(p) as zf:
                klassen = [e[3:] if e[:2].isdigit() and e[2:3] == "_" else e
                           for e in sorted(zf.namelist()) if e.lower().endswith(".xlsx")]
        except (OSError, zipfile.BadZipFile):
            klassen = []
        out.append({
            "datei": n,
            "zeit": datetime.datetime.fromtimestamp(os.path.getmtime(p)),
            "groesse": os.path.getsize(p),
            "klassen": klassen,
        })
    return out


def lesen(user_id: int, datei: str | None = None) -> bytes:
    """Inhalt einer Version (Standard: neueste). Nur Dateinamen aus versionen() zulässig."""
    erlaubt = [v["datei"] for v in versionen(user_id)]
    if not erlaubt:
        raise FileNotFoundError("Keine gespeicherte Sammlung vorhanden.")
    datei = datei or erlaubt[0]
    if datei not in erlaubt:
        raise FileNotFoundError("Diese Version gibt es nicht.")
    with open(os.path.join(ordner(user_id), datei), "rb") as f:
        return f.read()


def pruefsumme(books: list[dict]) -> str:
    try:
        return hashlib.sha1(pickle.dumps(books, protocol=4)).hexdigest()
    except Exception:  # noqa: BLE001 – unpicklable content: treat as always changed
        return os.urandom(8).hex()


def _stand_datei(user_id: int) -> str:
    return os.path.join(ordner(user_id), "stand.json")


def zuletzt_gespeichert(user_id: int) -> str | None:
    """Prüfsumme des zuletzt gespeicherten Stands (überlebt Neustarts über stand.json)."""
    with _lock:
        if user_id in _gespeichert:
            return _gespeichert[user_id]
    try:
        with open(_stand_datei(user_id), encoding="utf-8") as f:
            wert = json.load(f).get("pruefsumme")
    except (OSError, ValueError):
        wert = None
    with _lock:
        _gespeichert.setdefault(user_id, wert)
    return wert


def als_gespeichert_merken(user_id: int, summe: str) -> None:
    """Nach dem Öffnen: der geladene Stand gilt als gespeichert (kein sofortiges Neuschreiben)."""
    with _lock:
        _gespeichert[user_id] = summe


def _zip_bauen(books: list[dict], password: str) -> bytes:
    from app.excel.writer import build_gradebook
    from app.grades.routes import _gradebook_export_filename

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, book in enumerate(books, start=1):
            clean = {k: v for k, v in book.items() if k != "_zugang"}
            # Laufende Nummer vorne: das Laden sortiert nach Namen, so bleibt die Reihenfolge.
            zf.writestr(f"{i:02d}_{_gradebook_export_filename(book)}",
                        build_gradebook(clean, password=password))
    return buf.getvalue()


def speichern(user_id: int, books: list[dict], password: str, summe: str | None = None) -> str:
    """Neue Version schreiben; liefert den Dateinamen."""
    if not books:
        raise ValueError("Keine Klassen geöffnet.")
    if not password:
        raise ValueError("Ohne Passwort wird nicht auf dem Server gespeichert.")
    summe = summe or pruefsumme(books)
    inhalt = _zip_bauen(books, password)
    with _schreib_lock:
        d = ordner(user_id)
        os.makedirs(d, exist_ok=True)
        stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{PRAEFIX}{stempel}.zip"
        n = 2
        while os.path.exists(os.path.join(d, name)):
            name = f"{PRAEFIX}{stempel}-{n}.zip"
            n += 1
        tmp = os.path.join(d, name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(inhalt)
        os.replace(tmp, os.path.join(d, name))
        with open(_stand_datei(user_id), "w", encoding="utf-8") as f:
            json.dump({"pruefsumme": summe, "datei": name}, f)
        _aufraeumen(d)
    with _lock:
        _gespeichert[user_id] = summe
    log.info("Server-Ablage: %s gespeichert (Benutzer %s, %d Klasse(n))", name, user_id, len(books))
    return name


def _aufraeumen(d: str) -> None:
    namen = sorted((n for n in os.listdir(d) if n.startswith(PRAEFIX) and n.endswith(".zip")),
                   reverse=True)
    behalten = set(namen[:BEHALTEN])
    grenze = (datetime.date.today() - datetime.timedelta(days=TAGE)).strftime("%Y%m%d")
    tage = set()
    for n in namen:
        tag = n[len(PRAEFIX):len(PRAEFIX) + 8]
        if tag >= grenze and tag not in tage:
            tage.add(tag)
            behalten.add(n)
    for n in namen:
        if n not in behalten:
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass


# ── Automatisches Speichern ───────────────────────────────────────────────────

def _ausfuehren(user_id: int) -> None:
    with _lock:
        eintrag = _pending.pop(user_id, None)
        _timers.pop(user_id, None)
    if eintrag is None:
        return
    books, password, summe = eintrag
    try:
        speichern(user_id, books, password, summe)
    except Exception:  # noqa: BLE001 – darf den Server nie stören; steht im Protokoll
        log.exception("Server-Ablage: automatisches Speichern fehlgeschlagen (Benutzer %s)", user_id)


def vormerken(user_id: int, books: list[dict], password: str, summe: str) -> None:
    """Stand merken und nach VERZOEGERUNG speichern (der neueste vorgemerkte Stand gewinnt)."""
    with _lock:
        _pending[user_id] = (copy.deepcopy(books), password, summe)
        if user_id not in _timers:
            t = threading.Timer(VERZOEGERUNG, _ausfuehren, args=(user_id,))
            t.daemon = True
            _timers[user_id] = t
            t.start()


def sofort(user_id: int) -> None:
    """Vorgemerkten Stand jetzt schreiben (z. B. vor dem Abmelden oder Öffnen)."""
    with _lock:
        t = _timers.pop(user_id, None)
    if t is not None:
        t.cancel()
    _ausfuehren(user_id)


def ungespeichert(user_id: int, books: list[dict]) -> bool:
    return bool(books) and pruefsumme(books) != zuletzt_gespeichert(user_id)


def nach_request(response):
    """after_request: Änderungen an den offenen Klassen zum Speichern vormerken."""
    try:
        if request.path.startswith("/static/") or not verfuegbar():
            return response
        password = session.get(PW_KEY)
        from app.grades.routes import GRADEBOOKS_KEY
        books = session.get(GRADEBOOKS_KEY) or []
        if not password or not books:
            return response
        summe = pruefsumme(books)
        uid = int(current_user.id)
        with _lock:
            vorgemerkt = _pending.get(uid)
        if summe == zuletzt_gespeichert(uid) or (vorgemerkt and vorgemerkt[2] == summe):
            return response
        vormerken(uid, books, password, summe)
    except Exception:  # noqa: BLE001
        log.exception("Server-Ablage: Prüfung nach dem Request fehlgeschlagen")
    return response


def beim_abmelden() -> None:
    """Vor session.clear(): offenen Stand sofort sichern, falls Autospeichern aktiv ist."""
    if not verfuegbar():
        return
    password = session.get(PW_KEY)
    from app.grades.routes import GRADEBOOKS_KEY
    books = session.get(GRADEBOOKS_KEY) or []
    uid = int(current_user.id)
    if password and ungespeichert(uid, books):
        with _lock:
            t = _timers.pop(uid, None)
            _pending.pop(uid, None)
        if t is not None:
            t.cancel()
        try:
            speichern(uid, books, password)
        except Exception:  # noqa: BLE001
            log.exception("Server-Ablage: Speichern beim Abmelden fehlgeschlagen")
    else:
        sofort(uid)


def status() -> dict | None:
    """Für die Seitenleiste: aktiv? zuletzt gespeichert? (None, wenn nicht verfügbar)"""
    if not verfuegbar():
        return None
    zuletzt = None
    try:
        zuletzt = datetime.datetime.fromtimestamp(os.path.getmtime(_stand_datei(int(current_user.id))))
    except OSError:
        pass
    return {
        "autospeichern": bool(session.get(PW_KEY)),
        "zuletzt": zuletzt,
    }
