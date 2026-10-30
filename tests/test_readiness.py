"""Checks for the public data-check API, CLI and GUI progress plumbing.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import contextlib
from collections import OrderedDict
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import vispa
from vispa import cli
from vispa.readiness import data_check


class DataCheckTests(unittest.TestCase):
    def _config(self, root):
        files = {
            "ds00.nii": b"ds00",
            "raw/0007/001.swc": b"1 1 0 0 0 1 -1\n",
            "mesh.obj": b"v 0 0 0\n",
            "processed/0007/001.swc": b"1 1 0 0 0 1 -1\n",
            "fnt.exe": b"exe",
            "fnt-from-swc.exe": b"converter fixture",
            "projects/0007_001.fnt": b"fnt",
        }
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        five_um = root / "five_um"
        five_um.mkdir()
        return {
            "path": root / "vispa.yaml",
            "defaults": {"cache_root": root / "cache"},
            "samples": {
                "0007": {
                    "ds00_processed": root / "ds00.nii",
                    "resample_5um": five_um,
                    "swc_cache": root / "raw" / "0007",
                }
            },
            "sources": {
                "http_host": "http://example.invalid",
                "raw_swc_base": "http://example.invalid/raw",
                "http_path": "images",
                "legacy_raw_swc_root": root / "raw",
                "brain_view": {
                    "mesh_path": root / "mesh.obj",
                    "processed_swc_root": root / "processed",
                },
            },
            "visual_toolkit": {
                "default_sample": "0007",
                "default_neuron": "001.swc",
                "fnt_tracer": {
                    "executable": root / "fnt.exe",
                    "converter_executable": root / "fnt-from-swc.exe",
                    "catalog_base_url": "https://example.org/monkeydata",
                    "project_root": root / "projects",
                },
            },
        }

    def test_public_api_reports_full_checklist_and_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            progress = []
            report = data_check(
                config, progress=lambda done, total: progress.append((done, total)))
            self.assertIs(vispa.check, data_check)
            self.assertTrue(report["ready"], report["checklist"])
            self.assertEqual(report["checked"], 15)
            self.assertEqual(progress[-1], (15, 15))
            self.assertEqual(progress, [(index, 15) for index in range(1, 16)])
            self.assertTrue(any(
                line.startswith("[OK] DS00 image:")
                and str(root / "ds00.nii") in line
                for line in report["checklist"]))
            self.assertTrue(any(item["role"] == "download_cache" and
                                item["status"] == "ready" for item in report["checks"]))
            self.assertTrue(any(item["role"] == "fnt_native" and
                                item["status"] == "configured" and
                                "can be prepared" in item["detail"] for item in report["checks"]))
            self.assertFalse((root / "cache").exists())

    def test_manual_project_alone_does_not_satisfy_native_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            (root / "fnt-from-swc.exe").unlink()
            report = data_check(config)
            self.assertFalse(report["ready"])
            self.assertTrue((root / "projects" / "0007_001.fnt").is_file())
            self.assertTrue(any(item["role"] == "fnt_native" and item["status"] == "missing"
                                for item in report["checks"]))

    def test_optional_region_dependencies_are_checked_as_directory_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            region_root = root / "regions"
            region_root.mkdir()
            manifest = region_root / "region_mesh_manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            config["sources"]["brain_view"].update(
                region_mesh_root=region_root, region_manifest=manifest)
            progress = []
            report = data_check(
                config, progress=lambda done, total: progress.append((done, total)))
            self.assertTrue(report["ready"], report["checklist"])
            self.assertEqual(report["checked"], 17)
            self.assertEqual(progress[-1], (17, 17))
            region = next(item for item in report["checks"]
                          if item["role"] == "region_mesh_root")
            self.assertEqual(region["status"], "ready")
            self.assertEqual(region["detail"], "Found")

    def test_ds00_uses_manifest_selected_source_without_hashing_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            selected = root / "selected.nii.gz"
            selected.write_bytes(b"selected DS00")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"selected_preprocessed_outputs": [{
                "sample": "0007", "relative_path": selected.name,
                "sha256": hashlib.sha256(selected.read_bytes()).hexdigest()}]}), encoding="utf-8")
            config["defaults"]["ds00_root"] = root
            config["sources"]["dataset_manifest"] = manifest
            config["samples"]["0007"]["ds00_processed"] = selected
            report = data_check(config)
            ds00 = next(item for item in report["checks"] if item["role"] == "ds00")
            self.assertEqual(ds00["path"], str(selected.resolve()))
            self.assertTrue(report["ready"])
            self.assertFalse(ds00["checksum_verified"])
            self.assertEqual(ds00["declared_sha256"], hashlib.sha256(selected.read_bytes()).hexdigest())
            config["samples"]["0007"]["ds00_processed"] = root / "ds00.nii"
            historical = data_check(config)
            self.assertTrue(historical["ready"])
            selected_item = next(item for item in historical["checks"] if item["role"] == "ds00")
            self.assertEqual(selected_item["path"], str(selected.resolve()))
            self.assertEqual(selected_item["configured_reference_path"], str(root / "ds00.nii"))
            self.assertEqual(selected_item["selection_basis"], "dataset manifest")
            config["samples"]["0007"]["ds00_processed"] = selected
            selected.unlink()
            self.assertFalse(data_check(config)["ready"])

    def test_processed_cache_is_not_native_raw_swc(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            config["samples"]["0007"]["swc_cache"] = root / "processed" / "0007"
            config["sources"]["raw_swc_base"] = "https://example.org/raw"
            (root / "raw" / "0007" / "001.swc").unlink()
            report = data_check(config)
            raw = next(item for item in report["checks"] if item["role"] == "raw_swc_retrieval")
            self.assertEqual(raw["status"], "missing")
            self.assertIn("retrieval required", raw["detail"])
            self.assertFalse(report["ready"])

    def test_missing_context_directory_fails_the_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            (root / "five_um").rmdir()
            report = data_check(config)
            self.assertFalse(report["ready"])
            self.assertTrue(any(
                line.startswith("[MISSING] 5 um Context sections:")
                for line in report["checklist"]))

    def test_cli_check_json_uses_public_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            config_path = root / "vispa.json"
            import json
            config_path.write_text(json.dumps({
                "version": 1,
                "base_dir": str(root),
                "defaults": {"cache_root": str(root / "cache")},
                "samples": {"0007": {
                    "ds00_processed": "ds00.nii",
                    "resample_5um": "five_um",
                    "swc_cache": "raw/0007",
                }},
                "sources": {
                    "http_host": "http://example.invalid",
                    "raw_swc_base": "http://example.invalid/raw",
                    "http_path": "images",
                    "legacy_raw_swc_root": "raw",
                    "brain_view": {
                        "mesh_path": "mesh.obj",
                        "processed_swc_root": "processed",
                    },
                },
                "visual_toolkit": {
                    "default_sample": "0007",
                    "default_neuron": "001.swc",
                    "fnt_tracer": {
                        "executable": "fnt.exe",
                        "converter_executable": "fnt-from-swc.exe",
                        "catalog_base_url": "https://example.org/monkeydata",
                        "project_root": "projects",
                    },
                },
            }), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = cli.main(["check", "--config", str(config_path), "--json"])
        self.assertEqual(result, 0)
        self.assertIn('"schema": "vispa.data-check.v1"', output.getvalue())
        self.assertIn('"ready": true', output.getvalue())


class ProgressBarTests(unittest.TestCase):
    def test_determinate_resource_check_uses_progress_bar(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.progress = mock.Mock()
        gui.root = mock.Mock()
        gui._show_progress(maximum=15)
        gui._set_progress(4, 15)
        gui._hide_progress()
        gui.progress.configure.assert_any_call(
            mode="determinate", maximum=15, value=4)
        gui.progress.pack.assert_called_with(side="right", padx=14, pady=6)
        gui.progress.start.assert_not_called()
        gui.progress.stop.assert_called()
        gui.progress.pack_forget.assert_called_once()

    def test_low_resolution_section_cache_reuses_and_evicts(self):
        from vispa import toolkit

        tool = toolkit.VisPa.__new__(toolkit.VisPa)
        tool.low_res_slice_cache_limit = 1
        tool._section_cache = OrderedDict()
        calls = []

        def fake_read(path):
            calls.append(path)
            return object()

        with mock.patch.object(toolkit, "_read_tiff", side_effect=fake_read):
            first = tool._read_cached_section("first.tif")
            self.assertIs(tool._read_cached_section("first.tif"), first)
            tool._read_cached_section("second.tif")
            tool._read_cached_section("second.tif")
        self.assertEqual(calls, ["first.tif", "second.tif"])
        self.assertEqual(list(tool._section_cache), [str(Path("second.tif").resolve())])

    def test_ready_checklist_is_shown_as_a_structured_gui_dialog(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "0007"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "001.swc"
        gui._hide_progress = mock.Mock()
        gui._append_log = mock.Mock()
        gui.update_status = mock.Mock()
        gui._show_data_check = mock.Mock()
        gui._auto_fill_on_identity = False
        gui.root = mock.Mock()
        report = {
            "ready": True,
            "checked": 2,
            "issues": 0,
            "checklist": ["[OK] DS00 image: Found", "[OK] Download cache: Writable"],
            "summary": "All configured resources ready (2/2)",
            "checks": [
                {"role": "ds00", "label": "DS00 image", "status": "ready",
                 "detail": "Found", "path": r"\\server\ds00.nii"},
                {"role": "download_cache", "label": "Download cache",
                 "status": "ready", "detail": "Writable", "path": r"C:\cache"},
            ],
        }
        gui._finish_resource_check(("0007", "001.swc"), report, None)
        gui._show_data_check.assert_called_once_with(report)
        gui.update_status.assert_called_with("All configured resources ready (2/2)")
        self.assertEqual(gui.last_data_check, report)

    def test_swc3d_tab_requests_a_snapshot_when_not_cached(self):
        from vispa.gui import (NeuroVisGUI, SWC_BRAIN_VIEW_LABEL,
                               SWC_BRAIN_VIEW_INTERACTIVE_LABEL)

        self.assertEqual(SWC_BRAIN_VIEW_LABEL, "SWC Brain View")
        self.assertEqual(SWC_BRAIN_VIEW_INTERACTIVE_LABEL,
                         "SWC Brain View interactive")
        gui = object.__new__(NeuroVisGUI)
        gui.preview_files = {}
        gui._render_swc3d = mock.Mock()
        gui._show_role("SWC3D")
        gui._render_swc3d.assert_called_once_with()

    def test_swc3d_callback_builds_snapshot_and_runs_worker(self):
        from vispa.reviewer import NeuroVisGUI

        with tempfile.TemporaryDirectory() as folder:
            gui = object.__new__(NeuroVisGUI)
            gui._operation_running = False
            gui.sample_id = mock.Mock()
            gui.sample_id.get.return_value = "251637"
            gui.neuron_id = mock.Mock()
            gui.neuron_id.get.return_value = "004.swc"
            gui._current_portal_region = mock.Mock(return_value="PrCO")
            gui.save_outputs = mock.Mock()
            gui.save_outputs.get.return_value = True
            gui.output_dir = mock.Mock()
            gui.output_dir.get.return_value = folder
            gui.config_path = "fixture.yaml"
            gui.update_status = mock.Mock()
            gui._show_progress = mock.Mock()
            gui._hide_progress = mock.Mock()
            gui._finish_swc3d = mock.Mock()
            gui._ui_call = lambda callback, *args: callback(*args)
            gui._launch_processing = lambda worker: worker()
            with mock.patch(
                    "vispa.renderers.swc_brain_view.render_configured_snapshot",
                    return_value={"receipt": str(Path(folder) / "receipt.json")}
            ) as render:
                gui._render_swc3d()
            render.assert_called_once()
            args, kwargs = render.call_args
            self.assertEqual(args[:2], ("251637", "004.swc"))
            self.assertTrue(args[2].endswith("_3D_SWC.png"))
            self.assertEqual(kwargs, {"portal_region": "PrCO",
                                      "config_path": "fixture.yaml"})
            gui._finish_swc3d.assert_called_once_with(
                "251637", "004.swc", args[2],
                str(Path(folder) / "receipt.json"), True)

    def test_render_requires_loaded_soma_not_zero_placeholder(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui._autofill_identity = None
        for coordinates in (("", "", ""), ("0", "0", "0")):
            with self.subTest(coordinates=coordinates):
                gui.x_coord = mock.Mock()
                gui.y_coord = mock.Mock()
                gui.z_coord = mock.Mock()
                gui.x_coord.get.return_value, gui.y_coord.get.return_value, gui.z_coord.get.return_value = coordinates
                with mock.patch("vispa.gui.messagebox.showwarning") as warning:
                    self.assertFalse(gui.validate_inputs())
                self.assertEqual(warning.call_args.args[0], "Load soma first")

    def test_valid_identity_change_schedules_live_soma_lookup(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui._selected_identity = ("old", "001.swc")
        gui._auto_fill_on_identity = True
        gui._autofill_identity = ("old", "001.swc")
        gui._soma_autofill_after = None
        gui.x_coord = mock.Mock()
        gui.y_coord = mock.Mock()
        gui.z_coord = mock.Mock()
        gui._clear_identity_preview = mock.Mock()
        gui._update_neuron_status = mock.Mock()
        gui.root = mock.Mock()
        gui.root.after.return_value = "after-id"
        gui._on_identity_change()
        gui.x_coord.set.assert_called_once_with("")
        gui.y_coord.set.assert_called_once_with("")
        gui.z_coord.set.assert_called_once_with("")
        self.assertEqual(gui.root.after.call_args.args[0], 650)
        self.assertEqual(
            gui.root.after.call_args.args[1].__self__,
            gui,
        )

    def test_neuron_status_reports_found_identity_and_portal_region(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui._portal_region_cache = {"251637": {"004.swc": "PrCO_49"}}
        gui._neuron_lookup_state = "found"
        gui.neuron_status_var = mock.Mock()
        gui._update_neuron_status()
        gui.neuron_status_var.set.assert_called_once_with(
            "Neuron: found · PrCO_49")


if __name__ == "__main__":
    unittest.main()
