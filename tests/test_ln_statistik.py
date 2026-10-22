"""Statistik zu den einzelnen Aufgaben eines Leistungsnachweises."""
import unittest

from app.grades.ln_statistik import afb_statistik, aufgaben_statistik


def _ln(schueler):
    return {
        "aufgaben": [
            {"label": "1", "max_punkte": 10, "afb": "I"},
            {"label": "2", "max_punkte": 10, "afb": "II"},
            {"label": "3", "max_punkte": 4, "afb": "III"},
        ],
        "schueler": schueler,
    }


class AufgabenStatistikTest(unittest.TestCase):
    def test_mittel_median_quote(self):
        st = aufgaben_statistik(_ln([
            {"name": "A", "punkte": [10, 2, 4]},
            {"name": "B", "punkte": [8, 4, 0]},
            {"name": "C", "punkte": [9, 3, 1]},
        ]))
        self.assertEqual(st["n"], 3)
        a1, a2, a3 = st["aufgaben"]
        self.assertEqual(a1["mittel"], 9.0)
        self.assertEqual(a1["median"], 9.0)
        self.assertEqual(a1["quote"], 0.9)
        self.assertEqual(a2["quote"], 0.3)
        self.assertEqual(a3["min"], 0.0)
        self.assertEqual(a3["max_erreicht"], 4.0)
        self.assertAlmostEqual(a3["anteil_voll"], 0.333)
        self.assertAlmostEqual(a3["anteil_null"], 0.333)
        self.assertEqual(st["analyse"]["beste"], "1")
        self.assertEqual(st["analyse"]["schlechteste"], "2")
        self.assertEqual(st["analyse"]["gut"], ["1"])
        self.assertEqual(st["analyse"]["schwach"], ["2", "3"])
        self.assertEqual(st["gesamt"]["max"], 24.0)

    def test_ignorierte_und_leere_schueler_zaehlen_nicht(self):
        st = aufgaben_statistik(_ln([
            {"name": "A", "punkte": [10, None, 2]},   # leeres Feld = 0 Punkte
            {"name": "B", "punkte": [0, 0, 0], "ignoriert": True},
            {"name": "C", "punkte": [None, None, None]},
            {"name": "D", "punkte": []},
        ]))
        self.assertEqual(st["n"], 1)
        self.assertEqual(st["aufgaben"][1]["mittel"], 0.0)
        self.assertEqual(st["aufgaben"][0]["trennschaerfe"], None)  # zu wenige Schüler

    def test_trennschaerfe(self):
        st = aufgaben_statistik(_ln([
            {"name": "A", "punkte": [10, 9, 4]},
            {"name": "B", "punkte": [6, 5, 2]},
            {"name": "C", "punkte": [2, 1, 0]},
        ]))
        self.assertGreater(st["aufgaben"][0]["trennschaerfe"], 0.9)

    def test_ohne_punkte(self):
        st = aufgaben_statistik(_ln([]))
        self.assertEqual(st["n"], 0)
        self.assertIsNone(st["aufgaben"][0]["mittel"])
        self.assertIsNone(st["analyse"]["beste"])


def _afb_ln(schueler):
    # AFB I: 10 P., AFB II: 10 P., AFB III: 10 P.
    return {
        "aufgaben": [
            {"label": "1", "max_punkte": 10, "afb": "I"},
            {"label": "2", "max_punkte": 10, "afb": "II"},
            {"label": "3", "max_punkte": 10, "afb": "III"},
        ],
        "schueler": [{"name": n, "punkte": p, "note_15": note} for n, p, note in schueler],
    }


class AfbStatistikTest(unittest.TestCase):
    def test_ohne_afb(self):
        ln = _afb_ln([("A", [1, 2, 3], 5)])
        for t in ln["aufgaben"]:
            t["afb"] = ""
        self.assertFalse(afb_statistik(ln)["vorhanden"])

    def test_passende_anforderungen(self):
        st = afb_statistik(_afb_ln([
            ("Sehr gut", [10, 10, 8], 14), ("Gut", [10, 8, 3], 10),
            ("Mittel", [8, 6, 1], 7), ("Schwach", [7, 3, 0], 4),
        ]))
        self.assertEqual([b["quote"] for b in st["bereiche"]], [0.875, 0.675, 0.3])
        self.assertTrue(all(c["ok"] for c in st["checks"]), st["checks"])
        self.assertEqual(st["afb3"]["auffaellig"], [])

    def test_afb3_von_schwachem_schueler_geloest(self):
        # "Mittel" kann die Anwendung nicht, löst AFB III aber voll → AFB III zu leicht?
        st = afb_statistik(_afb_ln([
            ("Sehr gut", [10, 10, 9], 14), ("Gut", [10, 8, 3], 10),
            ("Mittel", [8, 2, 10], 8), ("Schwach", [7, 3, 0], 4),
        ]))
        self.assertEqual([a["name"] for a in st["afb3"]["auffaellig"]], ["Mittel"])
        self.assertIn(False, [c["ok"] for c in st["checks"]])

    def test_starke_schueler_in_starker_klasse_nicht_auffaellig(self):
        # Oberes Drittel liegt hier bei 95 % – 85 % in AFB I+II zählt trotzdem als stark
        st = afb_statistik(_afb_ln([
            ("A", [10, 10, 10], 15), ("B", [10, 9, 9], 14), ("C", [9, 8, 8], 13), ("D", [9, 8, 2], 12),
        ]))
        self.assertEqual(st["afb3"]["auffaellig"], [])

    def test_afb3_zu_leicht(self):
        st = afb_statistik(_afb_ln([("A", [10, 9, 9], 14), ("B", [8, 6, 8], 10), ("C", [6, 4, 7], 7)]))
        texte = " ".join(c["text"] for c in st["checks"] if c["ok"] is False)
        self.assertIn("zu leicht", texte)
        self.assertIn("Ungewöhnliche Reihenfolge", texte)


if __name__ == "__main__":
    unittest.main()
