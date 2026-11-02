"""Focused exact-identity neuron-side source tests.

Version: 1.12.0.dev4 (local/unreleased)
Last updated: 2026-11-02
Change history: ../CHANGELOG.md
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from openpyxl import Workbook

from vispa.neuron_side import lookup_neuron_side
from vispa.renderers.swc_brain_view import _hierarchy_region


class NeuronSideTests(unittest.TestCase):
    def _book(self, root, rows):
        book = Workbook()
        sheet = book.active
        sheet.title = "Summary"
        sheet.append(["SampleID", "NeuronID", "Soma_Region", "Soma_Side"])
        for row in rows:
            sheet.append(row)
        book.save(Path(root) / "251637_FULL.xlsx")

    def test_exact_right_and_changed_identity(self):
        with TemporaryDirectory() as root:
            self._book(root, [("251637", "004.swc", "CR_PrCO", "R"),
                              ("251637", "005.swc", "CL_PrCO", "L")])
            right = lookup_neuron_side(root, "251637", "004.swc")
            self.assertEqual((right["status"], right["side"]), ("verified", "Right"))
            self.assertEqual(right["source"]["row"], 2)
            self.assertEqual(right["source"]["soma_region"], "CR_PrCO")
            self.assertEqual(lookup_neuron_side(root, "251637", "005.swc")["side"], "Left")
            self.assertEqual(lookup_neuron_side(root, "251637", "006.swc")["status"], "unknown")
            self.assertEqual(lookup_neuron_side(root, "251638", "004.swc")["status"], "unknown")

    def test_duplicate_and_conflict_fail_closed(self):
        with TemporaryDirectory() as root:
            self._book(root, [("251637", "004.swc", "CR_PrCO", "R"),
                              ("251637", "004.swc", "CR_PrCO", "R")])
            self.assertIn("duplicate", lookup_neuron_side(root, "251637", "004.swc")["reason"])
            self._book(root, [("251637", "004.swc", "CL_PrCO", "R")])
            conflict = lookup_neuron_side(root, "251637", "004.swc")
            self.assertEqual(conflict["status"], "unknown")
            self.assertIn("conflicts", conflict["reason"])
            self.assertEqual(lookup_neuron_side(root, "251637", "../004.swc")["status"], "unknown")

    def test_portal_key_is_canonical_cortex_not_neuron_side_or_sarm_index(self):
        with TemporaryDirectory() as root:
            mesh = {"file": "precentral_operular_area (PrCO).obj", "sha256": "a" * 64}
            entries = [
                {"family": "CHARM", "side": side, "level6_index": index,
                 "acronym": "PrCO", "status": "unique", "mesh": mesh}
                for side, index in (("CL", 49), ("CR", 549))
            ] + [{"family": "SARM", "side": "SL", "level6_index": 1004,
                  "acronym": "Cl", "status": "unique", "mesh":
                  {"file": "claustrum (Cl).obj", "sha256": "b" * 64}}]
            path = Path(root) / "map.json"
            path.write_text(json.dumps({"schema": "vispa-nmt-level6-region-obj-map.v2",
                                        "source_sha256": {"mesh_manifest": "c" * 64},
                                        "entries": entries}), encoding="utf-8")
            source = {"region_hierarchy_map": path}
            manifest = {"sha256": "c" * 64}
            selected, resolution = _hierarchy_region(source, "PrCO_49", manifest)
            self.assertEqual(selected, mesh)
            self.assertEqual(resolution["canonical_region_key"]["right_atlas_index"], 549)
            self.assertNotIn("side", resolution)
            self.assertNotIn("hierarchy", resolution)
            selected, resolution = _hierarchy_region(source, "Cl_304", manifest)
            self.assertIsNone(selected)
            self.assertEqual(resolution["status"], "unmatched")
            self.assertIn("namespace", resolution["reason"])


if __name__ == "__main__":
    unittest.main()
