"""Synthetic render-style regression checks.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
"""
import unittest
import sys
from pathlib import Path
import os
import tempfile
from unittest import mock

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from vispa.renderers.microscopy_panels import VisPa
from vispa.renderers.swc_brain_view import TRACE_LABEL, _legend_texture


class OutputStyleTests(unittest.TestCase):
    def test_swc_trace_role_uses_explicit_file_type(self):
        self.assertEqual(TRACE_LABEL, "Processed neuron SWC")

    def test_marker_is_centered_and_uses_display_pixels(self):
        tool = object.__new__(VisPa)
        for dpi in (100, 123, 200):
            fig, ax = plt.subplots(figsize=(6, 4), dpi=dpi)
            try:
                tool._draw_target_marker(ax, 7, 11, size_um=None,
                                         min_px=12, crosshair_px=16,
                                         label_mode='none')
                fig.canvas.draw()
                self.assertEqual(tuple(fig.get_size_inches()), (6, 4))
                self.assertEqual(fig.dpi, dpi)
                self.assertTrue(np.allclose(ax.collections[0].get_offsets()[0], (7, 11)))
                self.assertAlmostEqual(np.sqrt(ax.collections[0].get_sizes()[0]) * dpi / 72, 12)
                self.assertEqual([tuple(a.xyann) for a in ax.texts],
                                 [(16, 0), (-16, 0), (0, 16), (0, -16)])
                self.assertTrue(all(tuple(a.xy) == (7, 11) for a in ax.texts))
            finally:
                plt.close(fig)

    def test_panel_trace_style_matches_standalone_context(self):
        tool = object.__new__(VisPa)
        fig, ax = plt.subplots(figsize=(6, 4), dpi=123)
        try:
            segment = [np.array([[1., 1.], [3., 3.]])]
            panel = {'display': np.zeros((5, 5)), 'edge_segments': segment,
                     'markers': [], 'fov_um': (5, 5), 'resolution_um': (1, 1),
                     'scale_bar_um': 0}
            tool._draw_panel(ax, panel)
            self.assertEqual([round(c.get_linewidths()[0], 2) for c in ax.collections],
                             [1.4, 0.7])
            self.assertEqual([round(c.get_alpha(), 2) for c in ax.collections],
                             [0.55, 0.9])
        finally:
            plt.close(fig)

    def test_saved_panel_uses_export_dpi_before_marker_draw(self):
        tool = object.__new__(VisPa)
        tool.sample_id = 'SYNTH'
        tool.PANEL_FIGSIZE = (6, 4)
        tool.PANEL_DPI = 123
        panel = {'display': np.zeros((32, 32)), 'fov_um': (32., 32.),
                 'depth_um': 1., 'resolution_um': (1., 1.), 'scale_bar_um': 0.,
                 'markers': [(16., 16., '#00e5ee', None, 'Target',
                              {'min_px': 12, 'crosshair_px': 16})]}
        with tempfile.TemporaryDirectory(dir=os.environ.get('VISPA_TEST_ROOT')) as output:
            with mock.patch.object(tool, '_draw_target_marker', wraps=tool._draw_target_marker) as marker:
                result = tool._save_panel_plot(panel, '001', 'Soma', output_dir=output)
            self.assertEqual(marker.call_args.args[0].figure.dpi, 123)
            self.assertEqual(marker.call_args.args[0].figure.get_size_inches().tolist(), [6., 4.])
            with Image.open(result['output_png']) as png:
                self.assertGreater(png.width, 400)

    def test_gl_legend_fits_small_dark_and_light_windows(self):
        plan = {'sample_id': 'SYNTH', 'neuron_id': '001.swc',
                'mesh_label': 'Brain mesh',
                'settings': {'window_size': [100, 100], 'background': [1., 1., 1.],
                             'mesh_color': [0., 1., 0.], 'neuron_color': [1., 0., 0.],
                             'soma_color': [0., 1., 1.]}}
        light = _legend_texture(plan)
        self.assertLessEqual(light.width, 76)
        plan['settings']['background'] = [0., 0., 0.]
        dark = _legend_texture(plan)
        self.assertNotEqual(light.getpixel((0, 0)), dark.getpixel((0, 0)))

    def test_gl_legend_keeps_soma_region_meaning_in_compact_mode(self):
        plan = {'sample_id': 'SYNTH', 'neuron_id': '001.swc',
                'mesh_label': 'NMT mesh',
                'region_mesh': {'legend_label': 'Bilateral soma region · PrCO',
                                'compact_label': 'Soma · PrCO',
                                'color': [0.3, 0.7, 1.0]},
                'region_resolution': {'source': 'portal_region', 'requested': 'PrCO_49',
                                      'status': 'selected'},
                'settings': {'window_size': [180, 100], 'background': [0., 0., 0.],
                             'mesh_color': [.8, .8, .8], 'neuron_color': [1., .5, 0.],
                             'soma_color': [0., 1., 1.]}}
        image = _legend_texture(plan)
        self.assertLessEqual(image.width, 156)
        self.assertEqual(image.height, 98)


if __name__ == '__main__':
    unittest.main()
