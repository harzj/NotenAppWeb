"""Nachtermine, Excel-Blattnamen und Session-Schutz. Aufruf: python -m unittest discover -s tests -t ."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from app.excel import schema as S
from app.excel.reader import load_gradebook
from app.excel.writer import build_gradebook
from app.grades import berechnung as B

SZENARIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_szenario.py")


def _ln(sheet, schueler, nachtermin_von=None, typ="GLN"):
    return {"sheet_name": sheet, "name": sheet[3:], "ln_typ": typ, "hj": "HJ1", "sl_zuordnung": None,
            "gln_slot": None, "nachtermin_von": nachtermin_von, "noten_runden": True,
            "aufgaben": [{"label": "1", "afb": "", "max_punkte": 10}],
            "aufgaben_tree": [], "schueler": schueler}


def _s(name, punkte=None, note=None, ignoriert=False):
    return {"name": name, "punkte": [punkte], "note_15": note, "note_6": None, "ignoriert": ignoriert}


class EffektiveNoteTest(unittest.TestCase):
    def setUp(self):
        self.ht = _ln("LN_KA1", [_s("A, a", 10, 15), _s("B, b"), _s("C, c"), _s("D, d", ignoriert=True)])
        self.nt1 = _ln("LN_KA1_NT", [_s("B, b", 5, 7), _s("C, c")], nachtermin_von="LN_KA1")
        self.nt2 = _ln("LN_KA1_NT2", [_s("C, c", 3, 4), _s("D, d", 8, 11)], nachtermin_von="LN_KA1")
        self.lns = [self.ht, self.nt1, self.nt2]

    def test_haupttermin_und_mehrere_nachtermine(self):
        self.assertEqual(B.effective_entry("A, a", self.ht, self.lns), (15.0, False, None))
        self.assertEqual(B.effective_entry("B, b", self.ht, self.lns), (7.0, False, 1))
        self.assertEqual(B.effective_entry("C, c", self.ht, self.lns), (4.0, False, 2))
        # im Haupttermin ignoriert, aber im Nachtermin geschrieben → zählt
        self.assertEqual(B.effective_entry("D, d", self.ht, self.lns), (11.0, False, 2))

    def test_haupttermin_hat_vorrang(self):
        self.nt1["schueler"].append(_s("A, a", 0, 0))
        self.assertEqual(B.effective_entry("A, a", self.ht, self.lns)[0], 15.0)

    def test_nachtermin_zaehlt_nicht_doppelt(self):
        self.assertEqual(sorted(B.gln_notes_for_hj("B, b", "HJ1", self.lns)), [7.0])
        self.assertEqual(B.gln_notes_for_hj("A, a", "HJ1", self.lns), [15.0])


class ExcelBlattnamenTest(unittest.TestCase):
    def test_ungueltige_und_lange_namen(self):
        lang = "LN_" + "Kursarbeit Analysis Funktionen"  # > 31 Zeichen
        ht = _ln(lang, [_s("A, a", 10, 15), _s("B, b")])
        nt = _ln(lang + "_NT", [_s("B, b", 5, 7)], nachtermin_von=lang)
        slash = _ln("LN_KA 1/2", [_s("A, a", 4, 5)])
        data = {"klasse": "7a", "fach": "M", "schuljahr": "2026", "modus": "klasse",
                "stammdaten": [{"nachname": "A", "vorname": "a"}, {"nachname": "B", "vorname": "b"}],
                "leistungsnachweise": [ht, nt, slash], "gln_weights": {"HJ1": {lang: 2.0}}}
        d = load_gradebook(build_gradebook(data), None)
        sheets = [ln["sheet_name"] for ln in d["leistungsnachweise"]]
        self.assertTrue(all(len(n) <= S.SHEET_NAME_MAX for n in sheets), sheets)
        self.assertIn("LN_KA 1_2", sheets)
        ht2 = next(ln for ln in d["leistungsnachweise"] if not ln["nachtermin_von"] and ln["sheet_name"] != "LN_KA 1_2")
        expected = float(S.percent_to_note15(5, 10, runden=True))  # recomputed from the points
        self.assertEqual(B.effective_entry("B, b", ht2, d["leistungsnachweise"]), (expected, False, 1))
        self.assertEqual(d["gln_weights"]["HJ1"], {ht2["sheet_name"]: 2.0})
        # the in-memory data stays untouched
        self.assertEqual(ht["sheet_name"], lang)


class AppSzenarienTest(unittest.TestCase):
    def _run(self, name):
        with tempfile.TemporaryDirectory() as work:
            e = {k: v for k, v in os.environ.items() if k not in ("FILE_LOGIN_KEY", "FILE_LOGIN_ACCEPT")}
            e.update(PYTHONIOENCODING="utf-8",
                     DATABASE_URL="sqlite:///" + os.path.join(work, "t.db").replace("\\", "/"))
            r = subprocess.run([sys.executable, SZENARIO, name, work], env=e, capture_output=True,
                               text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            return json.loads(r.stdout.strip().splitlines()[-1])

    def test_nachtermine(self):
        out = self._run("nachtermin")
        self.assertTrue(out["kandidaten_seite"])
        self.assertEqual(len(out["nt1_schueler"]), 1)          # benoteter Schüler abgewiesen
        self.assertEqual(out["eff_nt"], [15.0, False, 1])
        self.assertTrue(out["eff_mit"])                          # Punkte im NT überschreiben nichts
        self.assertEqual(out["nt_anzahl"], 2)
        self.assertNotIn(out["nt1_schueler"][0], out["nt2_schueler"])
        self.assertEqual(len(set(out["sheets"])), 2)
        self.assertEqual(set(out["status"].values()), {200}, out["status"])
        self.assertTrue(out["nt_als_ln_umgeleitet"])
        self.assertEqual(out["ln_liste_karten"], 4)              # Nachtermine keine eigenen LN
        self.assertEqual(out["reload_eff"], [15.0, False, 1])
        self.assertEqual(out["reload_nt"], 2)
        self.assertTrue(out["bereinigt"])
        self.assertEqual(out["nach_nt_loeschen"], 1)
        self.assertEqual(out["verwaist"], 0)

    def test_session_nur_bei_aenderung_schreiben(self):
        out = self._run("session")
        self.assertEqual(out["writes_lesend"], 0)
        self.assertEqual(out["writes_schreibend"], 1)


if __name__ == "__main__":
    unittest.main()
