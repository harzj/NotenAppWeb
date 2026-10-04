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

print(json.dumps(out))
