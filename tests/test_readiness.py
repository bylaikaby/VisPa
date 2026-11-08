"""Checks for the public data-check API, CLI and GUI progress plumbing.

Version: 1.21.2 (local/unreleased)
Last updated: 2026-11-08
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
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import vispa
from vispa import cli
from vispa.readiness import data_check


class DataCheckTests(unittest.TestCase):
    def _config(self, root):
        files = {
            "ds00.nii": b"ds00",
            "raw/0007/001.swc": b"1 1 0 0 0 1 -1\n",
            "mesh.obj": b"v 0 0 0\n",
            "cache/swc_processed/0007/001.swc": b"1 1 0 0 0 1 -1\n",
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
            with mock.patch("vispa.updates.load_updates", return_value={
                "matches_installed": True,
                "installed_version": vispa.__version__,
                "latest_version": vispa.__version__,
            }):
                report = data_check(
                    config, progress=lambda done, total: progress.append((done, total)))
            self.assertIs(vispa.check, data_check)
            self.assertTrue(report["ready"], report["checklist"])
            self.assertEqual(report["checked"], 16)
            self.assertEqual(progress[-1], (16, 16))
            self.assertEqual(progress, [(index, 16) for index in range(1, 17)])
            self.assertTrue(any(
                line.startswith("[OK] DS00 image:")
                and str(root / "ds00.nii") in line
                for line in report["checklist"]))
            self.assertTrue(any(item["role"] == "download_cache" and
                                item["status"] == "ready" for item in report["checks"]))
            processed = next(item for item in report["checks"] if item["role"] == "processed_swc")
            self.assertEqual(processed["path"], str(root / "cache/swc_processed/0007/001.swc"))
            self.assertEqual(processed["detail"], "Managed cache found; source receipt absent")
            self.assertTrue(any(item["role"] == "fnt_native" and
                                item["status"] == "configured" and
                                "can be prepared" in item["detail"] for item in report["checks"]))
            update = next(item for item in report["checks"]
                          if item["role"] == "update_status")
            self.assertFalse(update["required"])
            self.assertEqual(update["status"], "ready")
            self.assertEqual((root / "cache/swc_processed/0007/001.swc").read_bytes(),
                             b"1 1 0 0 0 1 -1\n")

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

    def test_processed_cache_receipt_role_and_absent_fetch_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = self._config(root)
            swc = root / "cache/swc_processed/0007/001.swc"
            receipt = swc.with_name(swc.name + ".source.json")
            receipt.write_text(json.dumps({"role": "processed", "sample_id": "0007",
                                           "neuron_id": "001.swc"}), encoding="utf-8")
            item = next(row for row in data_check(config)["checks"]
                        if row["role"] == "processed_swc")
            self.assertEqual(item["source_receipt_path"], str(receipt))
            self.assertEqual(item["source_receipt_role"], "processed")
            self.assertTrue(item["source_receipt_identity_matches"])
            swc.unlink()
            item = next(row for row in data_check(config)["checks"]
                        if row["role"] == "processed_swc")
            self.assertEqual(item["status"], "missing")
            self.assertIn("fetch on Brain View execution", item["detail"])

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
            self.assertEqual(report["checked"], 18)
            self.assertEqual(progress[-1], (18, 18))
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
    def test_runtime_version_message_reports_compact_config_identity(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.test_mode = False
        gui.version_report = {
            "vispa_version": "1.13.0.dev12",
            "config_name": "ded_vispa_config",
            "config_version": "1.0.4",
            "config_updated_at": "2026-11-04T15:37:24+08:00",
            "config_path": r"D:\VisPa\config\ded_vispa_config_v1.0.6.yaml",
            "config_origin": "explicit",
            "config_sha256": "a" * 64,
            "test_mode": False,
            "resolved_output_root": r"\\server\output",
            "resolved_cache_root": r"D:\VisPa\cache",
        }
        text = gui._runtime_version_message()
        self.assertIn("VisPa: 1.13.0.dev12", text)
        self.assertIn("Config: ded_vispa_config 1.0.4", text)
        self.assertIn("Config updated: 2026-11-04T15:37:24+08:00", text)
        self.assertNotIn("Latest config log", text)

    def test_version_display_separates_app_and_config_versions(self):
        from vispa.reviewer import NeuroVisGUI
        report = {
            "vispa_version": "1.13.0.dev15",
            "config_name": "vispa_config",
            "config_version": "unversioned",
            "config_updated_at": "2026-11-04T15:48:44+08:00",
        }
        self.assertEqual(
            NeuroVisGUI._version_display_rows(report)[0],
            ("APP VERSION", "VisPa 1.13.0.dev15"))
        config_row = NeuroVisGUI._version_display_rows(report)[1]
        self.assertEqual(config_row[0], "CONFIG VERSION")
        self.assertIn("vispa_config · unversioned", config_row[1])
        self.assertIn("Updated: 2026-11-04T15:48:44+08:00", config_row[1])

    def test_update_uses_cached_rendering_without_prompt(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.root = mock.Mock()
        gui.root.winfo_exists.return_value = True
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui.update_status = mock.Mock()
        gui.output_root = r"D:\output"
        gui.preview_files = {}
        gui._refresh_preview_tabs = mock.Mock()
        gui._show_role = mock.Mock()
        gui._update_neuron_status = mock.Mock()
        gui._start_fnt_fetch = mock.Mock()
        gui._evaluate_cached = mock.Mock(return_value=("same", []))
        gui._find_cached_figures = mock.Mock(return_value=(
            [r"D:\output\251637_20261104"],
            {"Soma": r"D:\output\251637_20261104\251637_004_Soma_Plot.png"},
            {"fingerprint": {}}))
        with mock.patch("vispa.gui.messagebox.askyesno",
                        side_effect=AssertionError("reload must not prompt")):
            gui._reload_existing()
        self.assertIn("Soma", gui.preview_files)
        self.assertEqual(gui._cache_status, "cached: current (1 figure)")
        self.assertIn("Loaded cached rendering data from output", gui.update_status.call_args.args[0])

    def test_neuron_status_includes_cache_state(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui._portal_region_cache = {}
        gui._neuron_side_cache = {}
        gui._neuron_lookup_state = "found"
        gui._cache_status = "cached: current (1 figure)"
        gui._set_neuron_status = mock.Mock()
        gui._set_region_status = mock.Mock()
        gui._update_neuron_status()
        gui._set_neuron_status.assert_called_once_with(
            "Neuron status: found · cached")

    def test_neuron_status_omits_cache_miss_detail(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui._portal_region_cache = {}
        gui._neuron_side_cache = {}
        gui._neuron_lookup_state = "found"
        gui._cache_status = "cached: none"
        gui._set_neuron_status = mock.Mock()
        gui._set_region_status = mock.Mock()
        gui._update_neuron_status()
        gui._set_neuron_status.assert_called_once_with("Neuron status: found")

    def test_update_rerenders_stale_settings_without_new_acquisition(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.root = mock.Mock()
        gui.root.winfo_exists.return_value = True
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui.update_status = mock.Mock()
        gui.output_root = r"D:\output"
        gui.run_selected = mock.Mock()
        gui._update_neuron_status = mock.Mock()
        gui._find_cached_figures = mock.Mock(return_value=(
            [r"D:\output\251637_20261104"],
            {"Soma": r"D:\output\251637_20261104\251637_004_Soma_Plot.png"},
            {"fingerprint": {}}))
        gui._evaluate_cached = mock.Mock(return_value=("differs", ["settings changed"]))
        gui._reload_existing()
        gui.run_selected.assert_called_once_with(force_rerender=True)

    def test_update_action_refreshes_swc_then_rerenders_from_acquisition_cache(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.load_and_autofill = mock.Mock()
        gui._update_neuron_status = mock.Mock()
        gui.update_status = mock.Mock()
        gui.run_selected = mock.Mock()
        gui._update_current_identity()
        callback = gui.load_and_autofill.call_args.kwargs["after_load"]
        callback("251637", "004.swc")
        gui.run_selected.assert_called_once_with(
            force_rerender=True, force_reprocess=False)
        self.assertEqual(gui._cache_status, "cached: updating figures")

    def test_reprocess_propagates_acquisition_bypass(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui._operation_running = False
        gui._capture_processing_request = mock.Mock(return_value=mock.Mock())
        gui._begin_render_preview = mock.Mock()
        gui._run_worker = mock.Mock()
        gui.run_selected(
            roles=("Soma", "Context", "Sagittal"),
            force_review_figure=True, force_reprocess=True)
        self.assertTrue(gui._run_worker.call_args.kwargs["force_reprocess"])

    def test_sagittal_hint_preserves_fractional_spacing_from_filename(self):
        from vispa.gui import NeuroVisGUI
        from vispa.renderers import microscopy_panels

        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "252383"
        gui.sagittal_hint = mock.Mock()
        with mock.patch.dict(microscopy_panels.SAMPLE_PATHS, {
                "252383": {"ds00_processed":
                           "sample-252383_100x100x89.56_orient-LPS.nii"}}):
            gui._refresh_sagittal_hint()
        text = gui.sagittal_hint.configure.call_args.kwargs["text"]
        self.assertIn("100×100×89.56 µm", text)
        self.assertNotIn("filename declares", text)
        self.assertNotIn("orientation", text)

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

    def test_reprocess_bypasses_low_resolution_disk_cache(self):
        from vispa import toolkit
        with tempfile.TemporaryDirectory() as folder:
            tool = toolkit.VisPa.__new__(toolkit.VisPa)
            tool.sample_id = "251637"
            tool.low_res_share_candidates = []
            tool.cache_ssh_dir = folder
            tool.low_res_ssh_base = None
            tool._slice_sources = {}
            cached = Path(folder) / "251637_00001_CH1_resample.tif"
            cached.write_bytes(b"cache")

            tool.force_reprocess = False
            self.assertEqual(tool._get_low_res_slice_path(1), str(cached))
            tool.force_reprocess = True
            self.assertIsNone(tool._get_low_res_slice_path(1))

    def test_reprocess_ignores_high_resolution_cube_cache(self):
        from vispa import toolkit
        from vispa.renderers import microscopy_panels
        with tempfile.TemporaryDirectory() as folder:
            tool = toolkit.VisPa.__new__(toolkit.VisPa)
            tool.sample_id = "251637"
            tool.cache_http_dir = folder
            tool.force_reprocess = True
            tool._block_errors = {}
            cached = Path(folder) / "0" / "0_0_0.tif"
            cached.parent.mkdir()
            cached.write_bytes(b"old-cache")
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = b"fresh-cube"
            block_shape = tuple(reversed(microscopy_panels.BLOCK_SIZE_PIXELS))
            with mock.patch.object(microscopy_panels, "HTTP_HOST", "http://example.test"), \
                 mock.patch.object(microscopy_panels, "HTTP_PATH", ""), \
                 mock.patch.object(microscopy_panels, "HTTP_ATTEMPTS", 1), \
                 mock.patch.object(microscopy_panels.urllib.request, "urlopen",
                                   return_value=response) as urlopen, \
                 mock.patch.object(
                     microscopy_panels, "_read_highres_cube",
                     return_value=np.zeros(block_shape, dtype=np.uint16)):
                tool._download_http_block(0, 0, 0)
            urlopen.assert_called_once()
            self.assertEqual(cached.read_bytes(), b"fresh-cube")

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

    def test_startup_check_prompts_when_a_new_version_is_parsed(self):
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
        update = {
            "role": "update_status",
            "label": "Version/update check",
            "required": False,
            "status": "update_available",
            "detail": "Installed 1.13.0.dev16; latest parsed 1.13.0.dev17",
        }
        report = {
            "ready": True, "checked": 1, "issues": 0,
            "checklist": ["[UPDATE] Version/update check: " + update["detail"]],
            "summary": "All configured resources ready (1/1)",
            "checks": [update],
        }
        with mock.patch("vispa.reviewer.messagebox.showinfo") as showinfo:
            gui._finish_resource_check(("0007", "001.swc"), report, None)
        showinfo.assert_called_once()
        self.assertIn("1.13.0.dev16", showinfo.call_args.args[1])
        self.assertIn("1.13.0.dev17", showinfo.call_args.args[1])
        gui._show_data_check.assert_called_once_with(report)

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

    def test_moved_action_buttons_use_outlined_shadow_style(self):
        from vispa.gui import NeuroVisGUI, SWC_BRAIN_VIEW_INTERACTIVE_LABEL
        gui = object.__new__(NeuroVisGUI)
        with mock.patch("vispa.gui.tk.Button") as button:
            gui._flat_button(
                mock.Mock(), SWC_BRAIN_VIEW_INTERACTIVE_LABEL,
                mock.Mock(), primary=True)
        options = button.call_args.kwargs
        self.assertEqual(options["relief"], "raised")
        self.assertEqual(options["bd"], 1)
        self.assertEqual(options["highlightthickness"], 1)

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
            gui._append_log = mock.Mock()
            gui.preview_label = mock.Mock()
            gui.preview_caption = mock.Mock()
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
            gui.preview_label.configure.assert_called_once_with(
                image='', text='Rendering SWC Brain View…')
            gui.preview_caption.set.assert_called_once_with(
                'SWC Brain View · 251637/004.swc · rendering')

    def test_open_output_folder_uses_saving_field_after_preview(self):
        from vispa.reviewer import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.current_preview = r'C:\temp\visual_toolkit_preview\deleted.png'
        gui.output_dir = mock.Mock()
        gui.output_dir.get.return_value = r'C:\review\saved_outputs'
        gui.update_status = mock.Mock()
        gui._append_log = mock.Mock()
        with mock.patch('vispa.reviewer.os.makedirs') as mkdir, mock.patch(
                'vispa.reviewer.os.startfile', create=True) as start:
            gui._open_output_folder()
        expected = str(Path(r'C:\review\saved_outputs').absolute())
        mkdir.assert_called_once_with(expected, exist_ok=True)
        start.assert_called_once_with(expected)
        gui.update_status.assert_called_once_with(f'Opened output folder: {expected}')

    def test_operation_log_records_activated_script_command_and_pid(self):
        from vispa.reviewer import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui._append_log = mock.Mock()
        gui._ui_call = lambda callback, *args: callback(*args)

        gui._log_operation(
            "FNT tools", "started",
            command=["C:\\tools\\fnt-tracer.exe", "C:\\cache\\004.swc.fnt"],
            pid=1234, project="C:\\cache\\004.swc.fnt")

        line = gui._append_log.call_args.args[0]
        self.assertTrue(line.startswith("[STARTED] FNT tools"))
        self.assertIn("fnt-tracer.exe", line)
        self.assertIn("004.swc.fnt", line)
        self.assertIn("pid=1234", line)

    def test_swc3d_failure_replaces_loading_state(self):
        from vispa.reviewer import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = '251637'
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = '004.swc'
        gui.preview_label = mock.Mock()
        gui.preview_caption = mock.Mock()
        gui.update_status = mock.Mock()
        gui._append_log = mock.Mock()
        gui._show_swc3d_error('251637', '004.swc', 'worker exited')
        gui.preview_label.configure.assert_called_once_with(
            image='', text='SWC Brain View failed:\nworker exited')
        gui.preview_caption.set.assert_called_once_with(
            'SWC Brain View · 251637/004.swc · failed')

    def test_neuron_catalog_geometry_fits_screen_at_high_dpi(self):
        from vispa.reviewer import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.scale = 2.0
        gui.root = mock.Mock()
        gui.root.winfo_vrootx.return_value = 0
        gui.root.winfo_vrooty.return_value = 0
        gui.root.winfo_vrootwidth.return_value = 1920
        gui.root.winfo_vrootheight.return_value = 1080
        gui.root.winfo_rootx.return_value = -300
        gui.root.winfo_rooty.return_value = -200
        gui.root.winfo_width.return_value = 1000
        gui.root.winfo_height.return_value = 800
        width, height, x, y = gui._catalog_geometry(900, 1000)
        self.assertEqual((width, height), (1120, 984))
        self.assertGreaterEqual(x, 48)
        self.assertGreaterEqual(y, 48)
        self.assertLessEqual(x + width, 1920 - 48)
        self.assertLessEqual(y + height, 1080 - 48)

    def test_settings_wheel_binds_across_child_widgets(self):
        from vispa.reviewer import NeuroVisGUI

        handler = mock.Mock(return_value="break")
        leaf = mock.Mock()
        leaf.winfo_children.return_value = ()
        branch = mock.Mock()
        branch.winfo_children.return_value = (leaf,)
        gui = object.__new__(NeuroVisGUI)

        gui._bind_settings_wheel(branch, handler)

        branch.bind.assert_called_once_with('<MouseWheel>', handler)
        leaf.bind.assert_called_once_with('<MouseWheel>', handler)

    def test_settings_wheel_handler_scrolls_one_unit_each_direction(self):
        from vispa.reviewer import NeuroVisGUI

        canvas = mock.Mock()
        canvas.winfo_exists.return_value = True
        handler = NeuroVisGUI._settings_wheel_handler(canvas)

        self.assertEqual(handler(mock.Mock(delta=120)), "break")
        canvas.yview_scroll.assert_called_with(-1, "units")
        canvas.yview_scroll.reset_mock()
        self.assertEqual(handler(mock.Mock(delta=-120)), "break")
        canvas.yview_scroll.assert_called_with(1, "units")

    def test_render_preview_replaces_old_image_and_failure_message(self):
        from vispa.reviewer import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.preview_label = mock.Mock()
        gui.preview_caption = mock.Mock()
        gui.root = mock.Mock()
        gui._preview_after = 'old-resize'
        gui.preview_files = {'Soma': 'old.png'}
        gui._ephemeral_images = {'Soma': object()}
        gui.current_preview = 'old.png'
        gui._preview_photo = object()
        gui._refresh_preview_tabs = mock.Mock()
        gui.update_status = mock.Mock()
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = '251637'
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = '005.swc'
        request = SimpleNamespace(sample_id='251637', neuron_id='005.swc')
        gui._begin_render_preview(request)
        self.assertEqual(gui.preview_files, {})
        self.assertIsNone(gui.current_preview)
        gui.root.after_cancel.assert_called_once_with('old-resize')
        gui.preview_label.configure.assert_called_with(
            image='', text='Rendering figures…\nPlease wait.')
        gui._show_render_failure(request, 'source missing')
        gui.preview_label.configure.assert_called_with(
            image='', text='No figures rendered.\nsource missing')

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

    def test_soma_fill_checks_iondata_by_default_and_cache_only_when_requested(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui.root = mock.Mock()
        gui.root.after.side_effect = lambda delay, callback: callback()
        gui.x_coord = mock.Mock()
        gui.y_coord = mock.Mock()
        gui.z_coord = mock.Mock()
        gui._update_neuron_status = mock.Mock()
        gui.update_status = mock.Mock()
        gui._show_progress = mock.Mock()
        gui._hide_progress = mock.Mock()
        gui._activate_cached_figures = mock.Mock()
        gui._ui_call = lambda callback, *args: callback(*args)
        gui._launch_processing = lambda worker: worker()
        tree = SimpleNamespace(root=SimpleNamespace(x=1.5, y=2.5, z=3.5))
        with mock.patch("vispa.gui.IT.IONData") as provider:
            provider.return_value.getRawNeuronTreeByID.return_value = tree
            gui.load_and_autofill(silent_success=True)
            provider.return_value.getRawNeuronTreeByID.assert_called_with(
                "251637", "004.swc", refresh=True)
            gui.load_and_autofill(silent_success=True, refresh=False)
            provider.return_value.getRawNeuronTreeByID.assert_called_with(
                "251637", "004.swc", refresh=False)
        gui.x_coord.set.assert_called_with("1.5")
        self.assertIn("local cache", gui.update_status.call_args.args[0])
        gui._activate_cached_figures.assert_called_with(
            "251637", "004", quiet=False, start_fnt=False)

    def test_neuron_status_reports_found_identity_and_portal_region(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui._portal_region_cache = {"251637": {"004.swc": "PrCO_49"}}
        gui._neuron_side_pending = {("251637", "004.swc")}
        gui._neuron_lookup_state = "found"
        gui._cache_status = "cached: checking"
        gui.neuron_status_var = mock.Mock()
        gui.region_status_var = mock.Mock()
        gui._update_neuron_status()
        gui.neuron_status_var.set.assert_called_once_with(
            "Neuron status: found")
        gui.region_status_var.set.assert_called_once_with(
            "Region: PrCO_49 · side unverified")

    def test_neuron_side_uses_exact_workbook_result_not_portal_index(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = '251637'
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = '004.swc'
        gui._portal_region_cache = {'251637': {'004.swc': 'PrCO_49'}}
        gui._neuron_side_cache = {('251637', '004.swc'): {
            'status': 'verified', 'side': 'Right'}}
        gui._neuron_lookup_state = 'found'
        gui.neuron_status_var = mock.Mock()
        gui.region_status_var = mock.Mock()
        gui._update_neuron_status()
        gui.region_status_var.set.assert_called_once_with(
            'Region: Right PrCO_49')

    def test_nmt_coordinate_row_uses_vispa_side_atlas_voxel(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "004.swc"
        gui.nmt_x = mock.Mock()
        gui.nmt_y = mock.Mock()
        gui.nmt_z = mock.Mock()
        gui._neuron_side_cache = {
            ("251637", "004.swc"): {
                "status": "verified",
                "side": "Right",
                "source": {"atlas_voxel": [192, 217, 83]},
            },
        }
        gui._neuron_side_pending = set()
        gui._update_nmt_coordinate_display()
        gui.nmt_x.set.assert_called_once_with("192")
        gui.nmt_y.set.assert_called_once_with("217")
        gui.nmt_z.set.assert_called_once_with("83")

    def test_nmt_coordinate_row_shows_pending_then_clears(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "005.swc"
        gui.nmt_x = mock.Mock()
        gui.nmt_y = mock.Mock()
        gui.nmt_z = mock.Mock()
        gui._neuron_side_cache = {}
        gui._neuron_side_pending = {("251637", "005.swc")}
        gui._update_nmt_coordinate_display()
        gui.nmt_x.set.assert_called_once_with("…")
        gui.nmt_y.set.assert_called_once_with("…")
        gui.nmt_z.set.assert_called_once_with("…")

    def test_catalog_population_uses_vispa_side_results(self):
        from vispa.gui import NeuroVisGUI

        class Variable:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        class Table:
            def __init__(self):
                self.rows = []

            def get_children(self):
                return ()

            def insert(self, *args, **kwargs):
                self.rows.append((args, kwargs))

        snapshot = {
            "sample_id": "251637", "monkey_id": "936",
            "source_kind": "live-iondata", "request_url": "http://example",
            "fetched_at": "2026-11-04T00:00:00Z", "sha256": "a" * 64,
            "count": 3,
            "rows": [
                {"neuron_id": "004.swc", "portal_region": "PrCO_49"},
                {"neuron_id": "005.swc", "portal_region": "PrCO_49"},
                {"neuron_id": "006.swc", "portal_region": "PrCO_49"},
            ],
        }
        side_result = {
            "counts": {"Left": 1, "Right": 1, "Unknown": 1},
            "source": {"method": "IONData_soma_catalog+NMT_atlas"},
            "results": {
                "004.swc": {"status": "verified", "side": "Right"},
                "005.swc": {"status": "verified", "side": "Left"},
                "006.swc": {"status": "unknown", "side": None},
            },
        }
        gui = object.__new__(NeuroVisGUI)
        gui.neuron_catalog_table = Table()
        gui._catalog_rows_by_iid = {}
        gui.neuron_catalog_info = Variable()
        gui.neuron_catalog_title = Variable()
        gui.neuron_catalog_side_summary = Variable()
        gui._populate_neuron_catalog(
            snapshot, side_result=side_result, side_state="complete")
        values = [entry[1]["values"] for entry in gui.neuron_catalog_table.rows]
        tags = [entry[1]["tags"] for entry in gui.neuron_catalog_table.rows]
        self.assertEqual(values[0], ("Right", "004.swc", "PrCO_49"))
        self.assertEqual(values[1], ("Left", "005.swc", "PrCO_49"))
        self.assertEqual(values[2], ("Unknown", "006.swc", "PrCO_49"))
        self.assertEqual(tags, [("side-right",), ("side-left",), ("side-unknown",)])
        self.assertEqual(
            gui.neuron_catalog_side_summary.value,
            "Side: Left 1 · Right 1 · Unknown 1")
        self.assertIn("IONData_soma_catalog+NMT_atlas", gui.neuron_catalog_info.value)

    def test_catalog_filter_and_sort_do_not_refetch(self):
        from vispa.gui import NeuroVisGUI

        class Variable:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Table:
            def __init__(self):
                self.children = []
                self.rows = {}
                self.headings = {}

            def get_children(self):
                return tuple(self.children)

            def delete(self, *items):
                for item in items:
                    if item in self.children:
                        self.children.remove(item)
                    self.rows.pop(item, None)

            def insert(self, _parent, _index, iid, values, tags):
                self.children.append(iid)
                self.rows[iid] = {"values": values, "tags": tags}

            def item(self, iid, values=None, tags=None):
                if values is not None:
                    self.rows[iid]["values"] = values
                if tags is not None:
                    self.rows[iid]["tags"] = tags

            def heading(self, column, text=None):
                if text is not None:
                    self.headings[column] = text

        snapshot = {
            "rows": [
                {"neuron_id": "010.swc", "portal_region": "PrCO_49"},
                {"neuron_id": "002.swc", "portal_region": "Ial_42"},
                {"neuron_id": "005.swc", "portal_region": "M1_79"},
            ],
        }
        side_result = {
            "results": {
                "010.swc": {"status": "verified", "side": "Right"},
                "002.swc": {"status": "verified", "side": "Left"},
                "005.swc": {"status": "unknown", "side": None},
            },
        }
        gui = object.__new__(NeuroVisGUI)
        gui._catalog_snapshot = snapshot
        gui._catalog_rows_by_iid = {}
        gui._catalog_view_side_result = side_result
        gui._catalog_view_side_state = "complete"
        gui._catalog_filter_var = Variable("right prco")
        gui._catalog_region_filter_var = Variable("All regions")
        gui._catalog_sort_column = None
        gui._catalog_sort_reverse = False
        gui.neuron_catalog_visible_count = Variable()
        gui.neuron_catalog_table = Table()
        gui._neuron_catalog_window = object()
        gui._render_neuron_catalog_rows(snapshot)
        self.assertEqual([row["values"][1] for row in gui.neuron_catalog_table.rows.values()],
                         ["010.swc"])
        self.assertEqual(gui.neuron_catalog_visible_count.get(), "Showing 1 / 3")
        self.assertEqual(
            gui.neuron_catalog_table.headings["portal_region"],
            "Ion_NMT_region")

        gui._catalog_filter_var.set("")
        gui._catalog_region_filter_var.set("PrCO_49")
        gui._apply_neuron_catalog_filter()
        self.assertEqual(
            [row["values"][1]
             for row in gui.neuron_catalog_table.rows.values()],
            ["010.swc"])
        self.assertEqual(gui.neuron_catalog_visible_count.get(), "Showing 1 / 3")

        gui._catalog_region_filter_var.set("All regions")
        gui._sort_neuron_catalog("side")
        self.assertEqual(
            [row["values"][1] for row in gui.neuron_catalog_table.rows.values()],
            ["002.swc", "010.swc", "005.swc"])
        self.assertEqual(gui.neuron_catalog_table.headings["side"], "Side ↑")
        gui._sort_neuron_catalog("side")
        self.assertEqual(gui.neuron_catalog_table.headings["side"], "Side ↓")

    def test_catalog_region_values_are_exact_and_sorted(self):
        from vispa.gui import NeuroVisGUI
        rows = [
            {"neuron_id": "001.swc", "portal_region": ""},
            {"neuron_id": "002.swc", "portal_region": "PrCO_49"},
            {"neuron_id": "003.swc", "portal_region": "Ial_42"},
            {"neuron_id": "004.swc", "portal_region": "PrCO_49"},
        ]
        self.assertEqual(
            NeuroVisGUI._catalog_region_values(rows),
            ("All regions", "Ial_42", "PrCO_49", "Unassigned"))

    def test_catalog_side_application_updates_cache_and_export(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui._catalog_side_request_id = 3
        gui._catalog_sample_id = "251637"
        gui._neuron_catalog_window = mock.Mock()
        gui._neuron_catalog_window.winfo_exists.return_value = True
        gui._catalog_snapshot = {"sample_id": "251637", "snapshot_id": "s1", "count": 1}
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "251637"
        gui._neuron_side_cache = {}
        gui.neuron_catalog_export_button = mock.Mock()
        gui._populate_neuron_catalog = mock.Mock()
        gui._update_neuron_status = mock.Mock()
        gui.update_status = mock.Mock()
        result = {
            "status": "complete",
            "counts": {"Left": 0, "Right": 1, "Unknown": 0},
            "source": {"method": "IONData_soma_catalog+NMT_atlas"},
            "results": {"004.swc": {"status": "verified", "side": "Right"}},
        }
        with mock.patch("vispa.reviewer.IT.catalog_matches_sample", return_value=True), \
             mock.patch("vispa.reviewer.IT.catalog_snapshot_unchanged", return_value=True):
            gui._apply_catalog_side_load(3, "251637", "s1", result, None)
        self.assertEqual(gui._neuron_side_cache[("251637", "004.swc")]["side"], "Right")
        gui.neuron_catalog_export_button.configure.assert_called_with(state="normal")
        gui._update_neuron_status.assert_called_once()

    def test_catalog_save_prompt_defaults_to_shared_table_folder(self):
        from vispa.gui import NeuroVisGUI
        fetched = "2026-11-04T00:00:00Z"
        source_sha = "a" * 64
        snapshot_id = hashlib.sha256(
            f"251637\0{fetched}\0{source_sha}".encode()).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            snapshot = {
                "sample_id": "251637", "monkey_id": "936",
                "source_kind": "live-iondata", "request_url": "http://example",
                "fetched_at": fetched, "sha256": source_sha,
                "snapshot_id": snapshot_id, "count": 1,
                "rows": [{
                    "sample_id": "251637", "neuron_id": "004.swc",
                    "portal_region": "PrCO_49", "snapshot_id": snapshot_id,
                }],
            }
            side_result = {
                "status": "complete",
                "counts": {"Left": 0, "Right": 1, "Unknown": 0},
                "source": {"method": "IONData_soma_catalog+NMT_atlas"},
                "results": {"004.swc": {
                    "status": "verified", "side": "Right",
                    "source": {"method": "NMT_atlas_region_prefix"}}},
            }
            chosen = root / "table" / "ion_neuronlists" / "custom.csv"
            gui = object.__new__(NeuroVisGUI)
            gui._catalog_snapshot = snapshot
            gui._catalog_side_result = side_result
            gui._catalog_sample_id = "251637"
            gui.sample_id = mock.Mock()
            gui.sample_id.get.return_value = "251637"
            gui.output_root = str(root / "VisPa_outputs")
            gui.output_dir = mock.Mock()
            gui.output_dir.get.return_value = str(root / "saving")
            gui.config_path = None
            gui._neuron_catalog_window = None
            gui.root = mock.Mock()
            gui.update_status = mock.Mock()
            gui._append_log = mock.Mock()
            gui.neuron_catalog_info = mock.Mock()
            with mock.patch(
                    "vispa.reviewer.filedialog.asksaveasfilename",
                    return_value=str(chosen)) as prompt:
                gui.save_neuron_catalog_table()
            default_dir = root / "VisPa_outputs" / "table" / "ion_neuronlists"
            self.assertEqual(Path(prompt.call_args.kwargs["initialdir"]), default_dir)
            self.assertTrue(prompt.call_args.kwargs["initialfile"].startswith(
                "936_251637_neuron_table_"))
            self.assertTrue(chosen.is_file())
            gui.update_status.assert_called()

    def test_sample_change_autoloads_open_catalog(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "252527"
        gui._catalog_observed_sample_id = "251637"
        gui._catalog_request_id = 1
        gui._catalog_side_request_id = 1
        gui._catalog_sample_id = "251637"
        gui._catalog_snapshot = {"sample_id": "251637"}
        gui._catalog_side_snapshot_id = "old"
        gui._catalog_side_result = {"status": "complete"}
        gui._catalog_rows_by_iid = {"row": {}}
        gui.neuron_catalog_table = mock.Mock()
        gui.neuron_catalog_table.get_children.return_value = ()
        gui._neuron_catalog_window = mock.Mock()
        gui.neuron_catalog_load_button = mock.Mock()
        gui.neuron_catalog_export_button = mock.Mock()
        gui.neuron_catalog_info = mock.Mock()
        gui.neuron_catalog_title = mock.Mock()
        gui.neuron_catalog_side_summary = mock.Mock()
        gui.root = mock.Mock()
        gui.load_neuron_catalog = mock.Mock()
        scheduled = []
        gui.root.after.side_effect = lambda delay, callback: scheduled.append((delay, callback)) or "after-1"
        gui._on_catalog_sample_change()
        self.assertEqual(scheduled[0][0], 700)
        scheduled[0][1]()
        gui.load_neuron_catalog.assert_called_once_with()

    def test_stale_workbook_result_does_not_change_selected_identity(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = '252714'
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = '008.swc'
        gui._neuron_side_pending = {('251637', '004.swc')}
        gui._neuron_side_cache = {}
        gui._append_log = mock.Mock()
        gui._update_neuron_status = mock.Mock()
        gui._store_neuron_side(('251637', '004.swc'), {
            'status': 'verified', 'side': 'Right', 'source': {}})
        gui._update_neuron_status.assert_not_called()
        gui._append_log.assert_not_called()

    def test_region_status_clears_on_identity_change_and_ignores_old_sample_error(self):
        from vispa.gui import NeuroVisGUI
        gui = object.__new__(NeuroVisGUI)
        gui.sample_id = mock.Mock()
        gui.sample_id.get.return_value = "252714"
        gui.neuron_id = mock.Mock()
        gui.neuron_id.get.return_value = "008.swc"
        gui._portal_region_cache = {"252384": {"008.swc": "Tpt_200"}}
        gui._neuron_lookup_state = "waiting"
        gui.neuron_status_var = mock.Mock()
        gui.region_status_var = mock.Mock()
        gui._update_neuron_status()
        gui.neuron_status_var.set.assert_called_once_with("Neuron status: waiting to load")
        gui.region_status_var.set.assert_called_once_with("Region: checking")
        gui.region_status_var.reset_mock()
        gui._set_region_lookup_error("252384", "008.swc", "old failure")
        gui.region_status_var.set.assert_not_called()
        gui._set_region_lookup_error("252714", "007.swc", "old neuron failure")
        gui.region_status_var.set.assert_not_called()

    def test_guide_sections_cover_review_and_recovery(self):
        from vispa.gui import NeuroVisGUI
        guide = NeuroVisGUI._guide_sections()
        self.assertEqual(len(guide), 6)
        content = " ".join(text for _, lines in guide for text in lines)
        for term in ("F5", "NIfTI", "3D SWC", "fnt-tracer", "receipt", "retry"):
            self.assertIn(term, content)


if __name__ == "__main__":
    unittest.main()
