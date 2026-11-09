"""Szenarien für test_dateilogin.py – laufen in einem eigenen Prozess, weil
Datenbank-URL, Datenordner und frozen-Modus beim Import festgelegt werden.

Aufruf: python tests/_szenario.py <name> <arbeitsordner>; Ergebnis als JSON auf stdout.
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
name, work = sys.argv[1], sys.argv[2]
out = {}


def _app():
    from app import create_app
    app = create_app("development")
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["RATELIMIT_ENABLED"] = False
    return app


def _login(c, user="admin", pw="admin"):
    return c.post("/auth/login", data={"username": user, "password": pw})


if name == "export":
    # Landkreis-Seite: Export als freigeschalteter Benutzer mit/ohne Passwort
    from app.extensions import db
    from app.models import User
    app = _app()
    with app.app_context():
        u = User(username="mueller", email="mueller@schule.de", is_approved=True,
                 lehrer_vorname="Eva", lehrer_nachname="Müller", anrede="Frau")
        u.set_password("pw-mueller")
        db.session.add(u)
        db.session.commit()
    c = app.test_client()
    _login(c, "mueller", "pw-mueller")
    c.get("/demo-beispielklasse")
    out["page_hint"] = "Zugriffsschlüssel" in c.get("/export/excel").get_data(as_text=True)
    r = c.post("/export/excel", data={"password": "geheim"})
    open(os.path.join(work, "mit_pw.xlsx"), "wb").write(r.data)
    r = c.post("/export/excel", data={"password": ""})
    open(os.path.join(work, "ohne_pw.xlsx"), "wb").write(r.data)
    # Session must not keep the token
    with c.session_transaction() as s:
        out["session_clean"] = all("_zugang" not in b for b in s["gradebooks"])

elif name == "notfall":
    # Notfallserver mit leerer Datenbank: Anmelden mit Notendatei
    app = _app()
    c = app.test_client()
    out["karte"] = "Mit Notendatei anmelden" in c.get("/auth/login").get_data(as_text=True)

    def datei_login(fname, pw):
        with open(os.path.join(work, fname), "rb") as f:
            data = f.read()
        r = c.post("/auth/login-datei", data={"datei": (io.BytesIO(data), fname), "datei_passwort": pw},
                   content_type="multipart/form-data", follow_redirects=True)
        return r.get_data(as_text=True)

    out["falsches_pw"] = "nicht geöffnet werden" in datei_login("mit_pw.xlsx", "falsch")
    out["ohne_token"] = "keinen gültigen Zugriffsschlüssel" in datei_login("ohne_pw.xlsx", "irgendwas")
    body = datei_login("mit_pw.xlsx", "geheim")
    out["angemeldet"] = "Angemeldet als mueller" in body
    from app.models import User
    with app.app_context():
        u = User.query.filter_by(username="mueller").first()
        out["user"] = None if u is None else {
            "approved": u.is_approved, "admin": u.is_admin, "nachname": u.lehrer_nachname}
    with c.session_transaction() as s:
        out["klassen"] = len(s.get("gradebooks") or [])
        out["session_clean"] = all("_zugang" not in b for b in s.get("gradebooks") or [])

elif name == "landkreis_nimmt_nicht_an":
    app = _app()
    c = app.test_client()
    out["karte"] = "Mit Notendatei anmelden" in c.get("/auth/login").get_data(as_text=True)
    out["status"] = c.post("/auth/login-datei").status_code

elif name == "frozen":
    # Simulate the PyInstaller exe: old instance/ next to the exe, fixed data folder
    import shutil
    import sqlite3
    exe_dir = os.path.join(work, "dist_neu")
    os.makedirs(os.path.join(exe_dir, "instance"))
    old_db = os.path.join(exe_dir, "instance", "app.db")
    con = sqlite3.connect(old_db)
    con.execute("CREATE TABLE marker (x INTEGER)")
    con.commit()
    con.close()
    sys.frozen = True
    sys.executable = os.path.join(exe_dir, "NotenApp.exe")
    sys._MEIPASS = os.path.join(ROOT, "app")
    app = _app()
    from app import paths
    dd = paths.data_dir()
    out["data_dir"] = dd
    out["db_uebernommen"] = os.path.exists(os.path.join(dd, "instance", "app.db"))
    con = sqlite3.connect(os.path.join(dd, "instance", "app.db"))
    out["marker"] = bool(con.execute("SELECT name FROM sqlite_master WHERE name='marker'").fetchone())
    con.close()
    out["secret_key_datei"] = os.path.exists(os.path.join(dd, "secret_key"))
    out["secret_key_aus_datei"] = app.config["SECRET_KEY"] == open(os.path.join(dd, "secret_key")).read().strip()
    out["debug"] = app.config["DEBUG"]
    out["admin_pw_datei"] = os.path.exists(os.path.join(dd, "admin_passwort.txt"))
    c = app.test_client()
    out["admin_admin_geht"] = _login(c, "admin", "admin").status_code == 302
    pw = [line.split()[-1] for line in open(os.path.join(dd, "admin_passwort.txt"), encoding="utf-8")
          if line.startswith("Passwort:")][0]
    out["admin_zufall_geht"] = _login(c, "admin", pw).status_code == 302
    shutil.rmtree(os.path.join(dd, "instance", "sessions"), ignore_errors=True)

elif name == "frozen_notfall":
    # Notfall-exe ohne dateilogin.key: Schluessel wird angelegt, Karte erscheint
    exe_dir = os.path.join(work, "dist_notfall")
    os.makedirs(exe_dir)
    sys.frozen = True
    sys.executable = os.path.join(exe_dir, "NotenApp.exe")
    sys._MEIPASS = os.path.join(ROOT, "app")
    app = _app()
    from app import paths
    key_file = os.path.join(paths.data_dir(), "dateilogin.key")
    out["key_angelegt"] = os.path.exists(key_file)
    out["key_gleich"] = os.path.exists(key_file) and open(key_file, encoding="utf-8").read().strip() == app.config["FILE_LOGIN_KEY"]
    body = app.test_client().get("/auth/login").get_data(as_text=True)
    out["karte"] = "Mit Notendatei anmelden" in body
    out["hinweis"] = "noch nicht eingerichtet" in body

elif name == "quellcode_notfall":
    # Notfallserver aus dem Quellcode (Dienst, deploy/): NOTENAPP_NOTFALL=1 + Datenordner
    app = _app()
    from app import paths
    from app.update_check import get_update_info
    dd = paths.data_dir()
    out["data_dir"] = dd
    out["notfall"] = paths.is_notfall_server()
    out["db_im_datenordner"] = os.path.exists(os.path.join(dd, "instance", "app.db"))
    out["secret_key_aus_datei"] = app.config["SECRET_KEY"] == open(os.path.join(dd, "secret_key")).read().strip()
    out["debug"] = app.config["DEBUG"]
    out["key_angelegt"] = os.path.exists(os.path.join(dd, "dateilogin.key"))
    out["datei_login"] = app.config["FILE_LOGIN_ACCEPT"]
    out["kein_update_hinweis"] = get_update_info(app) is None
    c = app.test_client()
    out["karte"] = "Mit Notendatei anmelden" in c.get("/auth/login").get_data(as_text=True)
    out["register"] = c.get("/auth/register").status_code
    out["zugang_ungueltig"] = c.get("/auth/zugang/xyz").status_code
    out["admin_admin_geht"] = _login(c, "admin", "admin").status_code == 302

elif name == "quellcode_ohne_notfall":
    # Landkreis/Entwicklung: NOTENAPP_DATA_DIR allein aendert nichts
    app = _app()
    from app import paths
    out["data_dir"] = paths.data_dir()
    out["root"] = ROOT
    out["notfall"] = paths.is_notfall_server()
    out["datei_login"] = app.config["FILE_LOGIN_ACCEPT"]

elif name == "ablage":
    # Server-Ablage am Notfallserver aus dem Quellcode (NOTENAPP_SERVER_ABLAGE=1)
    import time
    import zipfile as _zip
    from app.grades import ablage
    ablage.VERZOEGERUNG = 0.3
    app = _app()
    from app import paths
    from app.excel.reader import load_gradebook
    from app.grades.routes import GRADEBOOKS_KEY
    dd = paths.data_dir()
    pw = [line.split()[-1] for line in open(os.path.join(dd, "admin_passwort.txt"), encoding="utf-8")
          if line.startswith("Passwort:")][0]
    c = app.test_client()
    _login(c, "admin", pw)
    out["seite_ohne_daten"] = c.get("/ablage").status_code
    c.get("/demo-beispielklasse")
    out["zu_kurz"] = "mindestens 4" in c.post("/ablage/speichern", data={"password": "ab"},
                                              follow_redirects=True).get_data(as_text=True)
    r = c.post("/ablage/speichern", data={"password": "geheim1"})
    out["gespeichert"] = r.status_code == 302
    v = ablage.versionen(1)
    out["versionen_1"] = len(v)
    roh = open(os.path.join(ablage.ordner(1), v[0]["datei"]), "rb").read()
    with _zip.ZipFile(io.BytesIO(roh)) as zf:
        eintrag = zf.read(sorted(zf.namelist())[0])
    try:
        load_gradebook(eintrag, None)
        out["verschluesselt"] = False
    except Exception:
        out["verschluesselt"] = True
    # Änderung -> automatisch gespeichert, auch ohne weitere Anfrage
    with c.session_transaction() as sess:
        books = sess[GRADEBOOKS_KEY]
        books[0]["klasse"] = "Ablagetest"
        sess[GRADEBOOKS_KEY] = books
    c.get("/")
    time.sleep(1.5)
    out["versionen_2"] = len(ablage.versionen(1))
    # Abmelden, neu anmelden -> Weiterleitung zur Ablage
    c.get("/auth/logout")
    r = _login(c, "admin", pw)
    out["login_ziel"] = r.headers.get("Location", "")
    out["falsches_pw"] = "fehlgeschlagen" in c.post("/ablage/oeffnen", data={"password": "falsch"},
                                                    follow_redirects=True).get_data(as_text=True)
    r = c.post("/ablage/oeffnen", data={"password": "geheim1"})
    out["geoeffnet"] = r.status_code == 302 and r.headers.get("Location", "").endswith("/")
    with c.session_transaction() as sess:
        out["klasse_nach_oeffnen"] = sess[GRADEBOOKS_KEY][0].get("klasse")
    c.get("/")
    time.sleep(1.0)
    out["kein_neuschreiben_nach_oeffnen"] = len(ablage.versionen(1)) == out["versionen_2"]
    out["fremde_datei"] = "gibt es nicht" in c.post("/ablage/oeffnen", data={"password": "geheim1", "datei": "../../app.db"},
                                                    follow_redirects=True).get_data(as_text=True)
    out["sidebar"] = "Server-Ablage" in c.get("/").get_data(as_text=True)

elif name == "ablage_aus":
    # Gleiches Flag, aber kein Notfallserver (Landkreis) bzw. exe: Ablage bleibt aus
    if os.environ.get("ALS_EXE"):
        exe_dir = os.path.join(work, "dist_notfall")
        os.makedirs(exe_dir)
        sys.frozen = True
        sys.executable = os.path.join(exe_dir, "NotenApp.exe")
        sys._MEIPASS = os.path.join(ROOT, "app")
    app = _app()
    from app.grades import ablage
    with app.app_context():
        out["aktiviert"] = ablage.aktiviert(app)
    c = app.test_client()
    if not os.environ.get("ALS_EXE"):
        _login(c)
        out["seite"] = c.get("/ablage").status_code

elif name == "links_a":
    # Server A (z.B. Landkreis): Admin erzeugt Links, Kollegen benutzen sie
    import re
    from app.models import User
    app = _app()
    c = app.test_client()
    _login(c)

    def link(url):
        body = c.post(url).get_data(as_text=True)
        return re.search(r'id="linkFeld" value="([^"]+)"', body).group(1)

    einladung = link("/auth/admin/einladung")
    einladung_b = link("/auth/admin/einladung")   # fuer Server B
    c.get("/auth/logout")
    pfad = einladung.split("://", 1)[1].split("/", 1)[1]
    out["formular"] = "Konto einrichten" in c.get("/" + pfad).get_data(as_text=True)
    r = c.post("/" + pfad, data={"username": "neu1", "email": "neu1@schule.de",
                                 "password": "langespasswort", "password2": "langespasswort"})
    out["nach_einladung"] = r.headers.get("Location", "")
    with app.app_context():
        u = User.query.filter_by(username="neu1").first()
        out["neu1"] = None if u is None else {"approved": u.is_approved, "admin": u.is_admin}
    c.get("/auth/logout")
    out["zweimal"] = "bereits benutzt" in c.get("/" + pfad).get_data(as_text=True)
    out["manipuliert"] = "ungültig oder abgelaufen" in c.get("/" + pfad[:-3] + "xyz").get_data(as_text=True)
    # Passwort-Link fuer neu1
    _login(c)
    with app.app_context():
        uid = User.query.filter_by(username="neu1").first().id
    pw_link = link(f"/auth/admin/users/{uid}/passwort-link")
    pw_link_b = link(f"/auth/admin/users/{uid}/passwort-link")
    c.get("/auth/logout")
    pfad = pw_link.split("://", 1)[1].split("/", 1)[1]
    r = c.post("/" + pfad, data={"password": "nochlaengerespw", "password2": "nochlaengerespw"})
    c.get("/auth/logout")
    out["neues_pw_geht"] = _login(c, "neu1", "nochlaengerespw").status_code == 302
    c.get("/auth/logout")
    out["altes_pw_geht"] = _login(c, "neu1", "langespasswort").status_code == 302
    with open(os.path.join(work, "links.json"), "w", encoding="utf-8") as f:
        json.dump({"einladung": einladung_b, "passwort": pw_link_b}, f)

elif name == "links_b":
    # Server B (z.B. Notfallserver, leere DB, gleicher FILE_LOGIN_KEY)
    from app.models import User
    app = _app()
    c = app.test_client()
    with open(os.path.join(work, "links.json"), encoding="utf-8") as f:
        links = json.load(f)
    pfad = links["passwort"].split("://", 1)[1].split("/", 1)[1]
    r = c.post("/" + pfad, data={"password": "notfallpasswort1", "password2": "notfallpasswort1"})
    with app.app_context():
        u = User.query.filter_by(username="neu1").first()
        out["neu1_angelegt"] = None if u is None else {"approved": u.is_approved, "email": u.email}
    c.get("/auth/logout")
    out["login_b"] = _login(c, "neu1", "notfallpasswort1").status_code == 302
    c.get("/auth/logout")
    pfad = links["einladung"].split("://", 1)[1].split("/", 1)[1]
    out["einladung_b"] = "Konto einrichten" in c.get("/" + pfad).get_data(as_text=True)

elif name == "nachtermin":
    # Nachtermine: Auswahl, mehrere pro LN, Haupttermin hat Vorrang, Export/Import
    from app.excel.reader import load_gradebook
    from app.grades import berechnung as B
    app = _app()
    c = app.test_client()
    _login(c)
    c.get("/demo-beispielklasse")

    def book():
        with c.session_transaction() as s:
            return s["gradebooks"][s.get("active_gradebook_idx", 0)]

    d = book()
    idx = next(i for i, ln in enumerate(d["leistungsnachweise"]) if ln["ln_typ"] == "KLN")
    parent = d["leistungsnachweise"][idx]
    ohne = [s["name"] for s in parent["schueler"] if s.get("note_15") is None]
    mit = next(s["name"] for s in parent["schueler"] if s.get("note_15") is not None)
    note_mit = next(s["note_15"] for s in parent["schueler"] if s["name"] == mit)
    out["kandidaten_seite"] = all(n in c.get(f"/ln/{idx}").get_data(as_text=True) for n in ohne)

    # Nachtermin 1 nur für den ersten Fehlenden; der benotete Schüler wird abgewiesen
    c.post(f"/ln/{idx}/nachtermin/anlegen", data={"student": [ohne[0], mit]})
    d = book()
    nts = B.nachtermine_for(d["leistungsnachweise"][idx], d["leistungsnachweise"])
    out["nt1_schueler"] = [s["name"] for s in nts[0]["schueler"]]
    nt1_idx = d["leistungsnachweise"].index(nts[0])
    max_p = [a["max_punkte"] for a in nts[0]["aufgaben"]]
    c.post(f"/ln/{nt1_idx}/noten", json={"schueler": [{"name": ohne[0], "punkte": max_p},
                                                      {"name": mit, "punkte": [0] * len(max_p)}]})
    d = book()
    lns = d["leistungsnachweise"]
    out["eff_nt"] = B.effective_entry(ohne[0], lns[idx], lns)
    out["eff_mit"] = B.effective_entry(mit, lns[idx], lns)[0] == note_mit

    # Nachtermin 2: der in NT 1 Benotete steht nicht mehr zur Auswahl
    c.post(f"/ln/{idx}/nachtermin/anlegen", data={"student": ohne})
    d = book()
    nts = B.nachtermine_for(d["leistungsnachweise"][idx], d["leistungsnachweise"])
    out["nt_anzahl"] = len(nts)
    out["nt2_schueler"] = [s["name"] for s in nts[1]["schueler"]]
    out["sheets"] = [nt["sheet_name"] for nt in nts]

    seiten = [f"/ln/{idx}", f"/ln/{idx}/nachtermin/1", f"/ln/{idx}/nachtermin/2", "/ln",
              "/uebersicht/hj1", "/uebersicht/hj2", "/uebersicht/schuljahr", "/sl/SL3", "/sl/SL4",
              "/uebersicht/hj2/drucken", "/uebersicht/schuljahr/drucken"]
    out["status"] = {p: c.get(p).status_code for p in seiten}
    out["nt_als_ln_umgeleitet"] = c.get(f"/ln/{nt1_idx}").status_code == 302
    out["ln_liste_karten"] = c.get("/ln").get_data(as_text=True).count("bi-pencil")

    # Export und wieder laden: Nachtermin-Note zählt weiter
    r = c.post("/export/excel", data={"password": ""})
    d2 = load_gradebook(r.data, None)
    lns2 = d2["leistungsnachweise"]
    p2 = next(ln for ln in lns2 if ln["sheet_name"] == parent["sheet_name"])
    out["reload_eff"] = B.effective_entry(ohne[0], p2, lns2)
    out["reload_nt"] = len(B.nachtermine_for(p2, lns2))

    # Zu früh angelegter Nachtermin (Altbestand): Benotete werden beim Öffnen entfernt
    with c.session_transaction() as s:
        b = s["gradebooks"][s.get("active_gradebook_idx", 0)]
        nt = B.nachtermine_for(b["leistungsnachweise"][idx], b["leistungsnachweise"])[1]
        nt["schueler"].append({"name": mit, "punkte": [], "note_15": None, "note_6": None})
    c.get(f"/ln/{idx}")
    d = book()
    nt = B.nachtermine_for(d["leistungsnachweise"][idx], d["leistungsnachweise"])[1]
    out["bereinigt"] = mit not in [s["name"] for s in nt["schueler"]]

    # Löschen: einzelner Nachtermin, dann LN samt Nachterminen
    c.post(f"/ln/{idx}/nachtermin/1/loeschen")
    d = book()
    out["nach_nt_loeschen"] = len(B.nachtermine_for(d["leistungsnachweise"][idx], d["leistungsnachweise"]))
    c.post(f"/ln/{idx}/loeschen")
    d = book()
    out["verwaist"] = sum(1 for ln in d["leistungsnachweise"]
                          if ln.get("nachtermin_von") == parent["sheet_name"])

elif name == "nachruecken":
    # Schüler, die in den Stammdaten stehen, aber im LN fehlen, nachträglich aufnehmen
    app = _app()
    c = app.test_client()
    _login(c)
    c.get("/demo-beispielklasse")

    def book():
        with c.session_transaction() as s:
            return s["gradebooks"][s.get("active_gradebook_idx", 0)]

    d = book()
    idx = next(i for i, ln in enumerate(d["leistungsnachweise"])
               if ln["ln_typ"] == "GLN" and not ln.get("nachtermin_von"))
    # Neuer Schüler, der (wie bei Aufnahme ab später) nicht automatisch im LN landet
    with c.session_transaction() as s:
        b = s["gradebooks"][s.get("active_gradebook_idx", 0)]
        b["stammdaten"].append({"nachname": "Neu", "vorname": "Nina", "status": "aktiv", "austritt": ""})
    vorher = [s["name"] for s in book()["leistungsnachweise"][idx]["schueler"]]
    r = c.get(f"/ln/{idx}")
    seite = r.get_data(as_text=True)
    out["status"] = r.status_code
    out["kandidat_sichtbar"] = "Neu, Nina" in seite and 'id="nachrueckenModal"' in seite
    # Bereits enthaltene Namen werden ignoriert
    c.post(f"/ln/{idx}/schueler-nachruecken", data={"student": ["Neu, Nina", vorher[0]]})
    ln = book()["leistungsnachweise"][idx]
    namen = [s["name"] for s in ln["schueler"]]
    out["neu_drin"] = "Neu, Nina" in namen
    out["sortiert"] = namen == sorted(namen, key=lambda n: tuple(t.strip().lower() for t in n.partition(",")[::2]))
    out["nicht_am_ende"] = namen[-1] != "Neu, Nina"
    out["anzahl_diff"] = len(namen) - len(vorher)
    row = next(s for s in ln["schueler"] if s["name"] == "Neu, Nina")
    out["punkte_laenge_ok"] = len(row["punkte"]) == len(ln["aufgaben"])
    out["alte_noten_erhalten"] = all(
        any(s2["name"] == s1["name"] and s2.get("note_15") == s1.get("note_15") for s2 in ln["schueler"])
        for s1 in d["leistungsnachweise"][idx]["schueler"])
    out["danach_kein_kandidat"] = 'id="nachrueckenModal"' not in c.get(f"/ln/{idx}").get_data(as_text=True)

elif name == "session":
    # Unveränderte Session wird nicht zurückgeschrieben (sonst überschreibt ein
    # paralleler Seitenaufruf gerade gespeicherte Noten)
    app = _app()
    c = app.test_client()
    _login(c)
    c.get("/demo-beispielklasse")
    c.get("/")  # consumes the flash message (a real change)
    iface = app.session_interface
    writes = []
    orig = iface._upsert_session
    iface._upsert_session = lambda *a, **k: (writes.append(1), orig(*a, **k))
    c.get("/ln")
    c.get("/uebersicht/schuljahr")
    out["writes_lesend"] = len(writes)
    c.post("/ln/1/noten", json={"schueler": []})
    out["writes_schreibend"] = len(writes)

print(json.dumps(out))
