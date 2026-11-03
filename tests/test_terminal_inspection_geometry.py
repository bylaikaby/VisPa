"""Geometry regressions for the terminal context and anatomical overview.

Version: 1.13.0.dev5 (local/unreleased)
Last updated: 2026-11-03
Change history: ../CHANGELOG.md
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from vispa import terminal_inspection
from vispa.renderers import microscopy_panels as panels


class TerminalGeometryTests(unittest.TestCase):
    _work = Path(__file__).resolve().parents[1] / "work"

    def test_context_uses_target_xy_and_filters_table_sites_to_image_z_slab(self):
        image = np.arange(5 * 7 * 9, dtype=float).reshape(5, 7, 9)
        captured = {}

        def finalize(fig, ax, sx, sy, resolution, *args, **kwargs):
            captured.update(sx=sx, sy=sy, image=np.asarray(ax.images[0].get_array()),
                            coords=kwargs["soma_coords"])
            return "unused.png"

        renderer = SimpleNamespace(sample_id="sample", PANEL_FIGSIZE=(4, 4), PANEL_DPI=72,
                                   _overlay_swc=lambda *args: [], _finalize_plot=finalize,
                                   _title_text=lambda *args: "context")
        with mock.patch.object(panels, "resolve_widefield_parameters", return_value=(0.5, 0.0)):
            result = panels.VisPa.plot_widefield_context(
                renderer, image, (100, 200, 300), (10, 10, 10), (130, 230, 310),
                "004", swc_tree=None, recorded_sites_xyz_um=[
                    (120, 220, 305), (140, 240, 345), (150, 250, 355)])
        self.assertEqual((captured["sx"], captured["sy"]), (3, 3))
        self.assertEqual(captured["coords"], (130, 230, 310))
        self.assertEqual(captured["image"].shape, (7, 9, 3))
        self.assertEqual(result["fov_um"], (90, 70))
        self.assertEqual([(m[0], m[1]) for m in result["markers"][1:]],
                         [(2, 2), (4, 4)])

    def test_configured_panels_keep_soma_root_and_pass_terminal_target(self):
        self._work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._work) as temp:
            out = Path(temp)
            swc = out / "raw.swc"
            swc.write_text("1 1 100 200 300 1 -1\n2 2 130 230 310 1 1\n")
            from vispa.sources import read_swc
            tree = read_swc(swc)
            fake_tool = mock.Mock()
            fake_tool.plot_widefield_context.return_value = {"role": "context"}
            fake_tool.plot_tri_plot.return_value = str(out / "rendered.png")
            def render(*args, **kwargs):
                path = out / "rendered.png"
                path.write_bytes(b"png")
                return str(path)
            fake_tool.plot_tri_plot.side_effect = render
            prepared = {"panel": {"legend": [], "markers": [(1, 1, "cyan", None, "Target Terminal")], "notes": []}, "provenance": {
                "target_node_id": 2, "nifti_geometry": {
                    "spacing_mm_ijk": (0.1, 0.1, 0.1), "shape_ijk": (10, 10, 10)},
                "crop_jk": [0, 10, 0, 10], "slab_i_bounds": [1.5,2.5]}}
            with (mock.patch.object(terminal_inspection, "_configured_panels", wraps=terminal_inspection._configured_panels),
                  mock.patch.object(panels, "prepare_sagittal_panel", return_value=prepared) as sagittal,
                  mock.patch("vispa.toolkit.VisPa", return_value=fake_tool),
                  mock.patch("vispa.toolkit.configure_data_sources"),
                  mock.patch("vispa.config.load", return_value={})):
                terminal_inspection._configured_panels(
                    np.ones((5, 7, 9)), (100, 200, 300), (10, 10, 10), tree,
                    (130, 230, 310), [{"xyz_um": (140, 240, 345)}], "251637", "004",
                    2, swc, out, None, terminal_inspection.resolve_settings())
            context_call = fake_tool.plot_widefield_context.call_args
            self.assertEqual(context_call.args[3], (130, 230, 310))
            self.assertEqual(context_call.kwargs["recorded_sites_xyz_um"], [(140, 240, 345)])
            self.assertEqual(context_call.kwargs["target_label"], "Selected terminal")
            self.assertEqual(sagittal.call_args.args[:3], ("251637", "004", (100, 200, 300)))
            self.assertEqual(sagittal.call_args.kwargs["target_node_id"], 2)
            self.assertIn("Terminal 2 | provisional terminal region: unresolved",
                          fake_tool.plot_tri_plot.call_args.args[0][1]["title"])

    def test_full_sagittal_uses_terminal_plane_and_preserves_soma_provenance(self):
        self._work.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._work) as temp:
            swc = Path(temp) / "004.swc"
            swc.write_text("1 1 100 200 300 1 -1\n2 2 300 400 500 1 1\n")
            geometry = {"spacing_mm_ijk": (0.1, 0.1, 0.1), "shape_ijk": (10, 10, 10)}
            plane = np.arange(100, dtype=float).reshape(10, 10) + 1
            with (mock.patch.dict(panels.SAMPLE_PATHS, {"251637": {"monkey": "251637"}}),
                  mock.patch.object(panels, "_source_record", return_value={"path": "fake.nii"}),
                  mock.patch.object(panels, "_read_sagittal_planes", return_value=({3: plane}, geometry)) as read):
                result = panels.prepare_sagittal_panel(
                    "251637", "004", (100, 200, 300), swc_path=swc, target_node_id=2)
            panel, receipt = result["panel"], result["provenance"]
            self.assertEqual(read.call_args.args[1], (3,))
            self.assertEqual(panel["display"].shape, (10, 10))
            self.assertEqual(panel["markers"][0][:2], (5, 4))
            self.assertEqual(panel["markers"][0][4], "Target Terminal")
            self.assertEqual(receipt["swc"]["soma_xyz_um"], [100, 200, 300])
            self.assertEqual(receipt["target_xyz_um"], [300, 400, 500])
            self.assertEqual(receipt["target_node_id"], 2)
            self.assertEqual(receipt["crop_jk"], [0, 10, 0, 10])


if __name__ == "__main__":
    unittest.main()
