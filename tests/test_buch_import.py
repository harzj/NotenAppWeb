"""informatik.book-Import: CSV einlesen, OSS-Namen zuordnen, Zuordnung in der Notendatei speichern."""
import unittest

from app.excel.reader import load_gradebook
from app.excel.writer import build_gradebook
from app.grades import buch

KOPF = "format;klasse;klassen_id;test_id;test;anwendung;datum;schueler_id;oss_name;status;aufgabe_nr;aufgabe;max;punkte;offen"


def csv(*zeilen):
    return ("﻿" + "\r\n".join((KOPF,) + zeilen) + "\r\n").encode("utf-8")


class ParseTest(unittest.TestCase):
    def test_lang_format(self):
        daten = buch.parse_buch_csv(csv(
            "informatik.book/1;9a;3;7;SÜ 1;Buch;2026-09-14;student:1;anna.mueller;abgegeben;1;SQL;4;3,5;0",
            "informatik.book/1;9a;3;7;SÜ 1;Buch;2026-09-14;student:1;anna.mueller;abgegeben;2;ER;6;2;1",
            "informatik.book/1;9a;3;7;SÜ 1;Buch;2026-09-14;student:2;ben.x;nicht geschrieben;;;;;",
        ))
        self.assertEqual(daten["klasse"], "9a")
        self.assertEqual(daten["schueler"], {"student:1": "anna.mueller", "student:2": "ben.x"})
        (test,) = daten["tests"]
        self.assertEqual([(a["nr"], a["titel"], a["max"]) for a in test["aufgaben"]], [(1, "SQL", 4.0), (2, "ER", 6.0)])
        self.assertEqual(test["ergebnisse"]["student:1"], {"punkte": {1: 3.5, 2: 2.0}, "offen": [2]})
        self.assertNotIn("student:2", test["ergebnisse"])

    def test_fremde_datei(self):
        with self.assertRaises(buch.BuchParseError):
            buch.parse_buch_csv("Nachname;Vorname\r\nA;B\r\n".encode())


class ZuordnungTest(unittest.TestCase):
    NAMEN = ["Müller, Anna-Lena", "Schmidt, Jonas", "Bergquell, Ari", "Bergquell, Caro"]

    def test_vorschlaege(self):
        z = buch.zuordnen({"s1": "anna-lena.mueller_2", "s2": "jonas.schmit", "s3": "bergquell", "s4": "lehrer.test"},
                          self.NAMEN, {})
        self.assertEqual((z["s1"]["name"], z["s1"]["art"]), ("Müller, Anna-Lena", "sicher"))
        self.assertEqual((z["s2"]["name"], z["s2"]["art"]), ("Schmidt, Jonas", "vorschlag"))   # Tippfehler
        self.assertEqual(z["s3"]["art"], "vorschlag")                                          # mehrdeutig
        self.assertEqual((z["s4"]["name"], z["s4"]["art"]), ("", "keine"))

    def test_gespeichert_geht_vor_und_wird_nicht_doppelt_vergeben(self):
        z = buch.zuordnen({"s1": "jonas.schmidt", "s2": "xyz"}, self.NAMEN, {"s2": "Schmidt, Jonas"})
        self.assertEqual(z["s2"], {"name": "Schmidt, Jonas", "art": "gespeichert", "score": 1.0})
        self.assertNotEqual(z["s1"]["name"], "Schmidt, Jonas")


class SpeichernTest(unittest.TestCase):
    def test_zuordnung_ueberlebt_die_notendatei(self):
        data = {"klasse": "9a", "fach": "Informatik", "schuljahr": "2026/27", "stammdaten": [], "leistungsnachweise": [],
                "buch_zuordnung": {"student:1": "Müller, Anna", "student:2": ""},
                "buch_oss_namen": {"student:1": "anna.mueller"}, "buch_importiert": {"7": "LN_SÜ 1"}}
        zurueck = load_gradebook(build_gradebook(data))
        self.assertEqual(zurueck["buch_zuordnung"], data["buch_zuordnung"])
        self.assertEqual(zurueck["buch_importiert"], data["buch_importiert"])
        self.assertEqual(zurueck["buch_oss_namen"], data["buch_oss_namen"])


if __name__ == "__main__":
    unittest.main()
