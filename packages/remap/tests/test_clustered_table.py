"""Regression checks for clustered workbook evolution.

Version: 0.2.2.dev1 (local/unreleased)
Last updated: 2026-11-17
Change history: ../CHANGELOG.md
- 2026-11-17: Cover identity, malformed labels, dry run, preservation and output collision.
"""
import csv
from pathlib import Path
import unittest

from openpyxl import Workbook, load_workbook

from remap.morph_clustering.clustered_table import evolve
from tests.local_temp import local_temp


class ClusteredTableTests(unittest.TestCase):
    def test_evolution_and_guards(self):
        with local_temp() as folder:
            root = Path(folder)
            source, output, assignment = (root / n for n in ("source.xlsx", "out.xlsx", "labels.csv"))
            book = Workbook()
            book.active.title = "Summary"
            book.active.append(["SampleID", "NeuronID", "value"])
            book.active.append(["251637", "001.swc", 12])
            book.active.append(["251637", "002.swc", 20])
            book.save(source)
            book.close()
            assignment.write_text("FNT_NeuronID,k_2\n001,1\n", encoding="utf-8")
            plan = evolve(source, output, "251637", [("raw", assignment)], dry_run=True)
            self.assertEqual((plan["rows"], plan["scored"], plan["unscored"]), (2, 1, 1))
            self.assertFalse(output.exists())
            evolve(source, output, "251637", [("raw", assignment)])
            result = load_workbook(output, read_only=True)
            self.assertEqual(list(result["Summary"].values)[1:], [
                ("251637", "001.swc", 12), ("251637", "002.swc", 20)])
            self.assertEqual(list(result["FNT candidates"].values)[1:], [
                ("001.swc", "scored", 1), ("002.swc", "unscored", None)])
            result.close()
            original = output.read_bytes()
            with self.assertRaises(ValueError):
                evolve(source, output, "251637", [("raw", assignment)])
            self.assertEqual(output.read_bytes(), original)
            for content in ("FNT_NeuronID,k_2\n003,1\n",
                            "FNT_NeuronID,k_2\n001,1\n001,2\n",
                            "FNT_NeuronID,k_2\n001,0\n",
                            "FNT_NeuronID,k_2\n001,3\n",
                            "FNT_NeuronID,k_2,k_2\n001,1,1\n",
                            "FNT_NeuronID,k_1\n001,1\n",
                            "FNT_NeuronID,k_2\n"):
                assignment.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    evolve(source, root / "other.xlsx", "251637", [("raw", assignment)])
                self.assertFalse((root / "other.xlsx").exists())


if __name__ == "__main__":
    unittest.main()