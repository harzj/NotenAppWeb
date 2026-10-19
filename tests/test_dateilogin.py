"""Anmelden mit Notendatei, Datenordner der exe. Aufruf: python -m unittest discover -s tests -t ."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

from app.auth import dateilogin
from app.excel.reader import load_gradebook
from app.excel.writer import build_gradebook

KEY = "k" * 40
SZENARIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_szenario.py")
DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Noten_demo_klasse.xlsx")


def _user(**kw):
    base = dict(username="mueller", email="m@schule.de", lehrer_vorname="Eva", lehrer_nachname="Müller",
                dienstbezeichnung=None, anrede="Frau", notendatei_import=False, is_admin=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _read(work, name):
    with open(os.path.join(work, name), "rb") as f:
        return f.read()


class TokenTest(unittest.TestCase):
    def test_roundtrip(self):
        info = dateilogin.read_token(dateilogin.make_token(_user(), KEY), KEY)
        self.assertEqual(info["username"], "mueller")
        self.assertEqual(info["lehrer_nachname"], "Müller")

    def test_niemals_admin(self):
        info = dateilogin.read_token(dateilogin.make_token(_user(is_admin=True), KEY), KEY)
        self.assertNotIn("is_admin", info)

    def test_falscher_schluessel_und_manipulation(self):
        tok = dateilogin.make_token(_user(), KEY)
        self.assertIsNone(dateilogin.read_token(tok, "x" * 40))
        self.assertIsNone(dateilogin.read_token(tok[:-2] + "AA", KEY))
        self.assertIsNone(dateilogin.read_token("", KEY))

    def test_abgelaufen(self):
        tok = dateilogin.make_token(_user(), KEY)
        self.assertIsNone(dateilogin.read_token(tok, KEY, max_age=-1))

    def test_platzhalter_und_kurze_schluessel(self):
        old = os.environ.get("FILE_LOGIN_KEY")
        try:
            os.environ["FILE_LOGIN_KEY"] = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
            self.assertIsNone(dateilogin.load_key())
            os.environ["FILE_LOGIN_KEY"] = "kurz"
            self.assertIsNone(dateilogin.load_key())
            os.environ["FILE_LOGIN_KEY"] = KEY
            self.assertEqual(dateilogin.load_key(), KEY)
        finally:
            if old is None:
                os.environ.pop("FILE_LOGIN_KEY", None)
            else:
                os.environ["FILE_LOGIN_KEY"] = old

    def test_schluesseldatei_aus_jedem_editor(self):
        with tempfile.TemporaryDirectory() as d:
            for name, raw in [("utf8", (KEY + "\n").encode()),
                              ("bom", b"\xef\xbb\xbf" + KEY.encode() + b"\r\n"),
                              ("utf16", ("﻿" + KEY + "\r\n").encode("utf-16-le")),
                              ("quotes", ('"' + KEY + '"').encode())]:
                p = os.path.join(d, name)
                with open(p, "wb") as f:
                    f.write(raw)
                self.assertEqual(dateilogin._read_key_file(p), KEY, name)

    def test_excel_roundtrip(self):
        data = {"klasse": "7p", "stammdaten": [], "leistungsnachweise": [], "_zugang": "abc.def"}
        self.assertEqual(load_gradebook(build_gradebook(data, "pw"), "pw").get("_zugang"), "abc.def")
        data.pop("_zugang")
        self.assertNotIn("_zugang", load_gradebook(build_gradebook(data, None), None))


@unittest.skipUnless(os.path.exists(DEMO), "Demo-Datei fehlt")
class AppSzenarienTest(unittest.TestCase):
    """Export beim Landkreis → Anmeldung am (leeren) Notfallserver."""

    def _run(self, name, work, **env):
        e = {k: v for k, v in os.environ.items()
             if k not in ("FILE_LOGIN_KEY", "FILE_LOGIN_ACCEPT", "NOTENAPP_DATA_DIR", "DATABASE_URL")}
        e.update(env, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, SZENARIO, name, work], env=e, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def _db(self, work, name):
        return "sqlite:///" + os.path.join(work, name).replace("\\", "/")

    def test_export_und_notfall_login(self):
        with tempfile.TemporaryDirectory() as work:
            res = self._run("export", work, FILE_LOGIN_KEY=KEY, DATABASE_URL=self._db(work, "landkreis.db"))
            self.assertTrue(res["page_hint"])
            self.assertTrue(res["session_clean"])
            self.assertIn("_zugang", load_gradebook(_read(work, "mit_pw.xlsx"), "geheim"))
            self.assertNotIn("_zugang", load_gradebook(_read(work, "ohne_pw.xlsx"), None))

            res = self._run("notfall", work, FILE_LOGIN_KEY=KEY, FILE_LOGIN_ACCEPT="true",
                            DATABASE_URL=self._db(work, "notfall.db"))
            self.assertTrue(res["karte"])
            self.assertTrue(res["falsches_pw"])
            self.assertTrue(res["ohne_token"])
            self.assertTrue(res["angemeldet"])
            self.assertEqual(res["user"], {"approved": True, "admin": False, "nachname": "Müller"})
            self.assertEqual(res["klassen"], 1)
            self.assertTrue(res["session_clean"])

            # Fremder Schlüssel: Datei wird abgelehnt
            res = self._run("notfall", work, FILE_LOGIN_KEY="z" * 40, FILE_LOGIN_ACCEPT="true",
                            DATABASE_URL=self._db(work, "notfall2.db"))
            self.assertFalse(res["angemeldet"])
            self.assertIsNone(res["user"])

    def test_zugangslinks(self):
        with tempfile.TemporaryDirectory() as work:
            res = self._run("links_a", work, FILE_LOGIN_KEY=KEY, DATABASE_URL=self._db(work, "a.db"))
            self.assertTrue(res["formular"])
            self.assertTrue(res["nach_einladung"].endswith("/auth/profil"))
            self.assertEqual(res["neu1"], {"approved": True, "admin": False})
            self.assertTrue(res["zweimal"])
            self.assertTrue(res["manipuliert"])
            self.assertTrue(res["neues_pw_geht"])
            self.assertFalse(res["altes_pw_geht"])
            # Server B mit gleichem Schluessel: Passwort-Link legt das Konto dort an
            res = self._run("links_b", work, FILE_LOGIN_KEY=KEY, DATABASE_URL=self._db(work, "b.db"))
            self.assertEqual(res["neu1_angelegt"], {"approved": True, "email": "neu1@schule.de"})
            self.assertTrue(res["login_b"])
            self.assertTrue(res["einladung_b"])
            # Server C mit anderem Schluessel: Links gelten dort nicht
            res = self._run("links_b", work, FILE_LOGIN_KEY="z" * 40, DATABASE_URL=self._db(work, "c.db"))
            self.assertIsNone(res["neu1_angelegt"])
            self.assertFalse(res["einladung_b"])

    def test_notfall_exe_legt_schluessel_an(self):
        with tempfile.TemporaryDirectory() as work:
            res = self._run("frozen_notfall", work, NOTENAPP_DATA_DIR=os.path.join(work, "daten"),
                            FILE_LOGIN_ACCEPT="true")
            self.assertTrue(res["key_angelegt"])
            self.assertTrue(res["key_gleich"])
            self.assertTrue(res["karte"])
            self.assertFalse(res["hinweis"])

    def test_landkreis_nimmt_keine_datei_an(self):
        with tempfile.TemporaryDirectory() as work:
            res = self._run("landkreis_nimmt_nicht_an", work, FILE_LOGIN_KEY=KEY,
                            DATABASE_URL=self._db(work, "lk.db"))
            self.assertFalse(res["karte"])
            self.assertEqual(res["status"], 404)

    def test_exe_datenordner_und_absicherung(self):
        with tempfile.TemporaryDirectory() as work:
            dd = os.path.join(work, "daten")
            res = self._run("frozen", work, NOTENAPP_DATA_DIR=dd)
            self.assertEqual(os.path.normcase(res["data_dir"]), os.path.normcase(dd))
            self.assertTrue(res["db_uebernommen"])
            self.assertTrue(res["marker"])
            self.assertTrue(res["secret_key_datei"])
            self.assertTrue(res["secret_key_aus_datei"])
            self.assertFalse(res["debug"])
            self.assertTrue(res["admin_pw_datei"])
            self.assertFalse(res["admin_admin_geht"])
            self.assertTrue(res["admin_zufall_geht"])


if __name__ == "__main__":
    unittest.main()
