"""Aufgabenstruktur: beim Laden einer Datei aus den Bezeichnungen wiederherstellen."""
import copy
import unittest

from app.excel.reader import _rebuild_tree_from_labels
from app.grades.aufgaben import generate_labels, get_leaves, sanitize_node, tree_to_flat


def _cols(*labels):
    return [{"label": l, "afb": "I", "max_punkte": 2.0} for l in labels]


def _after_edit(tree):
    """What the editor does when the tree is saved again."""
    t = [sanitize_node(n) for n in copy.deepcopy(tree)]
    generate_labels(t)
    return [a["label"] for a in tree_to_flat(t)]


class AufgabenStrukturTest(unittest.TestCase):
    def test_unteraufgaben_bleiben_erhalten(self):
        tree = _rebuild_tree_from_labels(_cols("1", "2.1", "2.2", "3"))
        self.assertEqual([n["label"] for n in tree], ["1", "2", "3"])
        self.assertEqual([c["label"] for c in tree[1]["children"]], ["2.1", "2.2"])
        self.assertFalse(any(n["custom_label"] for n in tree + tree[1]["children"]))
        self.assertEqual(_after_edit(tree), ["1", "2.1", "2.2", "3"])

    def test_buchstaben_und_drei_ebenen(self):
        labels = ("1.a", "1.b", "2.1.a", "2.1.b", "2.2")
        tree = _rebuild_tree_from_labels(_cols(*labels))
        self.assertEqual(tree[0]["numbering_style"], "abc")
        self.assertEqual(tree[1]["children"][0]["numbering_style"], "abc")
        self.assertEqual(_after_edit(tree), list(labels))

    def test_eigene_bezeichnungen_bleiben(self):
        tree = _rebuild_tree_from_labels(_cols("Teil A", "Teil B.1", "Bonus"))
        self.assertTrue(tree[0]["custom_label"])
        self.assertEqual(_after_edit(tree), ["Teil A", "Teil B.1", "Bonus"])

    def test_spalten_reihenfolge_bleibt(self):
        # Points are stored by column: never merge, reorder or drop a column
        for labels in (("1", "2", "2.1"), ("1.a", "2", "1.b"), ("1", "1", "2"), ("1.", "x.y.z.w")):
            tree = _rebuild_tree_from_labels(_cols(*labels))
            self.assertEqual([l["label"] for l in get_leaves(tree)], list(labels), labels)


if __name__ == "__main__":
    unittest.main()
