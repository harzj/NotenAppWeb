import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy"))
import sichern  # noqa: E402


class SichernTest(unittest.TestCase):
    def test_sicherung_datenbank_und_schluessel(self):
        with tempfile.TemporaryDirectory() as daten:
            os.makedirs(os.path.join(daten, "instance"))
            con = sqlite3.connect(os.path.join(daten, "instance", "app.db"))
            con.execute("CREATE TABLE users (id INTEGER)")
            con.execute("INSERT INTO users VALUES (1)")
            con.commit()
            con.close()
            for name in ("secret_key", "dateilogin.key"):
                with open(os.path.join(daten, name), "w") as f:
                    f.write("x" * 40)
            extern = os.path.join(daten, "extern")
            self.assertEqual(sichern.main(["--daten", daten, "--ziel", extern]), 0)
            for ordner in (os.path.join(daten, "backups"), extern):
                dateien = os.listdir(ordner)
                db = [f for f in dateien if f.endswith(".db")]
                self.assertEqual(len(db), 1)
                self.assertTrue(any(f.startswith("schluessel.") for f in dateien))
                con = sqlite3.connect(os.path.join(ordner, db[0]))
                self.assertEqual(con.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
                con.close()

    def test_ohne_datenordner_fehler(self):
        env = os.environ.pop("NOTENAPP_DATA_DIR", None)
        try:
            self.assertEqual(sichern.main([]), 2)
        finally:
            if env is not None:
                os.environ["NOTENAPP_DATA_DIR"] = env


if __name__ == "__main__":
    unittest.main()
