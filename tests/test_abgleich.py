"""Abgleich zweier Notendateien derselben Klasse (app/grades/abgleich.py)."""
import copy
import unittest

from app.grades import abgleich


def klasse():
    return {
        "klasse": "7a", "schuljahr": "2026/27",
        "stammdaten": [{"nachname": "Adler", "vorname": "Ada", "status": "Aktiv"},
                       {"nachname": "Bach", "vorname": "Ben", "status": "Aktiv"}],
        "leistungsnachweise": [{
            "sheet_name": "LN_KA1", "name": "KA1", "ln_typ": "GLN", "hj": "HJ1",
            "aufgaben": [{"label": "1", "max_punkte": 10.0}],
            "schueler": [{"name": "Adler, Ada", "punkte": [8.0], "note_15": 11, "note_6": 2},
                         {"name": "Bach, Ben", "punkte": [None], "note_15": None, "note_6": None}],
        }],
        "mdl_noten": {"Adler, Ada": {"SL1": 10, "SL2": None}, "Bach, Ben": {"SL1": 7, "SL2": None}},
        "schuljahr_noten_actual": {},
    }


class AbgleichTest(unittest.TestCase):
    def test_identisch(self):
        self.assertEqual(abgleich.vergleiche(klasse(), klasse()), {"auto": [], "konflikte": []})

    def test_fehlendes_wird_uebernommen_abweichendes_ist_konflikt(self):
        alt, neu = klasse(), klasse()
        neu["mdl_noten"]["Adler, Ada"]["SL2"] = 12            # fehlt im alten Stand
        neu["mdl_noten"]["Bach, Ben"]["SL1"] = 9              # widerspricht
        neu["leistungsnachweise"][0]["schueler"][1].update(punkte=[5.0], note_15=7)   # alt leer
        neu["leistungsnachweise"].append({**copy.deepcopy(neu["leistungsnachweise"][0]),
                                          "sheet_name": "LN_KA2", "name": "KA2"})
        neu["stammdaten"].append({"nachname": "Cem", "vorname": "Can", "status": "Aktiv"})
        neu["schuljahr_noten_actual"] = {"Adler, Ada": 11}
        e = abgleich.vergleiche(alt, neu)
        auto = {x["id"] for x in e["auto"]}
        self.assertIn("note|mdl_noten|Adler, Ada|SL2", auto)
        self.assertIn("ln_zeile|LN_KA1|Bach, Ben", auto)
        self.assertIn("ln|LN_KA2", auto)
        self.assertIn("schueler|Cem, Can", auto)
        self.assertIn("note|schuljahr_noten_actual|Adler, Ada|", auto)
        self.assertEqual([x["id"] for x in e["konflikte"]], ["note|mdl_noten|Bach, Ben|SL1"])

        daten, zaehler = abgleich.anwenden(alt, neu, {})
        self.assertEqual(daten["mdl_noten"]["Bach, Ben"]["SL1"], 7)        # Standard: aktueller Stand
        self.assertEqual(daten["mdl_noten"]["Adler, Ada"]["SL2"], 12)
        self.assertEqual(len(daten["leistungsnachweise"]), 2)
        self.assertEqual(daten["schuljahr_noten_actual"], {"Adler, Ada": 11})
        self.assertEqual(zaehler, {"auto": len(e["auto"]), "neu": 0, "alt": 1})
        daten, _ = abgleich.anwenden(alt, neu, {"note|mdl_noten|Bach, Ben|SL1": "neu"})
        self.assertEqual(daten["mdl_noten"]["Bach, Ben"]["SL1"], 9)
        self.assertEqual(alt["mdl_noten"]["Bach, Ben"]["SL1"], 7)           # Eingabe unverändert

    def test_einzelne_korrektur_im_ln(self):
        alt, neu = klasse(), klasse()
        neu["leistungsnachweise"][0]["schueler"][0].update(punkte=[9.0], note_15=13)
        (k,) = abgleich.vergleiche(alt, neu)["konflikte"]
        self.assertEqual((k["id"], k["alt"], k["neu"]), ("ln_zeile|LN_KA1|Adler, Ada", "8 → 11 NP", "9 → 13 NP"))
        daten, _ = abgleich.anwenden(alt, neu, {k["id"]: "neu"})
        self.assertEqual(daten["leistungsnachweise"][0]["schueler"][0]["punkte"], [9.0])

    def test_geaenderte_aufgaben_nur_als_ganzer_ln(self):
        alt, neu = klasse(), klasse()
        neu["leistungsnachweise"][0]["aufgaben"] = [{"label": "1", "max_punkte": 12.0}]
        neu["leistungsnachweise"][0]["schueler"][0]["punkte"] = [11.0]
        (k,) = abgleich.vergleiche(alt, neu)["konflikte"]
        self.assertEqual(k["id"], "ln_ganz|LN_KA1")

    def test_nur_im_alten_stand_bleibt(self):
        alt, neu = klasse(), klasse()
        neu["mdl_noten"] = {}
        neu["leistungsnachweise"] = []
        daten, zaehler = abgleich.anwenden(alt, neu, {})
        self.assertEqual(daten, alt)
        self.assertEqual(zaehler, {"auto": 0, "neu": 0, "alt": 0})

    def test_klassen_schluessel(self):
        self.assertEqual(abgleich.klassen_schluessel({"klasse": " 7 A"}), "7a")


if __name__ == "__main__":
    unittest.main()
