"""Bounded batch planning tests with synthetic local mesh/SWC inputs.

Version: 1.11.0.dev25 (local/unreleased)
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
from unittest import mock

from batch.render_brain_views import load_jobs, main, run_batch


class BatchPlanningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.mesh = self.root / "region.obj"
        self.mesh.write_text("v -2 -3 -4\nv 2 3 4\nf 1 2 1\n", encoding="ascii")
        self.region_root = self.root / "regions"
        self.region_root.mkdir()
        (self.region_root / "amygdala (Amy).obj").write_text(
            "v -1 -1 -1\nv 1 1 1\nf 1 2 1\n", encoding="ascii")
        swc_root = self.root / "swc" / "251637"
        swc_root.mkdir(parents=True)
        for name in ("002.swc", "001.swc"):
            (swc_root / name).write_text("1 1 0 0 0 200 -1\n2 3 0 1 0 1 1\n", encoding="ascii")
        self.config = self.root / "vispa.json"
        self.config.write_text(json.dumps({
            "version": 1, "base_dir": str(self.root),
            "visual_toolkit": {"worker_python": "C:/not-used/python.exe", "output_root": str(self.root / "session")},
            "sources": {"brain_view": {"mesh_path": str(self.mesh),
                                       "region_mesh_root": str(self.region_root),
                                       "region_color": [0.3, 0.7, 1.0],
                                       "processed_swc_root": str(self.root / "swc"),
                                       "coordinate_frame": "fixture-frame", "coordinate_units": "stored"}}}),
            encoding="utf-8")
        (self.root / "settings").mkdir()
        self.jobs = self.root / "settings" / "jobs.json"
        self.payload = {"schema": "vispa.brain_view_batch.v1", "vispa_config": str(self.config),
                        "allow_all": False, "jobs": [{"sample_id": "251637", "region_id": "region",
                                                  "mesh_path": str(self.mesh), "mesh_label": "Region mesh",
                                                  "neuron_ids": ["002.swc", "001.swc"],
                                                  "coordinate_frame": "fixture-frame", "coordinate_units": "stored",
                                                  "camera_overrides": {"camera_distance_scale": 0.8}}]}
        self.save()

    def save(self):
        self.jobs.write_text(json.dumps(self.payload), encoding="utf-8")

    def test_dry_run_is_sorted_hash_bound_and_no_write(self):
        output = self.root / "output"
        plan = load_jobs(self.jobs, output, 1, False)
        self.assertEqual(plan["jobs"][0]["neuron_id"], "001.swc")
        self.assertEqual(plan["jobs"][0]["preflight"]["mesh_label"], "Region mesh")
        self.assertEqual(plan["jobs"][0]["preflight"]["settings"]["camera_distance_scale"], 0.8)
        self.assertEqual(run_batch(plan, dry_run=True)["status"], "dry_run")
        self.assertFalse(output.exists())

    def test_all_requires_two_opt_ins_and_frame_match(self):
        with self.assertRaisesRegex(ValueError, "allow_all"):
            load_jobs(self.jobs, self.root / "output", None, True)
        self.payload["allow_all"] = True
        self.save()
        self.assertEqual(load_jobs(self.jobs, self.root / "output", None, True)["requested"], 2)
        self.payload["jobs"][0]["coordinate_units"] = "mm"
        self.save()
        with self.assertRaisesRegex(ValueError, "exactly match"):
            load_jobs(self.jobs, self.root / "output", 1, False)

    def test_duplicate_identity_and_settings_overlap_refuse(self):
        self.payload["jobs"][0]["neuron_ids"] = ["001.swc", "001.swc"]
        self.save()
        with self.assertRaisesRegex(ValueError, "unique"):
            load_jobs(self.jobs, self.root / "output", 1, False)
        self.payload["jobs"][0]["neuron_ids"] = ["001.swc"]
        self.save()
        with self.assertRaisesRegex(ValueError, "separate"):
            load_jobs(self.jobs, self.root / "settings" / "output", 1, False)

    def test_default_mesh_label_uses_the_region_id(self):
        self.payload["jobs"][0]["region_id"] = "anterior_insula"
        self.payload["jobs"][0].pop("mesh_label")
        self.save()
        plan = load_jobs(self.jobs, self.root / "output", 1, False)
        self.assertEqual(plan["jobs"][0]["mesh_label"], "anterior_insula")
        self.assertEqual(plan["jobs"][0]["preflight"]["mesh_label"], "anterior_insula")

    def test_optional_region_selector_adds_one_overlay_without_changing_region_id(self):
        self.payload["jobs"][0]["region"] = "Amy"
        self.save()
        plan = load_jobs(self.jobs, self.root / "output", 1, False)
        entry = plan["jobs"][0]
        self.assertEqual(entry["region_id"], "region")
        self.assertEqual(entry["region"], "Amy")
        self.assertEqual(entry["preflight"]["region_mesh"]["acronym"], "Amy")
        self.assertEqual(entry["preflight"]["region_resolution"]["source"], "explicit")

    def test_failed_render_writes_receipt_and_returns_exit_two(self):
        stdout = io.StringIO()
        with (mock.patch("batch.render_brain_views.render_configured_snapshot",
                         side_effect=RuntimeError("synthetic render failure")),
              contextlib.redirect_stdout(stdout)):
            code = main(["--jobs", str(self.jobs), "--output-root",
                         str(self.root / "failed-output"), "--limit", "1"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "partial_or_failed")
        receipt = json.loads((self.root / "failed-output" / "batch_receipt.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "partial_or_failed")
        self.assertEqual(receipt["error"], "synthetic render failure")


if __name__ == "__main__":
    unittest.main()
