"""Focused regression checks for the standalone extraction seams.

Version: 1.11.0.dev9 (local/unreleased)
Last updated: 2026-10-23
Change history: ../CHANGELOG.md
"""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest
import struct
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TEST_INSTALLED = os.environ.get("VISPA_TEST_INSTALLED") == "1"
if not TEST_INSTALLED:
    sys.path.insert(0, str(SRC))


class StandaloneImportTests(unittest.TestCase):
    def test_import_does_not_need_iondata_or_mutate_sys_path(self):
        script = '''import builtins, os, sys
os.environ["APPDATA"] = sys.argv[2]
os.environ.pop("VISPA_CONFIG", None)
os.environ.pop("VISUAL_TOOLKIT_CONFIG", None)
os.environ.pop("PROJECTOME_DATASETS", None)
installed = os.environ.get("VISPA_TEST_INSTALLED") == "1"
if not installed:
    sys.path.insert(0, sys.argv[1])
before = list(sys.path)
original = builtins.__import__
blocked = {"IONData", "neuron_vis", "projectome_analysis", "dataset_config",
           "tifffile", "nibabel", "paramiko", "yaml"}
attempted = []
def guarded(name, *args, **kwargs):
    root = name.split(".", 1)[0]
    level = kwargs.get("level", args[3] if len(args) > 3 else 0)
    if root in blocked and not (root == "dataset_config" and level > 0):
        attempted.append(name)
        raise AssertionError("unexpected non-core import: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import vispa
import vispa.toolkit as toolkit
toolkit._sample_paths_from_config()
assert before == sys.path, (before, sys.path)
assert not attempted, attempted
assert "IONData" not in sys.modules
assert "dataset_config" not in sys.modules
if installed:
    import sysconfig
    from pathlib import Path
    purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
    editable_root = Path(sys.argv[1]).resolve() / "vispa"
    vispa_path = Path(vispa.__file__).resolve()
    toolkit_path = Path(toolkit.__file__).resolve()
    assert vispa_path.is_relative_to(purelib) or vispa_path.is_relative_to(editable_root)
    assert toolkit_path.is_relative_to(purelib) or toolkit_path.is_relative_to(editable_root)
        '''
        command = [sys.executable]
        if TEST_INSTALLED:
            command.append("-I")
        with tempfile.TemporaryDirectory() as config_home:
            command.extend(("-c", script, str(SRC), config_home))
            result = subprocess.run(command, cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_user_yaml_is_applied_on_toolkit_import(self):
        with tempfile.TemporaryDirectory() as appdata:
            config_dir = Path(appdata) / "VisualToolkit"
            config_dir.mkdir()
            (config_dir / "visual_toolkit_config.yaml").write_text(
                "version: 1\nvisual_toolkit:\n  settings:\n    review:\n      marker.color: '#123456'\n",
                encoding="utf-8")
            script = """from pathlib import Path
from vispa import toolkit
assert toolkit.ACTIVE_CONFIG['config_origin'] == 'environment'
assert toolkit.review_settings_snapshot()['marker']['color'] == '#123456'
assert Path(toolkit.ACTIVE_CONFIG['path']).name == 'visual_toolkit_config.yaml'
"""
            env = {key: value for key, value in os.environ.items()
                   if key not in {"VISPA_CONFIG", "VISUAL_TOOLKIT_CONFIG", "PROJECTOME_DATASETS"}}
            env.update({"APPDATA": appdata, "VISPA_CONFIG": str(config_dir / "visual_toolkit_config.yaml"),
                        "PYTHONPATH": str(SRC), "MPLBACKEND": "Agg"})
            result = subprocess.run([sys.executable, "-c", script], cwd=tempfile.gettempdir(),
                                    env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_tiff_extra_fails_only_when_tiff_reader_is_used(self):
        from vispa import toolkit
        with mock.patch.dict(sys.modules, {"tifffile": None}):
            with self.assertRaisesRegex(RuntimeError, "TIFF input could not be decoded"):
                toolkit._read_highres_cube("not-read.tif")

    def test_missing_tifffile_uses_pillow_for_low_resolution_tiff(self):
        import numpy as np
        from PIL import Image
        from vispa import toolkit

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "section.tif"
            expected = np.arange(25, dtype=np.uint16).reshape(5, 5)
            Image.fromarray(expected).save(source)
            with mock.patch.dict(sys.modules, {"tifffile": None}):
                actual = toolkit._read_tiff(source)
        self.assertTrue(np.array_equal(actual, expected))


class ReviewSettingsTests(unittest.TestCase):
    def test_schema_exposes_defaults_current_ranges_and_effects(self):
        from vispa import review_settings_schema, toolkit
        schema = review_settings_schema()
        marker = schema["settings"]["marker.color"]
        self.assertEqual(marker["default"], "#00e5ee")
        self.assertEqual(marker["current"], toolkit.REVIEW_SETTINGS["marker"]["color"])
        self.assertIn("minimum", schema["settings"]["figure.panel_dpi"])
        self.assertIn("maximum", schema["settings"]["figure.panel_dpi"])
        self.assertTrue(schema["settings"]["marker.color"]["effect"])

    def test_mapping_and_path_value_updates_sync_global_render_defaults(self):
        from vispa import apply_setting_overrides, toolkit
        original = toolkit.review_settings_snapshot()
        try:
            changed = apply_setting_overrides({
                "marker.color": "#ff00ff",
                "widefield.gain": 3.0,
                "widefield.threshold": -5,
                "context.width_um": 50,
                "marker.label_fontsize": 5,
                "scale_bar_candidates_um": [100, 200, 500],
                "figure.panel_figsize": [50, 30],
                "figure.panel_dpi": 20,
                "figure.review_figsize": [8, 4],
                "figure.review_dpi": 90,
            })
            self.assertEqual(changed["marker.color"], "#ff00ff")
            self.assertEqual(toolkit.TARGET_MARKER_COLOR, "#ff00ff")
            self.assertEqual(toolkit.WIDEFIELD_DEFAULT_PARAMETERS, (3.0, -5.0))
            self.assertEqual(toolkit.REVIEW_SETTINGS["context"]["width_um"], 50)
            self.assertIsInstance(toolkit.REVIEW_SETTINGS["context"]["width_um"], int)
            self.assertEqual(toolkit.REVIEW_SETTINGS["marker"]["label_fontsize"], 5.0)
            self.assertEqual(toolkit.SCALE_BAR_CANDIDATES_UM, (100.0, 200.0, 500.0))
            self.assertEqual(toolkit.VisPa.PANEL_FIGSIZE, (50.0, 30.0))
            self.assertEqual(toolkit.VisPa.PANEL_DPI, 20)
            self.assertEqual(toolkit.VisPa.TRIO_FIGSIZE, (8.0, 4.0))
            self.assertEqual(toolkit.VisPa.TRIO_DPI, 90)
            before_globals = (toolkit.REVIEW_SETTINGS["marker"]["color"],
                              toolkit.TARGET_MARKER_COLOR, toolkit.VisPa.PANEL_DPI)
            custom = toolkit.review_settings_snapshot()
            toolkit.apply_setting_overrides(["marker.color=#123456", "figure.panel_dpi=150"], settings=custom)
            self.assertEqual(custom["marker"]["color"], "#123456")
            self.assertEqual((toolkit.REVIEW_SETTINGS["marker"]["color"],
                              toolkit.TARGET_MARKER_COLOR, toolkit.VisPa.PANEL_DPI), before_globals)
        finally:
            toolkit.REVIEW_SETTINGS.clear()
            toolkit.REVIEW_SETTINGS.update(original)

    def test_context_overlay_depth_is_discoverable_and_validated(self):
        from vispa import apply_setting_overrides, review_settings_schema, toolkit
        schema = review_settings_schema()
        spec = schema["settings"]["context.swc_overlay_depth_um"]
        self.assertEqual(spec["default"], 100.0)
        self.assertTrue(spec["effect"])
        original = toolkit.review_settings_snapshot()
        try:
            apply_setting_overrides({"context.swc_overlay_depth_um": 50})
            self.assertEqual(
                toolkit.REVIEW_SETTINGS["context"]["swc_overlay_depth_um"], 50.0)
            with self.assertRaisesRegex(ValueError, "must be > 0"):
                apply_setting_overrides({"context.swc_overlay_depth_um": 0})
        finally:
            toolkit.REVIEW_SETTINGS.clear()
            toolkit.REVIEW_SETTINGS.update(original)
            toolkit._sync_review_setting_constants()

    def test_shared_settings_api_is_atomic_and_available_through_toolkit_facade(self):
        from vispa import apply_settings, resolve_settings, settings_schema, toolkit
        self.assertIs(toolkit.resolve_settings, resolve_settings)
        schema = settings_schema("all")
        self.assertEqual(set(schema["scopes"]), {"review", "brain-view", "montage"})
        target = resolve_settings("review")
        before = copy.deepcopy(target)
        changed = apply_settings("review", ["marker.color=#123456", "figure.panel_dpi=150"], settings=target)
        self.assertEqual(changed["marker.color"], "#123456")
        self.assertEqual(target["marker"]["color"], "#123456")
        self.assertEqual(target["figure"]["panel_dpi"], 150)
        self.assertEqual(before["marker"]["color"], "#00e5ee")
        stable = copy.deepcopy(target)
        with self.assertRaises((ValueError, KeyError)):
            apply_settings("review", ["marker.color=#abcdef", "figure.panel_dpi=0"], settings=target)
        self.assertEqual(target, stable)
        montage_base = {"display_gamma": 1.1}
        montage_result = resolve_settings("montage", ["foreground_threshold=0.2"], base=montage_base)
        self.assertEqual(montage_result["display_gamma"], 1.1)
        self.assertEqual(montage_base, {"display_gamma": 1.1})
        with self.assertRaisesRegex(ValueError, "explicit mutable settings target"):
            apply_settings("montage", {"display_gamma": 1.2})
        with self.assertRaisesRegex(ValueError, "base must be a mapping"):
            resolve_settings("review", base=["not", "a", "mapping"])

        partial = {"marker": {"color": "#00e5ee"}}
        partial_delta = apply_settings("review", {"figure.panel_figsize": [7, 5]}, settings=partial)
        self.assertEqual(partial["figure"]["panel_figsize"], (7.0, 5.0))
        self.assertEqual(partial_delta["figure.panel_figsize"], [7.0, 5.0])
        self.assertEqual(apply_settings("review", {"figure.panel_figsize": [7, 5]}, settings=partial), {})

        from vispa import toolkit
        original_global = toolkit.review_settings_snapshot()
        try:
            self.assertEqual(apply_settings("review", {
                "figure.panel_figsize": original_global["figure"]["panel_figsize"]}), {})
            global_delta = apply_settings("review", {"figure.panel_figsize": [6, 4]})
            self.assertEqual(global_delta["figure.panel_figsize"], [6.0, 4.0])
        finally:
            toolkit.REVIEW_SETTINGS.clear()
            toolkit.REVIEW_SETTINGS.update(original_global)
            toolkit._sync_review_setting_constants()

    def test_public_settings_api_changes_real_png_dimensions_and_marker_pixels(self):
        import numpy as np
        from PIL import Image
        from vispa import apply_setting_overrides, toolkit
        original = toolkit.review_settings_snapshot()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "plots"
            try:
                apply_setting_overrides({
                    "marker.color": "#ff00ff",
                    "marker.crosshair_px": 2,
                    "marker.label_offset_px": 0,
                    "figure.panel_figsize": [5, 3],
                    "figure.panel_dpi": 40,
                    "figure.review_figsize": [5, 3],
                    "figure.review_dpi": 40,
                })
                tool = toolkit.VisPa("SYNTH", cache_dir=root / "cache")
                try:
                    panel = tool.plot_soma_block(
                        np.arange(75, dtype=np.uint8).reshape(3, 5, 5),
                        (0, 0, 0), (1, 1, 1), (2, 2, 1), "001",
                        output_dir=output)
                    import matplotlib.pyplot as plt
                    with mock.patch.object(plt, 'close'):
                        review_png = Path(tool.plot_tri_plot(
                            [panel], "001", output_dir=output, suffix="APISettings",
                            legend=True))
                        review_figure = plt.gcf()
                    review_figure.canvas.draw()
                    data_ax = review_figure.axes[0]
                    self.assertTrue(np.allclose(data_ax.collections[0].get_edgecolors()[0], (1, 0, 1, 1)))
                    self.assertTrue(np.allclose(data_ax.collections[0].get_offsets()[0], (2, 2)))
                    marker_display = data_ax.transData.transform((2, 2))
                    tight = review_figure.get_tightbbox(review_figure.canvas.get_renderer())
                    marker_png_x = (marker_display[0] / review_figure.dpi - tight.x0 + 0.15) * 40
                    marker_png_y_from_bottom = (marker_display[1] / review_figure.dpi - tight.y0 + 0.15) * 40
                    plt.close(review_figure)
                finally:
                    tool.close()
                self.assertTrue(Path(panel["output_png"]).is_file())
                with Image.open(review_png) as image:
                    pixels = np.asarray(image.convert("RGB"))
                    self.assertGreater(image.width, 100)
                    self.assertGreater(image.height, 50)
                    self.assertLess(image.width, 400)
                    self.assertLess(image.height, 250)
                    # At 40 dpi thin markers are antialiased; test chromatic
                    # dominance rather than requiring fully saturated pixels.
                    cx, cy = int(round(marker_png_x)), int(round(image.height - marker_png_y_from_bottom))
                    rgb = pixels[max(0, cy-10):cy+11, max(0, cx-10):cx+11].astype(int)
                    self.assertGreater(rgb.size, 0)
                    magenta = ((rgb[:, :, 0] - rgb[:, :, 1] > 80) &
                               (rgb[:, :, 2] - rgb[:, :, 1] > 80))
                    self.assertGreater(int(magenta.sum()), 0)
            finally:
                toolkit.REVIEW_SETTINGS.clear()
                toolkit.REVIEW_SETTINGS.update(original)
                toolkit._sync_review_setting_constants()

    def test_labeled_review_axes_and_wrapped_legend_clear_at_different_aspects(self):
        import numpy as np
        import matplotlib.pyplot as plt
        from vispa import toolkit
        original = toolkit.review_settings_snapshot()
        figures = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tool = toolkit.VisPa("SYNTH", cache_dir=root / "cache")
            tool.TRIO_FIGSIZE = (12, 8)
            try:
                panel = tool.plot_soma_block(
                    np.arange(75, dtype=np.uint8).reshape(3, 5, 5),
                    (0, 0, 0), (1, 1, 1), (2, 2, 1), "001",
                    output_dir=root / "plots")
                panel["axis_labels"] = ("X pixel index (column)", "Y pixel index (row)")
                panel["legend"] = [
                    ("patch", "gray", "local NPY input · grayscale ZYX MIP"),
                    ("marker", toolkit.TARGET_MARKER_COLOR,
                     "target soma marker (box + cross, not to scale)"),
                ]
                real_figure = plt.figure

                def capture_figure(*args, **kwargs):
                    figure = real_figure(*args, **kwargs)
                    figures.append(figure)
                    return figure

                with mock.patch.object(plt, "figure", side_effect=capture_figure), \
                        mock.patch.object(plt, "close"):
                    tool.plot_tri_plot([panel], "001", output_dir=root / "plots",
                                        suffix="LabeledClearance", legend=True, dpi=100)
                labeled = figures[-1]
                labeled.canvas.draw()
                renderer = labeled.canvas.get_renderer()
                data_box = labeled.axes[0].get_tightbbox(renderer)
                legend_ax = labeled.axes[-1]
                legend_box = legend_ax.get_tightbbox(renderer)
                self.assertGreater(data_box.y0, legend_box.y1)
                labeled_grid = labeled.axes[0].get_subplotspec().get_gridspec()
                self.assertGreater(labeled_grid.hspace, 0.02)

                legacy_panel = dict(panel)
                legacy_panel["axis_labels"] = None
                with mock.patch.object(plt, "figure", side_effect=capture_figure), \
                        mock.patch.object(plt, "close"):
                    tool.plot_tri_plot([legacy_panel], "001", output_dir=root / "plots",
                                        suffix="LegacySpacing", legend=True, dpi=100)
                legacy_grid = figures[-1].axes[0].get_subplotspec().get_gridspec()
                self.assertEqual(legacy_grid.hspace, 0.02)

                multi_panels = []
                for role, color in (("Soma", "gray"), ("Context", "green"), ("Sagittal", "gray")):
                    multi = dict(panel)
                    multi["role"] = role
                    multi['notes'] = ['Candidate axes and native source directions remain unaccepted; ' * 8]
                    multi["legend"] = [
                        ("patch", color, f"{role} display"),
                        ("marker", toolkit.TARGET_MARKER_COLOR, role),
                    ]
                    multi_panels.append(multi)
                with mock.patch.object(plt, "figure", side_effect=capture_figure), \
                        mock.patch.object(plt, "close"):
                    multi_path = tool.plot_tri_plot(
                        multi_panels, "001", output_dir=root / "plots",
                        suffix="LegacyMultiPanelSpacing", legend=True, dpi=40)
                self.assertTrue(Path(multi_path).is_file())
                multi_grid = figures[-1].axes[0].get_subplotspec().get_gridspec()
                multi_figure = figures[-1]
                multi_figure.canvas.draw()
                renderer = multi_figure.canvas.get_renderer()
                legend_ax = multi_figure.axes[-1]
                for data_ax in multi_figure.axes[:-1]:
                    self.assertGreater(data_ax.get_tightbbox(renderer).y0,
                                       legend_ax.get_tightbbox(renderer).y1)
                    self.assertEqual(data_ax.get_anchor(), 'N')
                    self.assertEqual(tuple(data_ax.images[0].get_extent()), tuple(labeled.axes[0].images[0].get_extent()))
                text_boxes = [text.get_window_extent(renderer) for text in legend_ax.texts if text.get_text()]
                self.assertLessEqual(max(box.x1 for box in text_boxes), legend_ax.get_window_extent(renderer).x1 + 2)
                self.assertGreater(text_boxes[0].y0, legend_ax.get_legend().get_window_extent(renderer).y1)
                self.assertGreater(legend_ax.get_legend().get_window_extent(renderer).y0, text_boxes[-1].y1)

                tool.TRIO_FIGSIZE = (12, 0.01)
                with mock.patch.object(plt, "figure", side_effect=capture_figure), \
                        mock.patch.object(plt, "close", wraps=plt.close) as close_figure:
                    with self.assertRaisesRegex(RuntimeError, "cannot fit in the selected figure height"):
                        tool.plot_tri_plot([panel], "001", output_dir=root / "plots",
                                            suffix="ImpossibleClearance", legend=True, dpi=100)
                close_figure.assert_called_once_with(figures[-1])
            finally:
                tool.close()
                toolkit.REVIEW_SETTINGS.clear()
                toolkit.REVIEW_SETTINGS.update(original)
                toolkit._sync_review_setting_constants()
                for figure in figures:
                    plt.close(figure)

    def test_invalid_batch_is_atomic_for_custom_and_global_settings(self):
        from vispa import toolkit
        original = toolkit.review_settings_snapshot()
        constants = (toolkit.TARGET_MARKER_COLOR, toolkit.WIDEFIELD_DEFAULT_PARAMETERS,
                     toolkit.SCALE_BAR_CANDIDATES_UM, toolkit.VisPa.PANEL_DPI)
        custom = toolkit.review_settings_snapshot()
        with self.assertRaises(ValueError):
            toolkit.apply_setting_overrides(["marker.color=#123456", "figure.panel_figsize=0,3"], settings=custom)
        self.assertEqual(custom, original)
        with self.assertRaises(ValueError):
            toolkit.apply_setting_overrides(["marker.color=#123456", "figure.panel_dpi=0"])
        self.assertEqual(toolkit.REVIEW_SETTINGS, original)
        self.assertEqual((toolkit.TARGET_MARKER_COLOR, toolkit.WIDEFIELD_DEFAULT_PARAMETERS,
                          toolkit.SCALE_BAR_CANDIDATES_UM, toolkit.VisPa.PANEL_DPI), constants)


class ConfigTests(unittest.TestCase):
    @staticmethod
    def _synthetic_correction_policy():
        return {
            "corrected": True,
            "completion_record": "shift_record.json",
            "sample_id_field": "sample_id",
            "required_values": {"state": "ready", "shift_px": [2, 3], "first_section": 12},
            "collection_counts": {"sections": 4},
            "empty_fields": ["failures", "missing_files"],
            "cache_namespace": "synthetic_z12_aligned",
            "provenance": {"first_section": 12, "shift_px": [2, 3],
                            "swc_transform_applied": False,
                            "padding": "zero; excluded source support"},
        }

    @staticmethod
    def _nifti_header(shape, affine_diag):
        header = bytearray(352)
        struct.pack_into("<i", header, 0, 348)
        struct.pack_into("<8h", header, 40, 3, *shape, 1, 1, 1, 1)
        struct.pack_into("<hh", header, 70, 16, 32)
        struct.pack_into("<8f", header, 76, 1, 1, 1, 1, 1, 1, 1, 1)
        struct.pack_into("<f", header, 108, 352)
        struct.pack_into("<2f", header, 112, 1, 0)
        header[123] = 2
        struct.pack_into("<h", header, 254, 1)
        for row, offset in enumerate((280, 296, 312)):
            values = [0.0, 0.0, 0.0, 0.0]
            values[row] = affine_diag[row]
            struct.pack_into("<4f", header, offset, *values)
        return bytes(header)

    def test_config_rejects_falsy_nonmapping_sections_and_half_gui_defaults(self):
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for key, value in (("defaults", []), ("samples", []), ("sources", [])):
                path = root / f"bad-{key}.json"
                path.write_text(json.dumps({"version": 1, key: value}), encoding="utf-8")
                with self.subTest(section=key), self.assertRaisesRegex(ValueError, f"{key} must be a mapping"):
                    load(path)
            path = root / "half-default.json"
            path.write_text(json.dumps({"version": 1, "visual_toolkit": {
                "default_sample": "SYNTH", "default_neuron": ""}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must both be set"):
                load(path)

    def test_generic_geometry_descriptor_is_validated_and_published_from_config(self):
        from vispa import toolkit
        geometry = {"shape_ijk": [10, 20, 30], "spacing_mm_ijk": [0.005, 0.005, 0.005],
                    "affine_diag": [-0.005, -0.005, 0.005]}
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "geometry.json"
            config_path.write_text(json.dumps({"version": 1, "samples": {
                "SYNTH": {"ds00_expected_geometry": geometry}}}), encoding="utf-8")
            from vispa.dataset_config import load
            config = load(config_path)
            self.assertEqual(config["samples"]["SYNTH"]["ds00_expected_geometry"]["shape_ijk"], (10, 20, 30))
            with mock.patch.multiple(
                    toolkit, ACTIVE_CONFIG=None, EXPECTED_GEOMETRY={}, LOW_RES_SHARE_BY_SAMPLE={},
                    HTTP_HOST=None, HTTP_PATH=None, SSH_HOST=None, SSH_PORT=None, SSH_USER=None,
                    SSH_PASS=None, SSH_REMOTE_BASE=None, SSH_SAMPLE_ID=None, SHARE_ROOT=None,
                    DATASET_MANIFEST=None, SAMPLE_PATHS=dict(toolkit.SAMPLE_PATHS)):
                toolkit.configure_data_sources(config=config)
                self.assertEqual(toolkit.EXPECTED_GEOMETRY["SYNTH"]["affine_diag"], (-0.005, -0.005, 0.005))
                parsed = toolkit._nifti_metadata(self._nifti_header((10, 20, 30), (-0.005, -0.005, 0.005)),
                                                  toolkit.EXPECTED_GEOMETRY["SYNTH"])
                self.assertEqual(parsed["shape_ijk"], (10, 20, 30))
                for header in (
                    self._nifti_header((10, 20, 31), (-0.005, -0.005, 0.005)),
                    self._nifti_header((10, 20, 30), (-0.005, -0.006, 0.005)),
                    self._nifti_header((10, 20, 30), (0.005, -0.005, 0.005)),
                ):
                    with self.subTest(header=header[280:284]):
                        with self.assertRaises(ValueError):
                            toolkit._nifti_metadata(header, toolkit.EXPECTED_GEOMETRY["SYNTH"])
                local = Path(temp) / "repository" / "sample.nii"
                server = Path(temp) / "share" / "sample.nii"
                local.parent.mkdir()
                server.parent.mkdir()
                local.write_bytes(b"synthetic source")
                server.write_bytes(b"same-sized configured reference")
                manifest = Path(temp) / "manifest.json"
                manifest.write_text(json.dumps({"selected_preprocessed_outputs": [{
                    "sample": "SYNTH", "relative_path": "sample.nii",
                    "repository_candidate_path": str(local),
                    "sha256": toolkit._sha256(local),
                }]}), encoding="utf-8")
                toolkit.SHARE_ROOT = server.parent
                toolkit.DATASET_MANIFEST = manifest
                toolkit.SAMPLE_PATHS = {"SYNTH": {}}
                source_record = toolkit._source_record("SYNTH")
                self.assertEqual(source_record["expected_geometry"], toolkit.EXPECTED_GEOMETRY["SYNTH"])
            bad = dict(geometry, shape_ijk=[10, 0, 30])
            config_path.write_text(json.dumps({"version": 1, "samples": {
                "SYNTH": {"ds00_expected_geometry": bad}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "positive integers"):
                load(config_path)

    def test_generic_corrected_source_policy_validates_and_records_provenance(self):
        from vispa import toolkit
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            corrected = root / "low_res"
            corrected.mkdir()
            record = {
                "sample_id": "SYNTH", "state": "ready", "shift_px": [2, 3],
                "first_section": 12, "sections": [1, 2, 3, 4],
                # Missing empty inventory fields retain the historical falsey default.
            }
            (corrected / "shift_record.json").write_text(json.dumps(record), encoding="utf-8")
            policy = self._synthetic_correction_policy()
            path = root / "policy.json"
            path.write_text(json.dumps({"version": 1, "samples": {"SYNTH": {
                "resample_5um": str(corrected), "resample_5um_corrected": True,
                "resample_5um_policy": policy}}}), encoding="utf-8")
            config = load(path)
            with mock.patch.object(toolkit, "ACTIVE_CONFIG", config):
                tool = toolkit.VisPa("SYNTH", cache_dir=root / "cache",
                                              low_res_dir=corrected)
                try:
                    self.assertEqual(tool.low_res_correction["validation_policy"], policy)
                    self.assertEqual(Path(tool.cache_ssh_dir).name, "synthetic_z12_aligned")
                    self.assertEqual(tool.low_res_correction["record"], str(corrected / "shift_record.json"))
                    import hashlib
                    self.assertEqual(tool.low_res_correction["sha256"],
                                     hashlib.sha256((corrected / "shift_record.json").read_bytes()).hexdigest())
                finally:
                    tool.close()
                invalid_records = []
                for key, value in (("sample_id", "OTHER"), ("state", "running"),
                                   ("shift_px", [2, 4]), ("first_section", 13),
                                   ("sections", [1, 2, 3])):
                    invalid = dict(record)
                    invalid[key] = value
                    invalid_records.append((key, invalid))
                for field in policy["empty_fields"]:
                    invalid = dict(record)
                    invalid[field] = ["unexpected"]
                    invalid_records.append((field, invalid))
                for name, invalid in invalid_records:
                    with self.subTest(record_field=name):
                        (corrected / "shift_record.json").write_text(json.dumps(invalid), encoding="utf-8")
                        with self.assertRaises(ValueError):
                            toolkit.VisPa("SYNTH", cache_dir=root / f"cache-{name}",
                                                   low_res_dir=corrected)
            missing_policy = {"version": 1, "samples": {"SYNTH": {
                "resample_5um": str(corrected), "resample_5um_corrected": True}}}
            path.write_text(json.dumps(missing_policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires a complete resample_5um_policy"):
                load(path)
            bad = self._synthetic_correction_policy()
            bad["completion_record"] = "../shift_record.json"
            path.write_text(json.dumps({"version": 1, "samples": {"SYNTH": {
                "resample_5um": str(corrected), "resample_5um_policy": bad}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "traversal"):
                load(path)

    def test_invalid_in_memory_config_does_not_partially_apply_settings_or_sources(self):
        from vispa import toolkit
        before_active = toolkit.ACTIVE_CONFIG
        before_geometry = dict(toolkit.EXPECTED_GEOMETRY)
        before_low_res = dict(toolkit.LOW_RES_SHARE_BY_SAMPLE)
        before_source_globals = (toolkit.HTTP_HOST, toolkit.HTTP_PATH, toolkit.SSH_HOST,
                                 toolkit.SSH_PORT, toolkit.SSH_USER, toolkit.SSH_REMOTE_BASE,
                                 toolkit.SSH_SAMPLE_ID, toolkit.SHARE_ROOT, toolkit.DATASET_MANIFEST)
        before_settings = toolkit.review_settings_snapshot()
        ssh_pass_before = toolkit.SSH_PASS
        invalid_configs = [
            ({"defaults": {}, "samples": {}, "sources": [],
              "visual_toolkit": {"settings": {"review": {"marker.color": "#ff00ff"}}}},
             "must be mappings"),
            ({"defaults": {}, "samples": {}, "sources": {},
              "visual_toolkit": {"settings": {"review": {"marker.color": "#ff00ff"},
                                                "unknown": {}}}},
             "unknown scope"),
            ({"defaults": {}, "samples": {}, "sources": {},
              "visual_toolkit": {"settings": {"review": {"marker.color": "#ff00ff"},
                                                "brain-view": []}}},
             "settings.brain-view must be a mapping"),
            ({"defaults": {}, "samples": {}, "sources": {},
              "visual_toolkit": {"settings": {"review": {"marker.color": "#ff00ff"},
                                                "montage": []}}},
             "settings.montage must be a mapping"),
            ({"defaults": {}, "samples": {}, "sources": {},
              "visual_toolkit": {"settings": [],}},
             "visual_toolkit.settings must be a mapping"),
        ]
        try:
            for invalid, message in invalid_configs:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    toolkit.configure_data_sources(config=invalid)
                self.assertIs(toolkit.ACTIVE_CONFIG, before_active)
                self.assertEqual(toolkit.EXPECTED_GEOMETRY, before_geometry)
                self.assertEqual(toolkit.LOW_RES_SHARE_BY_SAMPLE, before_low_res)
                self.assertEqual((toolkit.HTTP_HOST, toolkit.HTTP_PATH, toolkit.SSH_HOST,
                                  toolkit.SSH_PORT, toolkit.SSH_USER, toolkit.SSH_REMOTE_BASE,
                                  toolkit.SSH_SAMPLE_ID, toolkit.SHARE_ROOT, toolkit.DATASET_MANIFEST),
                                 before_source_globals)
                self.assertTrue(toolkit.SSH_PASS is ssh_pass_before, "credential global changed")
                self.assertEqual(toolkit.review_settings_snapshot(), before_settings)
        finally:
            toolkit.REVIEW_SETTINGS.clear()
            toolkit.REVIEW_SETTINGS.update(before_settings)
            toolkit._sync_review_setting_constants()

    def test_corrected_marker_cannot_bypass_policy_through_mutable_active_config(self):
        from vispa import toolkit
        with tempfile.TemporaryDirectory() as temp:
            config = {"defaults": {}, "samples": {
                "SYNTH": {"resample_5um_corrected": True}}, "sources": {}}
            with mock.patch.object(toolkit, "ACTIVE_CONFIG", config):
                with self.assertRaisesRegex(ValueError, "requires a complete resample_5um_policy"):
                    toolkit.VisPa("SYNTH", cache_dir=Path(temp) / "cache")

    def test_gui_defaults_are_configured_or_blank_and_explicit_pair_wins(self):
        from vispa.gui import resolve_gui_launch_defaults
        identity, source, auto = resolve_gui_launch_defaults({"visual_toolkit": {}})
        self.assertEqual((identity, source, auto), (("", ""), "none", False))
        config = {"visual_toolkit": {"default_sample": "252527", "default_neuron": "048.swc",
                                     "auto_load": True}}
        self.assertEqual(resolve_gui_launch_defaults(config), (("252527", "048.swc"), "configured_default", True))
        self.assertEqual(resolve_gui_launch_defaults(config, "0012ch2", "0003.swc", False),
                         (("0012ch2", "0003.swc"), "explicit", False))
        self.assertEqual(resolve_gui_launch_defaults(config, auto_load=False)[2], False)
        with self.assertRaisesRegex(ValueError, "both be set"):
            resolve_gui_launch_defaults({"visual_toolkit": {
                "default_sample": "", "default_neuron": "048.swc"}})

    def test_null_visual_toolkit_section_keeps_legacy_empty_defaults(self):
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "null-ui.json"
            path.write_text(json.dumps({"version": 1, "visual_toolkit": None}), encoding="utf-8")
            config = load(path)
        self.assertEqual(config["visual_toolkit"]["settings"], {})
        self.assertTrue(Path(config["visual_toolkit"]["output_root"] or
                             config["defaults"]["output_root"] or
                             Path.home() / "VisualToolkit" / "output").is_absolute())

    def test_fnt_tracer_paths_resolve_and_reject_unknown_keys(self):
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "configs"
            folder.mkdir()
            config_path = folder / "fnt.json"
            config_path.write_text(json.dumps({
                "version": 1,
                "visual_toolkit": {"fnt_tracer": {
                    "executable": "../tools/fnt-tracer.exe",
                    "project_root": "../fnt_work"}},
            }), encoding="utf-8")
            tools = load(config_path)["visual_toolkit"]["fnt_tracer"]
            self.assertEqual(Path(tools["executable"]),
                             (folder / "../tools/fnt-tracer.exe").resolve())
            self.assertEqual(Path(tools["project_root"]),
                             (folder / "../fnt_work").resolve())
            config_path.write_text(json.dumps({
                "version": 1,
                "visual_toolkit": {"fnt_tracer": {"exe": "typo"}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown key"):
                load(config_path)

    def test_portal_provider_fetches_and_caches_missing_swc(self):
        from vispa import sources
        with tempfile.TemporaryDirectory() as temp:
            config = {"sources": {
                "http_host": "http://portal.invalid",
                "raw_swc_base": "http://raw.invalid/swc/newswc",
                "legacy_raw_swc_root": temp}}
            provider = sources.PortalSWCProvider(config)
            payloads = {
                "http://portal.invalid/neuronbrowser/api/user/getSampleInfo"
                "?project_id=&fMOST_id=251637": b'[{"project_id": "Monkey"}]',
                "http://raw.invalid/swc/newswc/Monkey/251637/swc_raw/004.swc":
                    b"1 1 10 20 30 1 -1\n2 3 11 20 30 1 1\n",
            }
            calls = []

            def fake_read(url):
                calls.append(url)
                return payloads[url]

            provider._read = fake_read
            tree = provider.getRawNeuronTreeByID("251637", "004.swc")
            self.assertEqual(len(tree.points), 2)
            cached = Path(temp) / "251637" / "004.swc"
            self.assertTrue(cached.is_file())
            again = provider.getRawNeuronTreeByID("251637", "004")
            self.assertEqual(len(again.points), 2)
            self.assertEqual(len(calls), 2)

    def test_save_toggle_selects_preview_or_output_folder(self):
        from types import SimpleNamespace
        from vispa.gui import NeuroVisGUI
        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        gui._preview_target_dir = lambda request: "preview"
        preview_request = SimpleNamespace(save_outputs=False, output_dir="out")
        save_request = SimpleNamespace(save_outputs=True, output_dir="out")
        self.assertEqual(gui._target_for(preview_request, True), "preview")
        self.assertEqual(gui._target_for(save_request, True), "out")

    def test_relative_config_paths_resolve_once_from_config_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "configs"
            folder.mkdir()
            config_path = folder / "visual.json"
            config_path.write_text(json.dumps({
                "version": 1,
                "defaults": {"resample_5um_root": "../images", "swc_root": "../swc"},
                "samples": {"0007": {"resample_5um": "sample_a", "swc_cache": "0007"}},
                "sources": {"dataset_manifest": "../manifest.json",
                            "http_base_url": "https://example.invalid/base",
                            "ssh_remote_base": "/srv/data/raw"},
            }), encoding="utf-8")
            from vispa.dataset_config import load
            config = load(config_path)
            self.assertEqual(config["samples"]["0007"]["resample_5um"], (Path(temp) / "images" / "sample_a").resolve())
            self.assertEqual(config["samples"]["0007"]["swc_cache"], (Path(temp) / "swc" / "0007").resolve())
            self.assertEqual(config["sources"]["dataset_manifest"], (Path(temp) / "manifest.json").resolve())
            self.assertEqual(config["sources"]["http_base_url"], "https://example.invalid/base")
            self.assertEqual(config["sources"]["ssh_remote_base"], "/srv/data/raw")

    def test_relative_swc_cache_without_swc_root_stays_config_relative(self):
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "configs"
            folder.mkdir()
            config_path = folder / "visual.json"
            config_path.write_text(json.dumps({
                "version": 1,
                "samples": {"0007": {"swc_cache": "0007"}},
            }), encoding="utf-8")
            config = load(config_path)
            self.assertEqual(config["samples"]["0007"]["swc_cache"],
                             (folder / "0007").resolve())
            self.assertFalse(Path(config["defaults"]["cache_root"]).is_relative_to(folder))

    def test_config_init_uses_own_default_and_explicitly_imports_legacy(self):
        from vispa.dataset_config import initialize_default_config, load
        with tempfile.TemporaryDirectory() as temp:
            appdata = Path(temp) / "appdata"
            legacy_dir = appdata / "VisualToolkit"
            legacy_dir.mkdir(parents=True)
            legacy = legacy_dir / "visual_toolkit_config.json"
            legacy.write_text(json.dumps({"version": 1, "samples": {
                "0007": {"swc_cache": "0007"}}}), encoding="utf-8")
            legacy_bytes = legacy.read_bytes()
            target = appdata / "VisPa" / "vispa_config.yaml"
            env = {"APPDATA": str(appdata), "VISPA_CONFIG": "", "VISUAL_TOOLKIT_CONFIG": "",
                   "PROJECTOME_DATASETS": ""}
            with mock.patch.dict(os.environ, env):
                with self.assertRaisesRegex(ValueError, r"must end with \.yaml"):
                    initialize_default_config(output=str(Path(temp) / "explicit.json"))
                self.assertFalse(target.exists())
                dry = initialize_default_config(dry_run=True)
                self.assertEqual((dry["action"], dry["source_kind"]),
                                 ("would_create", "package_defaults"))
                self.assertEqual(Path(dry["config_path"]), target.resolve())
                self.assertFalse(target.exists())
                explicit = initialize_default_config(output=str(target), from_path=str(legacy), dry_run=True)
                self.assertEqual(explicit["source_kind"], "explicit_source")
                self.assertFalse(target.exists())
                plan = initialize_default_config(from_path=str(legacy))
                self.assertEqual(plan["action"], "created")
                self.assertTrue(target.is_file())
                self.assertEqual(legacy.read_bytes(), legacy_bytes)
                self.assertEqual(initialize_default_config()["action"], "already_exists")
                loaded = load()
                self.assertEqual(loaded["samples"]["0007"]["swc_cache"],
                                 (legacy_dir / "0007").resolve())

    def test_new_vispa_profile_ignores_inherited_legacy_environment(self):
        from vispa.dataset_config import initialize_default_config, load
        with tempfile.TemporaryDirectory() as temp:
            appdata = Path(temp) / "appdata"
            legacy = Path(temp) / "old_project.yaml"
            legacy.write_text("version: 1\nvisual_toolkit:\n  default_sample: OLD\n  default_neuron: 001.swc\n",
                              encoding="utf-8")
            user_data = Path(temp) / "localappdata"
            with mock.patch.dict(os.environ, {"APPDATA": str(appdata), "LOCALAPPDATA": str(user_data),
                                              "VISPA_CONFIG": "",
                                              "VISUAL_TOOLKIT_CONFIG": str(legacy),
                                              "PROJECTOME_DATASETS": str(legacy)}):
                plan = initialize_default_config()
                config = load()
            self.assertEqual(plan["source_kind"], "package_defaults")
            self.assertEqual(config["path"], (appdata / "VisPa" / "vispa_config.yaml").resolve())
            self.assertEqual(config["visual_toolkit"]["default_sample"], "251637")
            self.assertEqual(config["visual_toolkit"]["default_neuron"], "003.swc")
            self.assertEqual(config["sources"]["neuron_catalog"]["mode"], "live-iondata")
            self.assertEqual(config["sources"]["neuron_catalog"]["host"], "http://10.10.48.110")
            self.assertEqual(config["sources"]["http_host"], "http://bap.cebsit.ac.cn")
            self.assertEqual(config["sources"]["raw_swc_base"], "http://10.10.31.31/swc/newswc")
            self.assertEqual(config["defaults"]["cache_root"], user_data / "VisPa" / "cache")
            self.assertEqual(config["defaults"]["output_root"], user_data / "VisPa" / "output")
            self.assertTrue(config["visual_toolkit"]["fnt_tracer"]["auto_download"])
            self.assertEqual(
                config["visual_toolkit"]["fnt_tracer"]["project_root"],
                Path(r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\fnt\projects"),
            )
            self.assertEqual(
                config["sources"]["brain_view"]["processed_swc_root"],
                Path(r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\brain_view\processed_swc"),
            )

    def test_ds00_children_follow_editable_root_without_changing_legacy_paths(self):
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            config_file = Path(temp) / "settings.json"
            source = {"version": 1, "defaults": {"ds00_root": str(Path(temp) / "new-ds00")},
                      "samples": {"relative": {"ds00_relative": "processed_nii/brain.nii"},
                                  "legacy": {"ds00_processed": str(Path(temp) / "legacy.nii")}},
                      "sources": {"dataset_manifest_relative": "manifest.json"}}
            config_file.write_text(json.dumps(source), encoding="utf-8")
            loaded = load(config_file)
            self.assertEqual(loaded["samples"]["relative"]["ds00_processed"].resolve(),
                             (Path(temp) / "new-ds00" / "processed_nii" / "brain.nii").resolve())
            self.assertEqual(loaded["samples"]["legacy"]["ds00_processed"].resolve(), (Path(temp) / "legacy.nii").resolve())
            self.assertEqual(loaded["sources"]["dataset_manifest"].resolve(), (Path(temp) / "new-ds00" / "manifest.json").resolve())
            source["samples"]["relative"]["ds00_processed"] = "other.nii"
            config_file.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "both ds00_processed and ds00_relative"):
                load(config_file)
            source["samples"]["relative"].pop("ds00_processed")
            source["samples"]["relative"]["ds00_relative"] = "../escape.nii"
            config_file.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stay under defaults.ds00_root"):
                load(config_file)

    def test_packaged_sample_paths_follow_edited_source_roots(self):
        import yaml
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            from importlib.resources import files
            raw = yaml.safe_load(files("vispa").joinpath("config_deb.yaml").read_text(encoding="utf-8"))
            raw["defaults"]["ds00_root"] = str(root / "new-ds00")
            raw["defaults"]["resample_5um_root"] = str(root / "new-5um")
            path = root / "profile.yaml"
            path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
            loaded = load(path)
            for sample_id, declaration in raw["samples"].items():
                if declaration.get("ds00_relative"):
                    self.assertEqual(loaded["samples"][sample_id]["ds00_processed"].resolve(),
                                     (root / "new-ds00" / declaration["ds00_relative"]).resolve())
                if declaration.get("resample_5um"):
                    self.assertEqual(loaded["samples"][sample_id]["resample_5um"].resolve(),
                                     (root / "new-5um" / declaration["resample_5um"]).resolve())
            self.assertEqual(loaded["sources"]["dataset_manifest"].resolve(), (root / "new-ds00" / "manifest.json").resolve())

    def test_config_init_materializes_validated_effective_settings_for_all_scopes(self):
        import yaml
        from vispa.dataset_config import initialize_default_config, load
        from vispa.settings import SCOPES, resolve_settings, settings_schema
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.json"
            source.write_text(json.dumps({
                "version": 1,
                "visual_toolkit": {"settings": {"review": {"marker.color": "#123456"}}},
                "sources": {"brain_view": {
                    "mesh_path": "brain.obj", "processed_swc_root": "swc",
                    "settings": {"line_width": 3.0}}},
            }), encoding="utf-8")
            output = root / "effective.yaml"
            plan = initialize_default_config(output=str(output), from_path=str(source))
            self.assertEqual((plan["action"], plan["source_kind"]), ("created", "explicit_source"))
            raw = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(set(raw["visual_toolkit"]["settings"]), set(SCOPES))
            loaded = load(output)

            def json_value(value):
                return json.loads(json.dumps(value))

            for scope in SCOPES:
                with self.subTest(scope=scope):
                    resolved = resolve_settings(scope, config=loaded)
                    expected = {}
                    for key in settings_schema(scope)["settings"]:
                        node = resolved
                        for part in key.split("."):
                            node = node[part]
                        expected[key] = json_value(node)
                    self.assertEqual(raw["visual_toolkit"]["settings"][scope], expected)
            self.assertEqual(raw["visual_toolkit"]["settings"]["review"]["marker.color"], "#123456")
            self.assertEqual(raw["visual_toolkit"]["settings"]["brain-view"]["line_width"], 3.0)
            self.assertIn("display_gamma", raw["visual_toolkit"]["settings"]["montage"])
            bad = root / "bad.json"
            bad.write_text(json.dumps({"version": 1, "visual_toolkit": {"settings": {
                "montage": {"display_gamma": "not-a-number"}}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "montage"):
                initialize_default_config(output=str(root / "bad.yaml"), from_path=str(bad))
            self.assertFalse((root / "bad.yaml").exists())

    def test_loaded_settings_are_validated_for_every_scope(self):
        from vispa.dataset_config import load
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = {
                "review": {"marker.color": "not-a-color"},
                "brain-view": {"camera_distance_scale": 0},
                "montage": {"display_gamma": "not-a-number"},
            }
            for scope, values in cases.items():
                path = root / f"{scope}.json"
                path.write_text(json.dumps({"version": 1, "visual_toolkit": {
                    "settings": {scope: values}}}), encoding="utf-8")
                with self.subTest(scope=scope), self.assertRaisesRegex(
                        ValueError, rf"visual_toolkit\.settings\.{scope}"):
                    load(path)
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({"version": 1, "sources": {"brain_view": {
                "mesh_path": "brain.obj", "processed_swc_root": "swc",
                "settings": {"line_width": -1}}}}), encoding="utf-8")
            # The legacy source block stays descriptive at load time; the worker
            # preflight rejects invalid values when a 3D view is requested.
            self.assertEqual(load(legacy)["sources"]["brain_view"]["settings"],
                             {"line_width": -1})
            from vispa.opengl import resolve_settings as resolve_brain_view
            with self.assertRaisesRegex(ValueError, "line_width"):
                resolve_brain_view({"line_width": -1})

    def test_gui_validates_arguments_before_creating_configuration(self):
        from vispa import gui
        with tempfile.TemporaryDirectory() as temp:
            appdata = Path(temp)
            target = appdata / "VisPa" / "vispa_config.yaml"
            legacy = appdata / "legacy-config.json"
            env = {"APPDATA": str(appdata), "VISPA_CONFIG": "",
                   "VISUAL_TOOLKIT_CONFIG": str(legacy), "PROJECTOME_DATASETS": str(legacy)}
            with mock.patch.dict(os.environ, env):
                invalid = (["--sam", "252527"], ["--bogus"],
                           ["--conf", str(appdata / "x.json")],
                           ["--sample", "252527"])
                for argv in invalid:
                    with self.subTest(argv=argv), self.assertRaises(SystemExit) as raised, \
                            mock.patch.object(sys, "stderr", io.StringIO()):
                        gui.main(argv)
                    self.assertEqual(raised.exception.code, 2)
                    self.assertFalse(target.exists())
                with mock.patch.object(sys, "stdout", io.StringIO()):
                    self.assertEqual(gui.main(["--dry-run"]), 0)
                self.assertFalse(target.exists())

                class DummyRoot:
                    def mainloop(self):
                        self.looped = True

                root = DummyRoot()
                with mock.patch.object(gui.tk, "Tk", return_value=root), \
                        mock.patch.object(gui, "NeuroVisGUI") as gui_class, \
                        mock.patch.object(gui, "configure_data_sources", create=True):
                    self.assertEqual(gui.main(["--sample", "252527", "--neuron", "001.swc"]), 0)
                self.assertTrue(target.is_file())
                self.assertTrue(gui_class.called)
                self.assertTrue(root.looped)

    def test_scoped_config_settings_preserve_layers_and_validate_loaded_mappings(self):
        from vispa.dataset_config import load
        from vispa.settings import resolve_settings, settings_schema
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "visual.json"
            config_path.write_text(json.dumps({
                "version": 1,
                "visual_toolkit": {"settings": {
                    "review": {"marker.color": "#112233"},
                    "brain-view": {"camera_distance_scale": 0.45},
                    "montage": {"display_gamma": 0.95},
                }},
                "sources": {"brain_view": {"mesh_path": "brain.obj", "processed_swc_root": "swc",
                                                "settings": {"camera_distance_scale": 0.30,
                                                             "line_width": 3.0}}},
            }), encoding="utf-8")
            config = load(config_path)
            self.assertEqual(config["visual_toolkit"]["settings"]["review"]["marker.color"], "#112233")
            self.assertEqual(resolve_settings("review", ["marker.color=#445566"], config=config)["marker"]["color"], "#445566")
            brain = resolve_settings("brain-view", config=config)
            self.assertEqual(brain["camera_distance_scale"], 0.45)  # new scope overrides legacy source values
            self.assertEqual(brain["line_width"], 3.0)  # legacy source values remain supported
            self.assertEqual(resolve_settings("brain-view", ["camera_distance_scale=0.6"], config=config)["camera_distance_scale"], 0.6)
            self.assertEqual(resolve_settings("montage", ["display_gamma=0.8"], config=config)["display_gamma"], 0.8)
            self.assertEqual(settings_schema("review", config=config)["settings"]["marker.color"]["current"], "#112233")
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            resolve_settings("review", config={"visual_toolkit": {"settings": {"review": []}}})
        with self.assertRaisesRegex(ValueError, "unknown scope"):
            resolve_settings("review", config={"visual_toolkit": {"settings": {"mesh": {}}}})

    def test_gui_config_editor_preserves_json_yaml_and_rejects_invalid_settings_atomically(self):
        from vispa import gui
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            editor = object.__new__(gui.NeuroVisGUI)
            json_path = root / "config.json"
            original = json.dumps({"version": 1, "visual_toolkit": {"settings": {"review": {"marker.color": "#00e5ee"}}}})
            json_path.write_text(original, encoding="utf-8")
            with mock.patch.object(gui.messagebox, "showerror") as showerror:
                invalid = json.dumps({"version": 1, "visual_toolkit": {"settings": {"review": {"unknown.key": 1}}}})
                self.assertFalse(editor._save_config_text(json_path, invalid))
                self.assertEqual(json_path.read_text(encoding="utf-8"), original)
                showerror.assert_called_once()
                valid_json = json.dumps({"version": 1, "visual_toolkit": {"settings": {"review": {"marker.color": "#123456"}}}})
                self.assertTrue(editor._save_config_text(json_path, valid_json))
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["visual_toolkit"]["settings"]["review"]["marker.color"], "#123456")
            yaml_path = root / "config.yaml"
            yaml_path.write_text("version: 1\nvisual_toolkit:\n  settings:\n    montage:\n      display_gamma: 0.9\n", encoding="utf-8")
            with mock.patch.object(gui.messagebox, "showerror") as showerror:
                self.assertTrue(editor._save_config_text(yaml_path, yaml_path.read_text(encoding="utf-8")))
            self.assertIn("display_gamma: 0.9", yaml_path.read_text(encoding="utf-8"))
            self.assertTrue((root / "config_backups").is_dir())

    def test_backend_roots_resolve_without_extra_sample_directory(self):
        from vispa.toolkit import VisPa
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tool = VisPa("0007", cache_root=root / "resource" / "cubes",
                                  output_root=root / "resource" / "segmented_cubes")
            try:
                self.assertEqual(Path(tool.cache_http_dir), root / "resource" / "cubes" / "0007" / "high_res_http")
                self.assertEqual(Path(tool.output_dir), root / "resource" / "segmented_cubes" / "0007")
            finally:
                tool.close()

    def test_legacy_cache_dir_keeps_historical_output_location(self):
        from vispa.toolkit import VisPa
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tool = VisPa("0007", cache_dir=root)
            try:
                self.assertEqual(Path(tool.output_dir), root / "output")
                self.assertEqual(Path(tool.cache_http_dir), root / "cubes" / "0007" / "high_res_http")
            finally:
                tool.close()

    def test_ssh_source_is_scoped_to_declared_sample_unless_overridden(self):
        from vispa import toolkit
        with tempfile.TemporaryDirectory() as temp:
            toolkit.configure_data_sources(config={
                "defaults": {"cache_root": Path(temp) / "cache", "output_root": Path(temp) / "output"},
                "samples": {}, "sources": {
                    "ssh_host": "example.invalid", "ssh_port": 20007,
                    "ssh_user": "user", "ssh_remote_base": "/remote/251637",
                    "ssh_sample_id": "251637",
                },
            })
            try:
                other = toolkit.VisPa("252718")
                selected = toolkit.VisPa("251637")
                override = toolkit.VisPa("252718", low_res_ssh_base="/remote/explicit")
                try:
                    self.assertIsNone(other.low_res_ssh_base)
                    self.assertEqual(selected.low_res_ssh_base, "/remote/251637")
                    self.assertEqual(override.low_res_ssh_base, "/remote/explicit")
                finally:
                    other.close(); selected.close(); override.close()
            finally:
                toolkit.configure_data_sources(config={"defaults": {}, "samples": {}, "sources": {}})


    def test_corrupt_cached_tiff_is_replaced_after_tiff_header_error(self):
        import tifffile
        from vispa import context_resources as resources
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "high_res_http" / "3" / "1_2_3.tif"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"bad")

            class Toolkit:
                sample_id = "0007"
                cache_http_dir = str(root / "high_res_http")
                _block_errors = {}
                _download_http_block = mock.Mock(return_value="replacement")

            source = resources.BoundedCubeSource(root, min_free_bytes=1)
            with mock.patch.object(resources, "_read_highres_cube",
                                   side_effect=tifffile.TiffFileError("bad cached TIFF")):
                self.assertEqual(source(Toolkit(), 1, 2, 3), "replacement")
            Toolkit._download_http_block.assert_called_once_with(1, 2, 3)

    def test_cached_cube_precedes_http_configuration_and_invalid_cache_stays_explicit(self):
        import numpy as np
        from vispa import toolkit

        with tempfile.TemporaryDirectory() as temp:
            cache_root = Path(temp) / "high_res_http"
            cube = cache_root / "3" / "1_2_3.tif"
            cube.parent.mkdir(parents=True)
            cube.write_bytes(b"cached source bytes")

            class LocalToolkit:
                sample_id = "0007"
                cache_http_dir = str(cache_root)
                _block_errors = {}

            local = LocalToolkit()
            valid = np.zeros((90, 360, 360), dtype=np.uint8)
            with mock.patch.object(toolkit, "HTTP_HOST", None), \
                    mock.patch.object(toolkit, "_read_highres_cube", return_value=valid) as decode, \
                    mock.patch.object(toolkit.urllib.request, "urlopen") as network:
                self.assertIs(toolkit.VisPa._download_http_block(local, 1, 2, 3), valid)
                decode.assert_called_once_with(str(cube))
                network.assert_not_called()
                cube.unlink()
                with self.assertRaisesRegex(RuntimeError, "No cached cube or HTTP cube source"):
                    toolkit.VisPa._download_http_block(local, 1, 2, 3)
                cube.write_bytes(b"corrupt")
                decode.side_effect = ValueError("bad TIFF")
                with self.assertRaisesRegex(RuntimeError, "Cached cube is invalid.*bad TIFF"):
                    toolkit.VisPa._download_http_block(local, 1, 2, 3)
                self.assertEqual(local._block_errors[(1, 2, 3)], "bad TIFF")
                network.assert_not_called()


class SWCProviderTests(unittest.TestCase):
    def setUp(self):
        isolated = mock.patch.dict(os.environ, {"VISPA_CONFIG": ""})
        isolated.start()
        self.addCleanup(isolated.stop)

    def test_three_node_tree_emits_each_parent_child_link_once(self):
        from vispa.sources import read_swc
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tree.swc"
            path.write_text("1 1 1 2 3 1 -1\n2 3 2 3 4 0.5 1\n3 3 3 4 5 0.5 2\n", encoding="utf-8")
            tree = read_swc(path)
            self.assertEqual(tree.root.xyz, (1.0, 2.0, 3.0))
            self.assertEqual(len(tree.points), 3)
            self.assertEqual(len(tree.edges), 2)
            self.assertEqual([[p.id for p in edge.data] for edge in tree.edges], [[1, 2], [2, 3]])

    def test_missing_parent_cycle_and_disconnected_rows_fail(self):
        from vispa.sources import read_swc
        cases = {
            "missing": "1 1 0 0 0 1 -1\n2 3 1 1 1 1 99\n",
            "cycle": "1 1 0 0 0 1 -1\n2 3 1 1 1 1 3\n3 3 2 2 2 1 2\n",
            "disconnected": "1 1 0 0 0 1 -1\n2 3 1 1 1 1 -1\n",
        }
        for name, content in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "bad.swc"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_swc(path)

    def test_provider_uses_registered_fallback_when_local_entry_is_absent(self):
        from vispa import sources
        marker = object()
        class Remote:
            def getRawNeuronTreeByID(self, sample, neuron):
                return marker
        sources.set_iondata_provider_factory(lambda: Remote())
        try:
            self.assertIs(sources.IONData().getRawNeuronTreeByID("0007", "missing"), marker)
        finally:
            sources.set_iondata_provider_factory(None)

    def test_local_swc_cache_precedes_registered_fallback(self):
        from vispa import sources
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "swc" / "0007"
            folder.mkdir(parents=True)
            (folder / "001.swc").write_text("1 1 10 20 30 1 -1\n", encoding="utf-8")
            config = Path(temp) / "config.json"
            config.write_text(json.dumps({"version": 1,
                "defaults": {"swc_cache_root": str(Path(temp) / "swc")},
                "samples": {"0007": {"swc_cache": "0007"}}}), encoding="utf-8")
            prior = os.environ.get("VISPA_CONFIG")
            os.environ["VISPA_CONFIG"] = str(config)
            marker = object()
            class Remote:
                def getRawNeuronTreeByID(self, sample, neuron):
                    return marker
            def fail_if_constructed():
                raise AssertionError("fallback provider should not load for a local SWC hit")
            sources.set_iondata_provider_factory(fail_if_constructed)
            try:
                tree = sources.IONData().getRawNeuronTreeByID("0007", "001.swc")
                self.assertEqual(tree.root.xyz, (10.0, 20.0, 30.0))
            finally:
                sources.set_iondata_provider_factory(None)
                if prior is None:
                    os.environ.pop("VISPA_CONFIG", None)
                else:
                    os.environ["VISPA_CONFIG"] = prior

    def test_legacy_local_swc_root_is_tried_after_configured_cache_miss(self):
        from vispa import sources
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy = root / "legacy" / "0007"
            legacy.mkdir(parents=True)
            (legacy / "001.swc").write_text("1 1 7 8 9 1 -1\n", encoding="utf-8")
            provider = sources.LocalSWCProvider({
                "samples": {"0007": {"swc_cache": root / "empty_cache"}},
                "sources": {"legacy_raw_swc_root": root / "legacy"},
            })
            tree = provider.getRawNeuronTreeByID("0007", "001.swc")
            self.assertEqual(tree.root.xyz, (7.0, 8.0, 9.0))


if __name__ == "__main__":
    unittest.main()


class MarkerLabelPresentationTests(unittest.TestCase):
    def test_label_modes_preserve_marker_position_and_default_hide_inline_text(self):
        import matplotlib.pyplot as plt
        from vispa import toolkit
        tool = object.__new__(toolkit.VisPa)
        for mode, expected in ((None, ''), ('none', ''), ('short', 'S'), ('numbered', '1')):
            fig, ax = plt.subplots()
            try:
                result = tool._draw_target_marker(ax, 10, 20, label_mode=mode)
                self.assertEqual(result['label_text'], expected)
                self.assertEqual([text.get_text() for text in ax.texts], [expected] if expected else [])
                self.assertEqual(tuple(ax.collections[0].get_offsets()[0]), (10, 20))
                self.assertEqual(tuple(ax.lines[0].get_ydata()), (20, 20))
            finally:
                plt.close(fig)
        with self.assertRaisesRegex(ValueError, 'one of'):
            toolkit._parse_setting_value('marker.label_mode', 'unknown', 'none')
        self.assertEqual(toolkit._parse_setting_value('marker.label_mode', 'short', 'none'), 'short')

    def test_standalone_role_legends_clear_index_labels_and_preserve_image_extent(self):
        import matplotlib.pyplot as plt
        import numpy as np
        from vispa import toolkit
        with tempfile.TemporaryDirectory() as directory:
            tool = toolkit.VisPa('SYNTH', cache_dir=directory)
            volume = np.arange(3 * 120 * 120).reshape(3, 120, 120)
            real_close = plt.close
            try:
                with mock.patch.object(plt.Figure, 'savefig'), mock.patch.object(plt, 'close'):
                    soma = tool.plot_soma_block(volume, (0, 0, 0), (1, 1, 1), (60, 60, 1), '001')
                    figures = [plt.gcf()]
                    tool.plot_widefield_context(volume, (0, 0, 0), (5, 5, 3), (300, 300, 3), '001')
                    figures.append(plt.gcf())
                    tool.plot_sagittal_context(dict(soma), '001')
                    figures.append(plt.gcf())
                for fig in figures:
                    fig.canvas.draw()
                    renderer = fig.canvas.get_renderer()
                    self.assertEqual(len(fig.legends), 1)
                    self.assertGreater(fig.axes[0].get_tightbbox(renderer).y0,
                                       fig.legends[0].get_window_extent(renderer).y1)
                    self.assertEqual(tuple(fig.axes[0].images[0].get_extent()), (-0.5, 119.5, 119.5, -0.5))
                    self.assertIn('Source X', fig.axes[0].get_xlabel())
            finally:
                for fig in locals().get('figures', []):
                    real_close(fig)
                tool.close()
