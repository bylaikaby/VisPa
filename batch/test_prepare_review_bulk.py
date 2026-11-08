"""Bounded job-preparation tests for exact animal identities and raw cache.

Version: 1.21.5 (local/unreleased)
Last updated: 2026-11-08
Change history: ../CHANGELOG.md
Status: candidate
2026-11-08: Isolate synthetic raw-source fixtures from the live shared cache.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import yaml
from unittest import mock

from batch.prepare_review_bulk import plan_jobs, prepare_jobs
from vispa.review_bulk_prepare import _region_entries, _selected_region
from vispa.data_input_adaptor import region_display_label
from vispa.review_bulk_dialog import BulkReviewDialog
from vispa.config import load as load_config
from vispa.review_bulk_render import (
    _region_display_value, load_review_jobs, neuron_folder_name, run_folder_name, run_review_bulk,
    validate_run_name,
)


class PrepareReviewBulkTests(unittest.TestCase):
    def _local_config(self, root):
        template = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
        config = yaml.safe_load(template.read_text(encoding="utf-8"))
        config["defaults"]["cache_root"] = str(root / "declared_cache")
        config["sources"]["legacy_raw_swc_root"] = None
        path = root / "config.yaml"
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
        return path

    def setUp(self):
        def sides(sample, neuron_ids, config):
            return {"status": "complete", "source": {"method": "fixture soma atlas"},
                    "results": {name: {"status": "verified", "side": "Right", "reason": "fixture",
                                       "source": {"atlas_region": "CR_M1"}}
                                for name in neuron_ids}}
        patcher = mock.patch("batch.prepare_review_bulk.acquire_neuron_sides", side_effect=sides)
        self.side_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_two_configured_missing_context_samples_freeze_intent(self):
        config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            loaded = load_config(config)
            loaded["path"] = None
            loaded["defaults"]["cache_root"] = root / "cache_root"
            loaded["sources"]["legacy_raw_swc_root"] = root / "cache_root" / "swc_raw"
            for sample in ("252383", "252718"):
                source = root / "sources" / sample
                source.mkdir(parents=True)
                (source / "001.swc").write_text("1 1 1 2 3 1 -1\n", encoding="utf-8")
                identities = root / f"{sample}.csv"
                identities.write_text(f"sample,neuron_id,portal_region\n{sample},001.swc,M1_79\n",
                                      encoding="utf-8")
                with mock.patch("batch.prepare_review_bulk.load", return_value=loaded):
                    plan = plan_jobs(config, sample, identities, False, [root / "sources"],
                                     root / "cache_root" / "swc_raw", None, 1, False)
                self.assertEqual(plan["jobs"][0]["context_source_status"],
                                 "missing_declared_5um_source")
                jobs_path = root / f"{sample}_jobs.json"
                with mock.patch("batch.prepare_review_bulk.load", return_value=loaded):
                    prepared = prepare_jobs(plan, jobs_path, dry_run=False, allow_download=False)
                self.assertEqual(prepared["status"], "prepared")
                frozen = json.loads(jobs_path.read_text(encoding="utf-8"))
                self.assertEqual(frozen["jobs"][0]["context_source_status"],
                                 "missing_declared_5um_source")

    def test_exact_sources_are_cached_and_frozen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources" / "251637"
            sources.mkdir(parents=True)
            first = sources / "001.swc"
            second = sources / "002.swc"
            first.write_text("1 1 1 2 3 1 -1\n", encoding="utf-8")
            second.write_text("1 1 4 5 6 1 -1\n", encoding="utf-8")
            identities = root / "identities.csv"
            identities.write_text("sample,neuron_id,ion_atlas,checked_region,portal_region\n"
                                  "251637,002.swc,M1_79,,M1_79\n"
                                  "251637,001.swc,M1_79,Right INS,M1_79\n")
            receipt = root / "sources.json"
            receipt.write_text(json.dumps({
                "sample_id": "251637", "raw_folder": str(sources), "manifest_count": 2,
                "source_files": [
                    {"id": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in (first, second)],
            }), encoding="utf-8")
            config = self._local_config(root)
            cache = root / "cache" / "swc_raw"
            jobs_path = root / "jobs" / "prepared.json"
            plan = plan_jobs(config, "251637", identities, False, [sources.parent], cache,
                             receipt, None, True)
            self.side_mock.assert_called_once()
            self.assertEqual(self.side_mock.call_args.args[1], ["001.swc", "002.swc"])
            self.assertEqual(plan["vispa_region_lookup"]["source"]["method"],
                             "fixture soma atlas")
            self.assertEqual((plan["selected_count"], plan["available_count"]), (2, 2))
            self.assertFalse(cache.exists())
            result = prepare_jobs(plan, jobs_path, dry_run=False, allow_download=False)
            self.assertEqual(result["status"], "prepared")
            jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
            self.assertEqual([job["neuron_id"] for job in jobs["jobs"]], ["001.swc", "002.swc"])
            self.assertEqual(jobs["jobs"][0]["soma_xyz"], [1.0, 2.0, 3.0])
            self.assertEqual(jobs["jobs"][1]["soma_xyz"], [4.0, 5.0, 6.0])
            self.assertEqual(jobs["jobs"][0]["soma_region"], "Right INS")
            self.assertEqual(jobs["jobs"][0]["soma_region_source"]["field"], "checked_region")
            self.assertEqual(jobs["jobs"][1]["soma_region"], "M1_79")
            self.assertEqual(jobs["jobs"][0]["neuron_folder"], "001_R_Right_INS_" +
                             hashlib.sha256("001_R_Right INS".encode()).hexdigest()[:8])
            self.assertEqual(jobs["jobs"][1]["neuron_folder"], "002_R_M1")
            self.assertEqual(jobs["output_layout"], "sample_neurons_flat")
            self.assertIsNone(jobs["jobs"][0]["source_acquisition_date"])
            self.assertIn("unknown", jobs["jobs"][0]["source_acquisition_date_status"])
            self.assertRegex(jobs["run_name"], r"^review_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")
            self.assertEqual(jobs["run_name"], plan["run_name"])
            render_plan = load_review_jobs(jobs_path, Path(jobs["figure_output_root"]), 1, False)
            self.assertEqual(Path(render_plan["jobs"][0]["output_dir"]).name,
                             jobs["jobs"][0]["neuron_folder"])
            self.assertEqual(Path(render_plan["jobs"][0]["output_dir"]).parent.name, "neurons")
            self.assertEqual(render_plan["jobs"][0]["soma_region"], "Right INS")
            self.assertEqual(render_plan["jobs"][0]["soma_region_entries"]["ion_atlas"], "M1_79")
            self.assertEqual(_region_display_value(render_plan["jobs"][0]),
                             "checked_region=Right INS | Portal: M1_79 | Atlas: Right M1")
            self.assertEqual(render_plan["jobs"][0]["vispa_region"]["status"], "verified")
            self.assertEqual(hashlib.sha256((cache / "251637/001.swc").read_bytes()).hexdigest(),
                             jobs["jobs"][0]["raw_swc_sha256"])

    def test_missing_cache_only_job_is_explicitly_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sources" / "251637"
            source.mkdir(parents=True)
            (source / "001.swc").write_text("1 1 1 2 3 1 -1\n", encoding="utf-8")
            identities = root / "identities.csv"
            identities.write_text("sample,neuron_id\n251637,001.swc\n251637,002.swc\n")
            config = self._local_config(root)
            plan = plan_jobs(config, "251637", identities, False, [source.parent],
                             root / "cache", None, None, True)
            self.assertEqual(plan["missing_count"], 1)
            result = prepare_jobs(plan, root / "jobs/prepared.json", dry_run=False,
                                  allow_download=False)
            self.assertEqual((result["status"], result["prepared_count"], result["failed_count"]),
                             ("partial", 1, 1))

    def test_catalog_source_is_frozen_by_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            snapshot = {"source_kind": "live-iondata", "sha256": "a" * 64,
                        "count": 1, "rows": [{"neuron_id": "001.swc", "portal_region": "M1_79"}]}
            with mock.patch("batch.prepare_review_bulk.list_neurons", return_value=snapshot):
                plan = plan_jobs(config, "251637", None, True, [], root / "cache",
                                 None, 1, False)
            self.assertEqual(plan["identity_source"]["sha256"], "a" * 64)
            self.assertEqual(plan["jobs"][0]["neuron_id"], "001.swc")
            self.assertEqual(plan["jobs"][0]["soma_region"], "M1_79")
            self.assertEqual(plan["jobs"][0]["soma_region_source"]["field"], "portal_region")
            with (mock.patch("batch.prepare_review_bulk.list_neurons", return_value=snapshot),
                  mock.patch("batch.prepare_review_bulk.acquire_neuron_sides",
                             side_effect=RuntimeError("offline"))):
                offline = plan_jobs(config, "251637", None, True, [], root / "cache",
                                    None, 1, False)
            self.assertEqual(offline["jobs"][0]["vispa_region"]["status"], "error")
            self.assertEqual(_region_display_value(offline["jobs"][0]),
                             "Portal: M1_79 | Atlas: unavailable")

    def test_region_union_filters_before_limit_and_unknown_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            snapshot = {"source_kind": "live-iondata", "sha256": "a" * 64, "count": 4,
                        "rows": [
                            {"neuron_id": "001.swc", "portal_region": "M1_79"},
                            {"neuron_id": "002.swc", "portal_region": "Other"},
                            {"neuron_id": "003.swc", "portal_region": "PMdc_82"},
                            {"neuron_id": "004.swc", "portal_region": "PMdc_82", "exclude": "yes"},
                        ]}
            with mock.patch("batch.prepare_review_bulk.list_neurons", return_value=snapshot):
                bounded = plan_jobs(config, "251637", None, True, [], root / "cache",
                                    None, 1, False, regions=["PMdc_82", "M1_79"])
                whole = plan_jobs(config, "251637", None, True, [], root / "cache",
                                  None, None, True, regions=["PMdc_82", "M1_79"])
                with self.assertRaisesRegex(ValueError, "Unknown atlas region"):
                    plan_jobs(config, "251637", None, True, [], root / "cache",
                              None, 1, False, regions=["Missing"])
            self.assertEqual([job["neuron_id"] for job in bounded["jobs"]], ["001.swc"])
            self.assertEqual([job["neuron_id"] for job in whole["jobs"]], ["001.swc", "003.swc"])
            self.assertEqual(whole["region_filter"]["labels"], ["M1_79", "PMdc_82"])
            self.assertEqual(whole["region_filter"]["source"]["sha256"], "a" * 64)
            self.assertTrue(whole["allow_all"])
            jobs_path = root / "jobs" / "filtered.json"
            jobs_path.parent.mkdir()
            jobs_path.write_text(json.dumps({
                "schema": "vispa.review_bulk.v1", "sample_id": "251637",
                "vispa_config": str(config), "allow_all": True,
                "region_filter": whole["region_filter"],
                "jobs": [{"sample_id": "251637", "neuron_id": "002.swc",
                          "soma_xyz": [1, 2, 3], "render_ready": True,
                          "soma_region_entries": {"portal_region": "Other"}}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from frozen region_filter"):
                load_review_jobs(jobs_path, root / "figures", 1, False)

    def test_checked_region_precedes_ion_atlas_and_preserves_entries(self):
        source = {"soma_region": {"checked_region": "Right INS", "ion_atlas": "M1_79",
                                  "other_entry": "retained"}, "portal_region": "M1_79"}
        entries = _region_entries(source)
        self.assertEqual(_selected_region(entries), ("Right INS", "soma_region.checked_region"))
        self.assertEqual(entries["soma_region"]["other_entry"], "retained")
        entries["soma_region"]["checked_region"] = ""
        self.assertEqual(_selected_region(entries), ("M1_79", "soma_region.ion_atlas"))
        self.assertEqual(_selected_region(_region_entries({"portal_region": "M1_79"})),
                         ("M1_79", "portal_region"))
        self.assertEqual(_region_display_value({"soma_region": "M1_79",
                                                "soma_region_source": {"field": "portal_region"}}),
                         "portal_region=M1_79")
        self.assertEqual(_region_display_value({"soma_region": "M1_79",
                                                "soma_region_entries": {"portal_region": "M1_79"},
                                                "soma_region_source": {"field": "portal_region"},
                                                "vispa_region": {"status": "verified", "side": "Right",
                                                                 "source": {"atlas_region": "CR_M1"}}}),
                     "Portal: M1_79 | Atlas: Right M1")
        self.assertEqual(region_display_label("M1_79", {"status": "verified", "side": "Right",
                                                         "source": {"atlas_region": "CR_M1"}}),
                     "Portal: M1_79 | Atlas: Right M1")
        self.assertEqual(region_display_label("M1_79", {"status": "error", "side": None,
                                                         "source": None}),
                         "Portal: M1_79 | Atlas: unavailable")
        with self.assertRaisesRegex(ValueError, "must be a string"):
            _selected_region(_region_entries({"soma_region": {"checked_region": ["M1_79"]}}))

    def test_legacy_name_and_unsafe_names(self):
        self.assertEqual(run_folder_name({}, "a" * 64), "bulk_aaaaaaaaaaaa")
        self.assertEqual(run_folder_name({"run_name": "review_2026-11-08_15-45-00"}, "a" * 64),
                         "review_2026-11-08_15-45-00")
        for name in ("../escape", "a/b", "a\\b", "", ".", "bad name", "CON", "com1", "LPT9"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_run_name(name)
        self.assertEqual(neuron_folder_name("252527", "011.swc", "M1_79", side="Right"), "011_R_M1")
        self.assertEqual(neuron_folder_name("252527", "011.swc", "PMdc_82", side="Left"), "011_L_PMdc")
        self.assertEqual(neuron_folder_name("252527", "011.swc", "area_7a_122"), "011_area_7a")
        self.assertEqual(neuron_folder_name("252527", "011.swc", None), "011_Unassigned")
        self.assertNotIn("/", neuron_folder_name("252527", "011.swc", "../../region"))

    def test_canonical_gui_cache_and_figure_root_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            config = load_config(config_path)
            config["defaults"]["cache_root"] = root / "managed"
            cache = root / "managed" / "swc_raw"
            config["sources"]["legacy_raw_swc_root"] = cache
            config["visual_toolkit"]["figure_output_root"] = root / "figures"
            swc = cache / "251637" / "001.swc"
            swc.parent.mkdir(parents=True)
            swc.write_text("1 1 1 2 3 1 -1\n", encoding="utf-8")
            before = hashlib.sha256(swc.read_bytes()).hexdigest()
            identities = root / "identities.csv"
            identities.write_text("sample,neuron_id,portal_region\n251637,001.swc,M1_79\n")
            jobs_path = root / "jobs" / "prepared.json"
            with mock.patch("batch.prepare_review_bulk.load", return_value=config):
                plan = plan_jobs(config_path, "251637", identities, False, [], cache,
                                 None, 1, False)
                result = prepare_jobs(plan, jobs_path, dry_run=False, allow_download=False)
            self.assertEqual(result["status"], "prepared")
            self.assertEqual(hashlib.sha256(swc.read_bytes()).hexdigest(), before)
            self.assertEqual(json.loads(jobs_path.read_text())["figure_output_root"], str(root / "figures"))
            BulkReviewDialog._validate_jobs(jobs_path, {
                "config": str(config_path), "sample": "251637", "regions": [],
                "cache": str(cache), "output": str(root / "figures"),
            }, require_exists=True)
            config["defaults"]["cache_root"] = root / "different-managed"
            with mock.patch("batch.prepare_review_bulk.load", return_value=config):
                with self.assertRaisesRegex(ValueError, "outside declared source roots"):
                    plan_jobs(config_path, "251637", identities, False, [], cache,
                              None, 1, False)

    def test_conflicting_neuron_receipt_blocks_resume_before_render(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            jobs_path = root / "jobs" / "jobs.json"
            jobs_path.parent.mkdir()
            jobs_path.write_text(json.dumps({
                "schema": "vispa.review_bulk.v1", "sample_id": "251637",
                "vispa_config": str(config), "output_layout": "sample_neurons",
                "run_name": "review_collision", "allow_all": False,
                "jobs": [{"sample_id": "251637", "neuron_id": "001.swc",
                          "soma_xyz": [1, 2, 3], "render_ready": True}],
            }), encoding="utf-8")
            plan = load_review_jobs(jobs_path, root / "figures", 1, False)
            folder = Path(plan["jobs"][0]["output_dir"])
            self.assertEqual(folder.parent.name, "001")
            folder.mkdir(parents=True)
            (folder / "review_receipt.json").write_text('{"job_sha256":"unrelated"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different job"):
                run_review_bulk(plan, dry_run=False, renderer=lambda *_: self.fail("rendered"), resume=True)

    def test_flat_render_uses_one_log_and_retains_history(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            jobs_path = root / "jobs" / "jobs.json"
            jobs_path.parent.mkdir()
            jobs_path.write_text(json.dumps({
                "schema": "vispa.review_bulk.v1", "sample_id": "251637",
                "vispa_config": str(config), "output_layout": "sample_neurons_flat",
                "run_name": "review_fixture", "allow_all": False,
                "figure_output_root": str(root / "figures"),
                "jobs": [{"sample_id": "251637", "neuron_id": "001.swc",
                          "neuron_folder": "001_R_M1", "soma_xyz": [1, 2, 3],
                          "render_ready": True}],
            }), encoding="utf-8")
            configured = load_config(config)
            configured["visual_toolkit"]["figure_output_root"] = root / "figures"
            configured["visual_toolkit"]["separate_plot_subfolder"] = "plots"
            output_root = root / "figures"
            with mock.patch("vispa.config.load", return_value=configured):
                plan = load_review_jobs(jobs_path, output_root, 1, False)
            def render(_job, folder, _config):
                paths = {}
                for role in ("Soma", "Context", "Sagittal", "TrioPlot"):
                    path = folder / f"{role}.png"
                    Image.new("RGB", (2, 2), "red").save(path)
                    paths[role] = str(path)
                (folder / "SomaBlock.nii.gz").write_bytes(b"fixture derivative")
                return {"outputs": paths, "errors": [],
                        "role_availability": {"Context": {
                            "status": "intentionally_unavailable",
                            "source_status": "missing_declared_5um_source"}}}
            with mock.patch("vispa.config.load", return_value=configured), mock.patch(
                    "vispa.review_bulk_render._verified_raw_path", return_value=None):
                first = run_review_bulk(plan, dry_run=False, renderer=render)
                self.assertEqual(first["status"], "pass", first.get("error"))
                log_path = output_root / "251637" / "process_log.json"
                record = json.loads(log_path.read_text(encoding="utf-8"))
                self.assertEqual(record["current_batch"]["source_jobs"][0]["neuron_id"], "001.swc")
                self.assertEqual(len(record["neurons"]["001.swc"]["current"]["outputs"]), 4)
                self.assertEqual(record["neurons"]["001.swc"]["current"]["role_availability"]
                                 ["Context"]["status"], "intentionally_unavailable")
                folder = Path(plan["jobs"][0]["output_dir"])
                self.assertEqual(folder.name, "001_R_M1")
                self.assertTrue((folder / "SomaBlock.nii.gz").is_file())
                self.assertTrue((folder / "TrioPlot.png").is_file())
                for role in ("Soma", "Context", "Sagittal"):
                    self.assertTrue((folder / "plots" / f"{role}.png").is_file())
                self.assertFalse((folder / "review_receipt.json").exists())
                self.assertFalse((output_root / "251637" / "bulk_runs").exists())
                with mock.patch("vispa.review_bulk_render.render_review_neuron", side_effect=AssertionError("rerendered")):
                    resumed = run_review_bulk(plan, dry_run=False, resume=True)
                self.assertEqual(resumed["completed"][0]["resume_action"], "verified_skip")
                second = run_review_bulk(plan, dry_run=False, renderer=render)
                self.assertEqual(second["status"], "pass")
                record = json.loads(log_path.read_text(encoding="utf-8"))
                self.assertEqual(len(record["neurons"]["001.swc"]["history"]), 1)
                self.assertGreaterEqual(len(record["batches"]), 2)

    def test_animal_log_preserves_brain_view_across_review_rerender(self):
        from vispa.render_records import (record_neuron_output, record_neuron_product,
                                          separate_plot_output_dir)
        self.assertEqual(separate_plot_output_dir(Path("neuron"),
                         {"visual_toolkit": {"separate_plot_subfolder": "plots"}}),
                         Path("neuron/plots"))
        with self.assertRaisesRegex(ValueError, "path-safe"):
            separate_plot_output_dir(Path("neuron"),
                                     {"visual_toolkit": {"separate_plot_subfolder": "../escape"}})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "251637" / "process_log.json"
            record_neuron_output(path, "251637", "001.swc", {
                "sample_id": "251637", "neuron_id": "001.swc", "status": "rendered_candidate",
                "outputs": {"Soma": {"path": "fixture"}}, "errors": []})
            record_neuron_product(path, "251637", "001.swc", "SWC3D",
                                  {"path": "brain-view.png", "sha256": "fixture-hash"})
            record_neuron_output(path, "251637", "001.swc", {
                "sample_id": "251637", "neuron_id": "001.swc", "status": "rendered_candidate",
                "outputs": {"Soma": {"path": "new-fixture"}}, "errors": []})
            slot = json.loads(path.read_text(encoding="utf-8"))["neurons"]["001.swc"]
            self.assertEqual(slot["current"]["products"]["SWC3D"]["path"], "brain-view.png")
            self.assertEqual(slot["current"]["outputs"]["Soma"]["path"], "new-fixture")
            self.assertEqual(len(slot["history"]), 2)

if __name__ == "__main__":
    unittest.main()
