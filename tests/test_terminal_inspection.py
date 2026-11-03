"""Local terminal plot contract.

Version: 1.13.0.dev5 (local/unreleased)
Last updated: 2026-11-03
Change history: ../CHANGELOG.md
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from vispa.terminal_inspection import (inspect, resolve_settings,
    _region_from_table, _sagittal_swc_segments, _remap_sites,
    _remap_workbook_regions)


class TerminalInspectionTests(unittest.TestCase):
    def test_two_terminals_share_one_soma_folder_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            np.save(root / "image.npy", np.ones((8,8,8), dtype=np.uint8))
            swc = root / "raw.swc"
            swc.write_text("1 1 2 2 2 1 -1\n2 2 4 4 4 1 1\n3 2 5 5 5 1 1\n")
            common = dict(input_path=root / "image.npy", swc_path=swc,
                subject="S", soma="A", origin=(0,0,0), resolution=(1,1,1),
                coordinate_frame="raw", output_root=root / "out")
            first = inspect(**common, node_id=2)
            second = inspect(**common, node_id=3)
            self.assertEqual(Path(first["output_png"]).parent,
                             root / "out" / "S(S)_vispa" / "neuron_swc_A" / "terminals")
            self.assertTrue(Path(first["output_png"]).is_file())
            self.assertTrue(Path(second["output_png"]).is_file())
            self.assertNotEqual(first["output_png"], second["output_png"])
            metadata = json.loads(Path(first["soma_metadata"]).read_text())
            self.assertEqual(metadata["raw_soma_xyz_um"], [2.0,2.0,2.0])
            self.assertEqual(metadata["soma"], "A")
            self.assertEqual(metadata["subject_folder"], "S(S)_vispa")
            self.assertEqual(metadata["neuron_folder"], "neuron_swc_A")
            self.assertEqual(metadata["raw_swc_sha256"],
                             __import__("hashlib").sha256(swc.read_bytes()).hexdigest())
            self.assertEqual(sorted(path.name for path in Path(first["output_png"]).parent.iterdir()),
                             ["terminal_000002.json", "terminal_000002.png",
                              "terminal_000003.json", "terminal_000003.png"])

    def test_remap_site_voxel_join_and_population_membership_are_distinct(self):
        import hashlib
        from vispa.sources import read_swc
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw.swc"; processed = root / "004.swc"
            raw.write_text("1 1 0 0 0 1 -1\n2 2 10 10 10 1 1\n3 3 20 20 20 1 1\n", encoding="ascii")
            processed.write_text("1 1 0 0 0 1 -1\n2 2 250 500 750 1 1\n3 3 500 500 750 1 1\n", encoding="ascii")
            remap = root / "remap.json"
            result = {"schema": "remap.one_neuron.v1", "sample_id": "S",
                "neuron_id": "004.swc", "source_sha256": {"swc": hashlib.sha256(processed.read_bytes()).hexdigest()},
                "coordinate_mapping": {"source_xyz_divided_by": 250,
                                       "then_voxel_offset": [0,0,0]},
                "terminal_sites": [{"voxel": [1,2,3], "region": "Area_A"},
                                   {"voxel": [2,2,3], "region": "Area_B"}]}
            remap.write_text(json.dumps(result), encoding="utf-8")
            sites, provenance = _remap_sites(remap, read_swc(raw), processed, "S", "004")
            self.assertEqual({site["node_id"]: site["region"] for site in sites},
                             {2: "Area_A", 3: "Area_B"})
            self.assertEqual(provenance["unmatched_or_ambiguous"], [])
            book = Workbook(); sheet = book.active; sheet.title = "Terminal_Sites"
            sheet.append(["NeuronID", "Neuron_Type", "Terminal_Region", "Side",
                          "Laterality", "Terminal_L1", "Terminal_L3", "Terminal_L6"])
            sheet.append(["004.swc", "", "Area_A", "", "", "", "", "Area_A"])
            sheet.append(["004.swc", "", "Area_B", "", "", "", "", "Area_B"])
            sheet.append(["other.swc", "", "Area_C", "", "", "", "", "Area_C"])
            workbook = root / "S_FULL.xlsx"; book.save(workbook)
            membership = _remap_workbook_regions(workbook, "S", "004")
            self.assertEqual(membership["regions"], ["Area_A", "Area_B"])
            self.assertEqual(membership["sample_identity_source"], "workbook_filename")
            self.assertIn("no endpoint", membership["status"])
            result["terminal_sites"].append({"voxel": [1,2,3], "region": "Area_A"})
            remap.write_text(json.dumps(result), encoding="utf-8")
            sites, provenance = _remap_sites(remap, read_swc(raw), processed, "S", "004")
            self.assertEqual(next(site for site in sites if site["node_id"] == 2)["region_match_status"],
                             "shared_voxel_same_region")
            self.assertEqual(provenance["unmatched_or_ambiguous"][0]["remap_row_count"], 2)

    def test_selected_terminal_region_only_and_unresolved_fallback(self):
        sites = [{"node_id": 3, "xyz_um": (3,3,3),
                  "region": {"names": {"3": {"abbreviation": "CR"},
                                       "6": {"abbreviation": "PrCO"}}}},
                 {"node_id": 4, "xyz_um": (4,4,4)}]
        selected = _region_from_table(sites, 3)
        self.assertEqual(selected["label"], "L3 CR | L6 PrCO")
        self.assertEqual(selected["status"], "provisional")
        self.assertEqual(_region_from_table(sites, 4)["label"], "unresolved")
        self.assertEqual(_region_from_table(sites, 5)["label"], "unresolved")

    def test_sagittal_trace_clips_edges_crossing_slab_and_plane(self):
        from vispa.sources import read_swc
        with tempfile.TemporaryDirectory() as temp:
            swc = Path(temp) / "cross.swc"
            swc.write_text("1 1 0 400 200 1 -1\n2 2 400 400 600 1 1\n", encoding="ascii")
            geometry = {"spacing_mm_ijk": (0.1,0.1,0.1), "shape_ijk": (10,10,10)}
            segments = _sagittal_swc_segments(read_swc(swc), geometry,
                (0,10,0,10), (1.5,2.5))
            self.assertEqual(len(segments), 1)
            self.assertEqual(set(segments[0]), {(3.5,4.0),(4.5,4.0)})
            self.assertEqual(_sagittal_swc_segments(read_swc(swc), geometry,
                (0,10,0,10), (5,6)), [])

    def test_context_settings_inherit_review_and_allow_rectangular_override(self):
        from vispa.config import resolve_settings as resolve_review
        review = resolve_review("review")
        inherited = resolve_settings(review_settings=review)
        self.assertEqual((inherited["width_um"], inherited["height_um"],
                          inherited["depth_um"], inherited["overlay_depth_um"],
                          inherited["scale_bar_um"], inherited["dpi"]),
                         (8000, 8000, 30, 100, 500, 200))
        rectangular = resolve_settings(("width_um=6000", "height_um=3000", "depth_um=45"), review)
        self.assertEqual((rectangular["width_um"], rectangular["height_um"],
                          rectangular["depth_um"]), (6000,3000,45))
        with self.assertRaisesRegex(ValueError, "exceed"):
            resolve_settings(("width_um=20000", "height_um=20000"), review)

    def test_configured_dry_run_reports_rectangular_source_dimensions(self):
        from vispa.config import load
        configured = load()
        sample = next(iter(configured["samples"]))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            swc = root / "raw.swc"
            swc.write_text("1 1 0 0 0 1 -1\n2 2 1 1 1 1 1\n", encoding="ascii")
            plan = inspect(swc_path=swc, subject=sample, soma="A", node_id=2,
                sample=sample, output_root=root / "out", dry_run=True,
                settings=("width_um=6000", "height_um=3000", "depth_um=45"))
            self.assertEqual(tuple(plan["settings"][key] for key in
                ("width_um", "height_um", "depth_um")), (6000,3000,45))
            monkey = str(configured["samples"][sample]["monkey"])
            self.assertEqual(Path(plan["output_png"]).parent,
                root / "out" / f"{sample}({monkey})_vispa" / "neuron_swc_A" / "terminals")
            self.assertFalse((root / "out").exists())

    def test_context_table_sites_follow_actual_z_support(self):
        from vispa.renderers.microscopy_panels import VisPa
        tool = object.__new__(VisPa)
        tool.sample_id = "fixture"
        with mock.patch.object(tool, "_finalize_plot", return_value="unused.png"), \
             mock.patch.object(tool, "_title_text", return_value="context"):
            panel = tool.plot_widefield_context(
                np.ones((5,8,8)), (0,0,300), (10,10,10), (20,20,310), "n",
                target_label="Selected terminal",
                recorded_sites_xyz_um=[(30,30,345),(40,40,360)])
        self.assertEqual([m[4] for m in panel["markers"]],
                         ["Selected terminal", "Recorded table site"])
        self.assertEqual(panel["markers"][1][:2], (3.0,3.0))

    def test_full_sagittal_targets_leaf_but_checks_root(self):
        from vispa.renderers import microscopy_panels as panels
        with tempfile.TemporaryDirectory() as temp:
            swc = Path(temp) / "test.swc"
            swc.write_text("1 1 100 100 100 1 -1\n2 2 200 200 200 1 1\n", encoding="ascii")
            geometry = {"spacing_mm_ijk": [0.1,0.1,0.1], "shape_ijk": [5,5,5]}
            fake = mock.Mock(sample_id="fixture", record={"path": str(swc)}, geometry=geometry)
            fake.plane_for_soma.return_value = (np.ones((5,5)), 2)
            with mock.patch.dict(panels.SAMPLE_PATHS, {"fixture": {"monkey":"x"}}):
                result = panels.prepare_sagittal_panel("fixture", "test", (100,100,100),
                    swc_path=swc, source=fake, target_node_id=2)
                self.assertEqual(result["provenance"]["target_node_id"], 2)
                self.assertEqual(result["provenance"]["sagittal_slice_i"], 2)
                self.assertEqual(result["provenance"]["swc"]["soma_xyz_um"], [100,100,100])
                self.assertEqual(result["panel"]["markers"][0][4], "Target Terminal")
                fake.plane_for_soma.assert_called_with((200.0,200.0,200.0))
                with self.assertRaisesRegex(ValueError, "absent"):
                    panels.prepare_sagittal_panel("fixture", "test", (100,100,100),
                        swc_path=swc, source=fake, target_node_id=99)
                with self.assertRaisesRegex(ValueError, "does not match"):
                    panels.prepare_sagittal_panel("fixture", "test", (200,200,200),
                        swc_path=swc, source=fake, target_node_id=2)
                soma_result = panels.prepare_sagittal_panel("fixture", "test", (100,100,100),
                    swc_path=swc, source=fake)
                self.assertEqual(soma_result["panel"]["markers"][0][4], "Target Soma")
                fake.plane_for_soma.assert_called_with((100.0,100.0,100.0))
                with self.assertRaisesRegex(ValueError, "requires a verified SWC"):
                    panels.prepare_sagittal_panel("fixture", "test", (100,100,100),
                        swc_path=swc.with_name("missing.swc"), source=fake,
                        allow_missing_swc=True, target_node_id=2)

    def test_dry_run_and_render_one_leaf_with_recorded_site(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "image.npy"
            swc = root / "raw.swc"
            table = root / "table.json"
            np.save(image, np.arange(1000, dtype=np.float32).reshape(10,10,10))
            swc.write_text("1 1 2 2 2 1 -1\n2 2 4 4 4 1 1\n3 2 6 6 6 1 2\n", encoding="ascii")
            table.write_text(json.dumps({"coordinate_frame": "raw", "rows": [
                {"node_id": 3, "raw_xyz_um": [6,6,6]}]}), encoding="utf-8")
            kwargs = dict(input_path=image, swc_path=swc, subject="S", soma="A",
                node_id=3, origin=(0,0,0), resolution=(1,1,1),
                coordinate_frame="raw", output_root=root / "out", table_path=table)
            plan = inspect(**kwargs, dry_run=True)
            self.assertEqual(plan["candidate_count"], 1)
            self.assertFalse(Path(plan["output_png"]).exists())
            result = inspect(**kwargs)
            self.assertTrue(Path(result["output_png"]).is_file())
            self.assertTrue(Path(result["receipt"]).is_file())
            self.assertTrue(Path(result["soma_metadata"]).is_file())
            with self.assertRaises(FileExistsError):
                inspect(**kwargs)

    def test_frame_mismatch_and_non_leaf_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            np.save(root / "i.npy", np.ones((3,3,3)))
            (root / "r.swc").write_text("1 1 0 0 0 1 -1\n2 2 1 1 1 1 1\n", encoding="ascii")
            (root / "t.json").write_text(json.dumps({"coordinate_frame": "other",
                "rows": [{"node_id":2,"raw_xyz_um":[1,1,1]}]}), encoding="utf-8")
            kwargs = dict(input_path=root / "i.npy", swc_path=root / "r.swc",
                subject="S", soma="A", node_id=2, origin=(0,0,0),
                resolution=(1,1,1), coordinate_frame="raw", output_root=root,
                table_path=root / "t.json", dry_run=True)
            with self.assertRaisesRegex(ValueError, "table frame"):
                inspect(**kwargs)
            kwargs["table_path"] = None; kwargs["node_id"] = 1
            with self.assertRaisesRegex(ValueError, "childless"):
                inspect(**kwargs)
