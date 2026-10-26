"""Stepwise region-to-FNT planning tests with local stand-ins for ReMAP.

Version: 1.11.0.dev18 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from batch.remap_stepwise import (
    load_case, main, match_clusters, read_swc_root, remap_version_supported,
    resolve_remap, run_stepwise, select_neurons, share_run_path,
)
from batch.render_review_bulk import load_review_jobs, main as bulk_main, run_review_bulk


class StepwiseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.swc = self.root / "analysis"
        self.raw = self.root / "raw"
        self.swc.mkdir()
        self.raw.mkdir()
        self.analysis_bytes = {}
        for name, x in (("001.swc", 40000), ("002.swc", 10)):
            text = f"# keep\n1 1 {x} 20 30 1 -1\n2 3 1 2 3 1 1\n"
            for folder in (self.swc, self.raw):
                (folder / name).write_text(text, encoding="utf-8")
            self.analysis_bytes[name] = (self.swc / name).read_bytes()
            self.analysis_bytes["raw-" + name] = (self.raw / name).read_bytes()
        self.inputs = {}
        for name in ("atlas.nii.gz", "key.txt", "template.nii.gz", "mask.nii.gz",
                     "charm.csv", "sarm.csv", "dist.txt", "joined.fnt"):
            path = self.root / name
            path.write_bytes(b"fixture-" + name.encode())
            self.inputs[name] = path
        self.config = self.root / "vispa.json"
        self.config.write_text("{}", encoding="utf-8")
        self.case_path = self.root / "cases" / "case.json"
        self.case_path.parent.mkdir()
        self.payload = {
            "schema": "vispa.remap_stepwise.v1",
            "run_id": "bounded-one",
            "share_slot": "remap_outputs",
            "share_base": str(self.root / "share"),
            "allow_all": False,
            "vispa_config": str(self.config),
            "region": {
                "sample_id": "251637",
                "neuron_ids": ["002.swc", "001.swc"],
                "swc_source_dir": str(self.swc),
                "atlas": str(self.inputs["atlas.nii.gz"]),
                "atlas_key": str(self.inputs["key.txt"]),
                "template": str(self.inputs["template.nii.gz"]),
                "hemisphere_mask": str(self.inputs["mask.nii.gz"]),
                "cortex_hierarchy_csv": str(self.inputs["charm.csv"]),
                "subcortical_hierarchy_csv": str(self.inputs["sarm.csv"]),
                "declared_space": "NMT_v2.1_sym atlas voxel index",
                "source_units": None,
            },
            "fnt": {
                "distance": str(self.inputs["dist.txt"]),
                "joined_fnt": str(self.inputs["joined.fnt"]),
                "k": 2,
            },
            "soma": {
                "source": "raw_swc_root",
                "raw_swc_dir": str(self.raw),
                "units": "declared raw SWC units",
            },
        }
        self.save()
        self.output = self.root / "run"

    def save(self):
        self.case_path.write_text(json.dumps(self.payload), encoding="utf-8")

    def api(self):
        parent = self

        class Api(dict):
            version = "0.1.0.dev4"

            def __getitem__(self, key):
                return getattr(self, key)

            def plan_population(self, config):
                self.planned = config
                return {"neuron_ids": list(config["neuron_ids"]),
                        "output_base": config["output_base"]}

            def run_population(self, plan):
                self.ran = True
                workbook = Path(plan["output_base"]) / "tables" / "251637_results.xlsx"
                workbook.parent.mkdir(parents=True, exist_ok=True)
                workbook.write_bytes(b"workbook")
                return {"workbook": str(workbook), "rows": len(plan["neuron_ids"]),
                        "sheets": ["Summary"]}

            def read_fnt_distances(self, distance, joined, symmetrization="max"):
                self.fnt_inputs = (distance, joined, symmetrization)

                class Matrix:
                    index = ["251637_001", "251637_002", "251637_003"]

                return Matrix(), {"n_neurons": 3, "symmetrization": symmetrization}

            def safe_linkage(self, matrix, method="average"):
                self.method = method
                return [[0.0, 1.0, 0.2, 2.0]]

            def fcluster(self, linkage, k, criterion="maxclust"):
                self.cut = (k, criterion)
                return [1, 1, 2]

        api = Api()
        api.ran = False
        parent.api_object = api
        return api

    def reader(self, path):
        self.assertTrue(Path(path).is_file())
        return [{"SampleID": "251637", "NeuronID": "001.swc", "Soma_Region": "CL_Id",
                 "Soma_Phys_X": 9, "Soma_Phys_Y": 8, "Soma_Phys_Z": 7}]

    def test_share_slots_stay_inside_the_fmost_root(self):
        base = str(self.root / "fMOST")
        outputs = share_run_path(base, "outputs", "251637", "run-1")
        remap = share_run_path(base, "remap_outputs", "251637", "run-1")
        resources = share_run_path(base, "resources", "251637", "run-1")
        self.assertTrue(str(outputs).endswith(str(Path("outputs") / "251637" / "run-1")))
        self.assertTrue(str(remap).endswith(str(Path("remap_outputs") / "251637" / "run-1")))
        self.assertTrue(str(resources).endswith(
            str(Path("resources") / "remap_stepwise" / "251637" / "run-1")))
        with self.assertRaisesRegex(ValueError, "share_slot"):
            share_run_path(base, "visual", "251637", "run-1")

    def test_version_gate_and_missing_remap(self):
        self.assertFalse(remap_version_supported("0.1.0.dev3"))
        self.assertTrue(remap_version_supported("0.1.0.dev4"))
        self.assertTrue(remap_version_supported("0.1.0"))
        self.assertTrue(remap_version_supported("0.2.0"))
        with self.assertRaisesRegex(RuntimeError, "ReMAP"):
            resolve_remap(lambda: (_ for _ in ()).throw(ImportError("remap")))

    def test_limit_sorts_and_dry_run_does_not_execute(self):
        case = load_case(self.case_path)
        selected = select_neurons(case, 1, False)
        self.assertEqual(selected, ["001.swc"])
        result = run_stepwise(case, selected, self.output, "output_root",
                              dry_run=True, remap_api=self.api())
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.api_object.ran)
        self.assertEqual(self.api_object.planned["neuron_ids"], ["001.swc"])
        self.assertTrue(str(self.api_object.planned["output_base"]).endswith("region"))

    def test_run_publishes_cluster_and_leaves_swc_bytes_unchanged(self):
        case = load_case(self.case_path)
        selected = select_neurons(case, 1, False)
        result = run_stepwise(case, selected, self.output, "output_root", dry_run=False,
                              remap_api=self.api(), summary_reader=self.reader)
        self.assertEqual(result["status"], "pass", result.get("error"))
        jobs = json.loads((self.output / "vispa_bulk_jobs.json").read_text(encoding="utf-8"))
        self.assertEqual(jobs["schema"], "vispa.review_bulk.v1")
        self.assertEqual(jobs["jobs"][0]["soma_xyz"], [40000.0, 20.0, 30.0])
        self.assertEqual(jobs["jobs"][0]["fnt_cluster"], 1)
        self.assertEqual(jobs["jobs"][0]["fnt_marker"], "251637_001")
        self.assertNotEqual(jobs["jobs"][0]["soma_xyz"], [9.0, 8.0, 7.0])
        self.assertFalse(jobs["swc_coordinates_rewritten"])
        assignments = (self.output / "fnt" / "assignments.csv").read_text(encoding="utf-8")
        self.assertIn("251637_003,2", assignments.replace(" ", ""))
        for name in ("001.swc", "002.swc"):
            self.assertEqual((self.swc / name).read_bytes(), self.analysis_bytes[name])
            self.assertEqual((self.raw / name).read_bytes(), self.analysis_bytes["raw-" + name])
        self.assertEqual(read_swc_root(self.raw / "001.swc"), (40000.0, 20.0, 30.0))

    def test_published_jobs_drive_a_bounded_vispa_dry_run(self):
        case = load_case(self.case_path)
        run_stepwise(case, ["001.swc"], self.output, "output_root", dry_run=False,
                     remap_api=self.api(), summary_reader=self.reader)
        plots = self.root / "plots"
        plan = load_review_jobs(self.output / "vispa_bulk_jobs.json", plots, 1, False)
        self.assertEqual(plan["jobs"][0]["neuron_id"], "001.swc")
        self.assertEqual(run_review_bulk(plan, dry_run=True)["status"], "dry_run")
        self.assertFalse(plots.exists())

    def test_rejects_unsafe_requests(self):
        case = load_case(self.case_path)
        with self.assertRaisesRegex(ValueError, "allow_all"):
            select_neurons(case, None, True)
        with self.assertRaisesRegex(ValueError, "outside"):
            run_stepwise(case, ["001.swc"], self.swc / "inside", "output_root",
                         dry_run=True, remap_api=self.api())
        self.payload["fnt"]["linkage"] = "ward"
        self.save()
        with self.assertRaisesRegex(ValueError, "linkage"):
            load_case(self.case_path)
        self.payload["fnt"]["linkage"] = "average"
        self.payload["region"]["neuron_ids"] = ["001.swc", "001.swc"]
        self.save()
        with self.assertRaisesRegex(ValueError, "unique"):
            load_case(self.case_path)
        with self.assertRaisesRegex(ValueError, "both"):
            match_clusters("251637", ["001.swc", "251637_001.swc"], {"251637_001": 1})

    def test_example_case_fails_closed_before_using_the_share(self):
        example = Path(__file__).with_name("remap_stepwise.example.json")
        with self.assertRaises(FileNotFoundError):
            load_case(example)

    def test_commands_require_an_explicit_destination(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = main(["--case", str(self.case_path), "--limit", "1"])
        self.assertEqual(status, 2)
        self.assertIn("output-root", stream.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bulk_main(["--jobs", str(self.case_path), "--output-root",
                                        str(self.root / "plots"), "--limit", "1", "--dry-run"]), 2)


class BulkRenderTests(unittest.TestCase):
    def test_renderer_failure_keeps_a_partial_receipt(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        config = root / "vispa.json"
        config.write_text("{}", encoding="utf-8")
        jobs = root / "jobs" / "vispa_bulk_jobs.json"
        jobs.parent.mkdir()
        jobs.write_text(json.dumps({
            "schema": "vispa.review_bulk.v1",
            "sample_id": "251637",
            "vispa_config": str(config),
            "jobs": [
                {"sample_id": "251637", "neuron_id": "001.swc", "render_ready": True,
                 "soma_xyz": [1, 2, 3], "soma_units": "declared", "soma_region": "CL_Id",
                 "fnt_cluster": 1, "fnt_marker": "251637_001"},
                {"sample_id": "251637", "neuron_id": "002.swc", "render_ready": False,
                 "soma_error": "missing raw SWC"},
                {"sample_id": "251637", "neuron_id": "003.swc", "render_ready": True,
                 "soma_xyz": [4, 5, 6], "soma_units": "declared"},
            ],
        }), encoding="utf-8")
        output = root / "plots"

        def renderer(job, folder, config_path):
            if job["neuron_id"] == "003.swc":
                raise RuntimeError("context unavailable")
            target = folder / "Soma.png"
            target.write_bytes(b"png")
            return {"outputs": {"Soma": str(target), "Context": str(target),
                                "Sagittal": str(target), "TrioPlot": str(target)},
                    "errors": []}

        with self.assertRaisesRegex(ValueError, "allow_all"):
            load_review_jobs(jobs, output, None, True)
        payload = json.loads(jobs.read_text(encoding="utf-8"))
        payload["allow_all"] = True
        jobs.write_text(json.dumps(payload), encoding="utf-8")
        plan = load_review_jobs(jobs, output, None, True)
        self.assertEqual([item["neuron_id"] for item in plan["jobs"]], ["001.swc", "003.swc"])
        result = run_review_bulk(plan, dry_run=False, renderer=renderer)
        self.assertEqual(result["status"], "partial_or_failed")
        self.assertTrue((output / "251637" / "001" / "Soma.png").is_file())
        self.assertTrue((output / "batch_receipt.json").is_file())


if __name__ == "__main__":
    unittest.main()
