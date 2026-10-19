"""Tests der Notenberechnung. Aufruf: python -m unittest discover -s tests"""
import unittest

from app.grades import berechnung as B
from app.grades import gewichtung as G

N = "Muster, Max"


def _ln(sheet, typ, note, *, sl=None, hj=None, ignoriert=False):
    return {"sheet_name": sheet, "name": sheet[3:], "ln_typ": typ, "sl_zuordnung": sl, "hj": hj,
            "nachtermin_von": None, "aufgaben": [],
            "schueler": [{"name": N, "punkte": [], "note_15": note, "ignoriert": ignoriert}]}


def _data(lns, **extra):
    d = {"leistungsnachweise": lns, "mdl_noten": {}, "sl_noten_actual": {}, "hj_noten": {},
         "stammdaten": [{"nachname": "Muster", "vorname": "Max", "status": "Aktiv"}]}
    d.update(extra)
    return d


class SlNoteTest(unittest.TestCase):
    def test_ohne_teilnoten_wie_bisher(self):
        d = _data([_ln("LN_K1", "KLN", 10, sl="SL1")], mdl_noten={N: {"SL1": 5}})
        # Default 80 % mündlich / 20 % KLN
        self.assertAlmostEqual(B.sl_note_for(d, N, "SL1"), 0.8 * 5 + 0.2 * 10)
        self.assertEqual(B.mdl_for(d, N, "SL1"), (5.0, "direkt"))

    def test_kln_gewichte(self):
        d = _data([_ln("LN_K1", "KLN", 12, sl="SL1"), _ln("LN_K2", "KLN", 6, sl="SL1")],
                  kln_weights={"SL1": {"LN_K1": 2}})
        self.assertAlmostEqual(B.sl_note_for(d, N, "SL1"), (2 * 12 + 6) / 3)

    def test_teilnoten_vorlaeufig_und_fest(self):
        d = _data([_ln("LN_K1", "KLN", 10, sl="SL2"),
                   _ln("LN_Ref", "MDL", 14, sl="SL2"), _ln("LN_Abfr", "MDL", 8, sl="SL2")],
                  mdl_weights={"SL2": {"LN_Ref": 2}})
        mean = (2 * 14 + 8) / 3
        self.assertEqual(B.mdl_for(d, N, "SL2"), (mean, "vorlaeufig"))
        self.assertAlmostEqual(B.sl_note_for(d, N, "SL2"), 0.8 * mean + 0.2 * 10)
        # Die endgültige mündliche Note überstimmt das Mittel
        d["mdl_noten"] = {N: {"SL2": 13}}
        self.assertEqual(B.mdl_for(d, N, "SL2"), (13.0, "fest"))
        self.assertAlmostEqual(B.sl_note_for(d, N, "SL2"), 0.8 * 13 + 0.2 * 10)

    def test_teilnoten_anderer_sl_wirken_nicht(self):
        d = _data([_ln("LN_Ref", "MDL", 14, sl="SL1")], mdl_noten={N: {"SL2": 7}})
        self.assertEqual(B.mdl_for(d, N, "SL2"), (7.0, "direkt"))

    def test_ignorierte_teilnote(self):
        d = _data([_ln("LN_A", "MDL", 3, sl="SL1", ignoriert=True), _ln("LN_B", "MDL", 9, sl="SL1")])
        self.assertEqual(B.mdl_for(d, N, "SL1"), (9.0, "vorlaeufig"))

    def test_nur_mdl_oder_nur_kln(self):
        d = _data([_ln("LN_K1", "KLN", 10, sl="SL1")])
        self.assertEqual(B.sl_note_for(d, N, "SL1"), 10)
        d = _data([], mdl_noten={N: {"SL1": 4}})
        self.assertEqual(B.sl_note_for(d, N, "SL1"), 4)


