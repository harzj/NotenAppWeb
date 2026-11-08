"""Sicherung des Notfallserver-Datenordners (vom Update-Skript vor jedem Neustart gerufen).

Gesichert werden die Benutzerdatenbank (SQLite-Backup, konsistent auch bei laufendem
Dienst), secret_key und dateilogin.key sowie aus der Server-Ablage die jeweils neueste
(verschluesselte) Sammlung je Benutzer. Ablage: <NOTENAPP_DATA_DIR>/backups/ und,
falls SICHERUNG_ZIEL gesetzt ist, zusaetzlich dort.
Aufbewahrung: die neuesten 10 plus die jeweils neueste je Tag der letzten 30 Tage.

    python deploy/sichern.py [--daten ORDNER] [--ziel ORDNER]
"""
import argparse
import datetime
import os
import sqlite3
import sys
import zipfile

LETZTE = 10
TAGE = 30
SCHLUESSEL = ("secret_key", "dateilogin.key", "dateilogin.key.txt")


def sichere_datenbank(quelle, ziel_datei):
    if not os.path.exists(quelle):
        return False
    q = sqlite3.connect(quelle)
    z = sqlite3.connect(ziel_datei)
    try:
        q.backup(z)
    finally:
        z.close()
        q.close()
    return True


def sichere_schluessel(daten, ziel_zip):
    n = 0
    with zipfile.ZipFile(ziel_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in SCHLUESSEL:
            pfad = os.path.join(daten, name)
            if os.path.isfile(pfad):
                zf.write(pfad, name)
                n += 1
        # Server-Ablage: neueste Sammlung je Benutzer (bleibt mit dem Datei-Passwort verschluesselt)
        ablage = os.path.join(daten, "ablage")
        if os.path.isdir(ablage):
            for benutzer in sorted(os.listdir(ablage)):
                ordner = os.path.join(ablage, benutzer)
                if not os.path.isdir(ordner):
                    continue
                staende = sorted(f for f in os.listdir(ordner) if f.startswith("sammlung_") and f.endswith(".zip"))
                if staende:
                    zf.write(os.path.join(ordner, staende[-1]), f"ablage/{benutzer}/{staende[-1]}")
                    n += 1
    if n == 0:
        os.remove(ziel_zip)
    return n > 0


def aufraeumen(ordner, praefix, endung):
    dateien = sorted((f for f in os.listdir(ordner) if f.startswith(praefix + ".") and f.endswith(endung)),
                     reverse=True)  # Zeitstempel im Namen -> neueste zuerst
    behalten = set(dateien[:LETZTE])
    grenze = (datetime.date.today() - datetime.timedelta(days=TAGE)).strftime("%Y%m%d")
    gesehen = set()
    for f in dateien:
        tag = f.split(".")[1][:8]
        if tag >= grenze and tag not in gesehen:
            gesehen.add(tag)
            behalten.add(f)
    for f in dateien:
        if f not in behalten:
            os.remove(os.path.join(ordner, f))


def sichere_nach(daten, ordner):
    os.makedirs(ordner, exist_ok=True)
    stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ok = []
    db = os.path.join(ordner, f"app.{stempel}.db")
    if sichere_datenbank(os.path.join(daten, "instance", "app.db"), db):
        ok.append(db)
    zipdatei = os.path.join(ordner, f"schluessel.{stempel}.zip")
    if sichere_schluessel(daten, zipdatei):
        ok.append(zipdatei)
    aufraeumen(ordner, "app", ".db")
    aufraeumen(ordner, "schluessel", ".zip")
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--daten", default=os.environ.get("NOTENAPP_DATA_DIR"),
                        help="Datenordner (Standard: Umgebungsvariable NOTENAPP_DATA_DIR)")
    parser.add_argument("--ziel", default=os.environ.get("SICHERUNG_ZIEL"),
                        help="zusaetzlicher Ordner, z. B. Netzlaufwerk (Standard: SICHERUNG_ZIEL)")
    args = parser.parse_args(argv)
    if not args.daten:
        print("FEHLER: kein Datenordner (NOTENAPP_DATA_DIR oder --daten).", file=sys.stderr)
        return 2
    daten = os.path.abspath(args.daten)

    for datei in sichere_nach(daten, os.path.join(daten, "backups")):
        print("gesichert:", datei)
    if args.ziel:
        try:
            for datei in sichere_nach(daten, args.ziel):
                print("gesichert (extern):", datei)
        except OSError as e:
            # Lokale Sicherung steht; ein nicht erreichbares Netzlaufwerk darf das Update nicht stoppen.
            print("WARNUNG: externes Ziel nicht beschreibbar:", e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
