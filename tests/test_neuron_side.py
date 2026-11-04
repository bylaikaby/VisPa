"""Focused exact-identity neuron-side source tests.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../CHANGELOG.md
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import csv
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest import mock

import numpy as np
from openpyxl import Workbook

from vispa import data_input_adaptor, neuron_side
from vispa.data_input_adaptor import (
    acquire_neuron_side, acquire_neuron_sides, lookup_neuron_side,
    side_from_region, write_neuron_catalog_table,
)
from vispa.renderers.swc_brain_view import _hierarchy_region


class NeuronSideTests(unittest.TestCase):
    def test_compatibility_module_shares_data_input_adaptor_state(self):
        self.assertIs(neuron_side, data_input_adaptor)
        self.assertIs(neuron_side.acquire_neuron_side, acquire_neuron_side)
        self.assertIs(neuron_side.lookup_neuron_side, lookup_neuron_side)

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

    def test_remap_results_can_supply_region_without_explicit_side_column(self):
        with TemporaryDirectory() as root:
            book = Workbook()
            sheet = book.active
            sheet.title = "Summary"
            sheet.append(["SampleID", "NeuronID", "Soma_Region"])
            sheet.append(["251637", "004.swc", "CR_PrCO"])
            sheet.append(["251637", "005.swc", "CL_PrCO"])
            path = Path(root) / "251637_results.xlsx"
            book.save(path)

            right = lookup_neuron_side(path, "251637", "004.swc")
            self.assertEqual((right["status"], right["side"]), ("verified", "Right"))
            self.assertEqual(right["source"]["producer"], "remap_results")
            self.assertEqual(right["source"]["side_method"], "Soma_Region_prefix")
            self.assertEqual(lookup_neuron_side(root, "251637", "005.swc")["side"], "Left")

    def test_side_function_requires_an_explicit_region_prefix(self):
        self.assertEqual(side_from_region("CL_Ial"), "Left")
        self.assertEqual(side_from_region("SR_Cl"), "Right")
        self.assertIsNone(side_from_region("PrCO_49"))
        self.assertIsNone(side_from_region(None))

    def test_native_vispa_side_acquisition_uses_soma_coordinate_and_atlas(self):
        with TemporaryDirectory() as root:
            atlas_path = Path(root) / "atlas.npy"
            key_path = Path(root) / "key.txt"
            image = np.zeros((2, 2, 2, 1, 6), dtype=np.int16)
            image[1, 1, 0, 0, 5] = 549
            np.save(atlas_path, image)
            key_path.write_text(
                "Index\tAbbreviation\tFull_Name\n"
                "549\tCR_PrCO\tCR_precentral_operular_area\n",
                encoding="utf-8")
            config = {"sources": {"atlas": {
                "root": atlas_path,
                "key": key_path,
                "coordinate_scale_um": 250.0,
            }}}

            result = acquire_neuron_side(
                "251637", "004.swc", config, soma_xyz=(250.0, 250.0, 0.0))

        self.assertEqual((result["status"], result["side"]), ("verified", "Right"))
        self.assertEqual(result["source"]["atlas_voxel"], [1, 1, 0])
        self.assertEqual(result["source"]["atlas_region"], "CR_PrCO")
        self.assertEqual(result["source"]["method"], "NMT_atlas_region_prefix")
        self.assertEqual(result["source"]["producer"], "VisPa native atlas side acquisition")

    def test_catalog_side_batch_reuses_native_soma_atlas_mechanism(self):
        with TemporaryDirectory() as root:
            atlas_path = Path(root) / "atlas.npy"
            key_path = Path(root) / "key.txt"
            image = np.zeros((2, 2, 2, 1, 6), dtype=np.int16)
            image[0, 0, 0, 0, 5] = 49
            image[1, 1, 0, 0, 5] = 549
            np.save(atlas_path, image)
            key_path.write_text(
                "Index\tAbbreviation\tFull_Name\n"
                "49\tCL_PrCO\tleft precentral operular area\n"
                "549\tCR_PrCO\tright precentral operular area\n",
                encoding="utf-8")
            config = {"sources": {"atlas": {
                "root": atlas_path, "key": key_path,
                "coordinate_scale_um": 250.0,
            }}}
            fetched = "2026-11-04T00:00:00Z"
            source_sha = "a" * 64
            soma_catalog = {
                "sample_id": "251637",
                "request_url": "http://example/getSoma?fMOST_id=251637",
                "fetched_at": fetched,
                "sha256": source_sha,
                "source_size": 123,
                "rows": [],
                "by_neuron": {
                    "004.swc": {"neuron_id": "004.swc",
                                 "soma_xyz": [250.0, 250.0, 0.0], "row": 2},
                    "005.swc": {"neuron_id": "005.swc",
                                 "soma_xyz": [0.0, 0.0, 0.0], "row": 3},
                },
            }
            with mock.patch.object(
                    data_input_adaptor, "_fetch_soma_catalog",
                    return_value=soma_catalog) as fetch:
                result = acquire_neuron_sides(
                    "251637", ["004.swc", "005.swc", "006.swc"], config)
        fetch.assert_called_once()
        self.assertEqual(result["counts"], {"Left": 1, "Right": 1, "Unknown": 1})
        self.assertEqual(result["results"]["004.swc"]["side"], "Right")
        self.assertEqual(result["results"]["005.swc"]["side"], "Left")
        self.assertEqual(result["results"]["006.swc"]["status"], "unknown")
        self.assertEqual(
            result["results"]["004.swc"]["source"]["soma_source"]["sha256"],
            source_sha)

    def test_catalog_table_records_side_mechanism_and_provenance(self):
        fetched = "2026-11-04T00:00:00Z"
        source_sha = "a" * 64
        snapshot_id = hashlib.sha256(
            f"251637\0{fetched}\0{source_sha}".encode("utf-8")).hexdigest()
        snapshot = {
            "sample_id": "251637",
            "source_kind": "live-iondata",
            "request_url": "http://example/selectNeurons?id=251637",
            "source_date": "live",
            "fetched_at": fetched,
            "sha256": source_sha,
            "snapshot_id": snapshot_id,
            "rows": [{
                "sample_id": "251637",
                "neuron_id": "004.swc",
                "portal_region": "PrCO_49",
                "snapshot_id": snapshot_id,
            }],
        }
        side_result = {
            "status": "complete",
            "counts": {"Left": 0, "Right": 1, "Unknown": 0},
            "source": {"method": "IONData_soma_catalog+NMT_atlas"},
            "results": {
                "004.swc": {
                    "status": "verified",
                    "side": "Right",
                    "reason": "soma coordinate maps to CR_PrCO",
                    "source": {
                        "method": "NMT_atlas_region_prefix",
                        "atlas_region": "CR_PrCO",
                        "atlas_voxel": [192, 217, 83],
                        "atlas_sha256": "b" * 64,
                        "soma_xyz": [47990.6992, 54164.6016, 20808.1992],
                        "soma_source": {
                            "sha256": source_sha,
                        },
                    },
                },
            },
        }
        with TemporaryDirectory() as root:
            record = write_neuron_catalog_table(
                snapshot, side_result, root, "936",
                recorded_at=datetime(2026, 11, 4, 10, 11, 12, tzinfo=timezone.utc))
            with Path(record["path"]).open(
                    encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertTrue(record["path"].endswith(
            "936_251637_neuron_table_20261104_101112.csv"))
        self.assertEqual(rows[0]["Side"], "Right")
        self.assertEqual(rows[0]["SideMethod"], "NMT_atlas_region_prefix")
        self.assertEqual(rows[0]["AtlasRegion"], "CR_PrCO")
        self.assertEqual(rows[0]["SomaCatalogSHA256"], source_sha)

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