class HjNoteTest(unittest.TestCase):
    def test_sl_mittel_zaehlt_wie_eine_gln(self):
        d = _data([_ln("LN_KA1", "GLN", 9, hj="HJ1"), _ln("LN_KA2", "GLN", 12, hj="HJ1")],
                  mdl_noten={N: {"SL1": 6, "SL2": 9}})
        self.assertAlmostEqual(B.hj_vorschlag_for(d, N, "HJ1"), (9 + 12 + 7.5) / 3)

    def test_bestaetigte_sl_note_und_gln_gewichte(self):
        d = _data([_ln("LN_KA1", "GLN", 9, hj="HJ1"), _ln("LN_KA2", "GLN", 12, hj="HJ1")],
                  mdl_noten={N: {"SL1": 6, "SL2": 9}},
                  sl_noten_actual={N: {"SL1": 10}},
                  gln_weights={"HJ1": {"LN_KA2": 2}},
                  sl_gewichtung={"sl_mittel_w": 0.5})
        sl_mittel = (10 + 9) / 2
        self.assertAlmostEqual(B.hj_vorschlag_for(d, N, "HJ1"),
                               (9 + 2 * 12 + 0.5 * sl_mittel) / 3.5)


class SchuljahrTest(unittest.TestCase):
    def test_standard_ein_drittel_zwei_drittel(self):
        self.assertAlmostEqual(B.compute_schuljahr_note(N, {N: {"HJ1": 9, "HJ2": 12}}), 11)

    def test_eigene_gewichte(self):
        gw = B.get_gewichtung({"sl_gewichtung": {"sj_hj1_w": 1, "sj_hj2_w": 1}})
        self.assertAlmostEqual(B.compute_schuljahr_note(N, {N: {"HJ1": 9, "HJ2": 12}}, gw), 10.5)

    def test_aufnahme_hj2_mit_vorheriger_note(self):
        gw = B.get_gewichtung({"sl_gewichtung": {"sj_hj1_w": 1, "sj_hj2_w": 3}})
        v = B.compute_schuljahr_note_klasse(N, {N: {"HJ2": 12}}, "HJ2", {"HJ1": 8}, gw)
        self.assertAlmostEqual(v, (8 + 3 * 12) / 4)


class GewichtungPayloadTest(unittest.TestCase):
    def setUp(self):
        self.d = _data([_ln("LN_K1", "KLN", 10, sl="SL1"), _ln("LN_M1", "MDL", 10, sl="SL1"),
                        _ln("LN_KA1", "GLN", 10, hj="HJ1")],
                       sl_gewichtung={"sl_mittel_w": 2.0, "hj_gln_w": 1.0})

    def test_merge_ohne_verlust(self):
        G.apply_payload(self.d, {"gewichtung": {"sl_mdl_pct": 60, "sl_kln_pct": 40},
                                 "mdl_weights": {"SL1": {"LN_M1": 3}}})
        self.assertEqual(self.d["sl_gewichtung"]["sl_mittel_w"], 2.0)   # bleibt erhalten
        self.assertEqual(self.d["sl_gewichtung"]["sl_mdl_pct"], 60)
        self.assertEqual(self.d["mdl_weights"], {"SL1": {"LN_M1": 3}})

    def test_ungueltige_eingaben(self):
        for bad in ({"gewichtung": {"foo": 1}},
                    {"gewichtung": {"sl_mdl_pct": -1}},
                    {"gewichtung": {"sl_mdl_pct": 0, "sl_kln_pct": 0}},
                    {"kln_weights": {"SL1": {"LN_M1": 1}}},     # falscher Typ
                    {"kln_weights": {"SL9": {"LN_K1": 1}}},
                    {"gln_weights": {"HJ1": {"LN_KA1": "abc"}}}):
            with self.assertRaises(ValueError, msg=bad):
                G.apply_payload(self.d, bad)
        self.assertNotIn("kln_weights", self.d)   # nichts halb übernommen

    def test_modell(self):
        m = G.build_model(self.d)
        self.assertEqual(m["sj"]["formel"], "33.3 % HJ1 + 66.7 % HJ2")
        self.assertEqual(m["hj"]["HJ1"]["sl_mittel_pct"], 66.7)   # SL-Mittel ×2 gegen eine GLN
        self.assertIn("Teilnote", m["sl"]["SL1"]["formel"])


if __name__ == "__main__":
    unittest.main()
