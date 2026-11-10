"""Synthetic render-style regression checks.

Version: 1.21.7 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
2026-11-08: Exercise real optional-region exports and GUI Soma export provenance.
2026-11-08: Validate configured absent-source Context panel and TrioPlot.
2026-11-08: Reject mutated renderer style under a saved strict profile.
2026-10-30: Cover the fixed 320-pixel crosshair, reduced legacy square,
exact centre, and GUI receipt
fingerprint with a legacy 60-pixel profile.
2026-11-08: Cover configurable, smaller crosshair and optional centre box.
2026-11-08: Check thinner shared cross stroke and exposed figure style.
2026-11-08: Check combined selected/VisPa atlas Region title and no separate
sagittal hemisphere clause.
2026-11-09: Validate NIfTI affine, forms, units, and sidecar geometry metadata.
"""
import unittest
import sys
from pathlib import Path
import os
import tempfile
import json
from types import SimpleNamespace
from unittest import mock

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from vispa.renderers.microscopy_panels import VisPa
from vispa.config import REVIEW_SETTINGS, review_settings_schema
from vispa.data_input_adaptor import (atlas_source_token, display_region_name,
                                     region_display_label)
from vispa.reviewer import NeuroVisGUI, FIXED_CROSSHAIR_NOTICE
from vispa.renderers.swc_brain_view import TRACE_LABEL, _legend_texture


class OutputStyleTests(unittest.TestCase):
    def test_native_volume_export_with_and_without_region(self):
        import nibabel as nib
        with tempfile.TemporaryDirectory(dir=os.environ.get('VISPA_TEST_ROOT')) as directory:
            tool = object.__new__(VisPa)
            tool.sample_id = '251637'
            tool.output_dir = directory
            volume = np.arange(24, dtype=np.uint16).reshape(2, 3, 4)
            for region in (None, 'Right PrCO'):
                with self.subTest(region=region):
                    path = tool.export_data(volume, (10, 20, 30), (1, 2, 3),
                                            '004.swc', soma_region=region)
                    image = nib.load(path)
                    np.testing.assert_array_equal(image.get_fdata(),
                                                  volume.transpose(2, 1, 0))
                    expected_affine = np.diag([1.0, 2.0, 3.0, 1.0])
                    expected_affine[:3, 3] = [10, 20, 30]
                    np.testing.assert_allclose(image.affine, expected_affine)
                    self.assertEqual(int(image.header['qform_code']), 2)
                    self.assertEqual(int(image.header['sform_code']), 2)
                    self.assertEqual(int(image.header['xyzt_units']) & 0x07, 3)
                    metadata = json.loads(Path(path + '.json').read_text())
                    self.assertIsNone(metadata['center_xyz_um'])
                    self.assertEqual(metadata['nifti_affine_ijk_to_xyz_um'],
                                     expected_affine.tolist())

    def test_gui_soma_export_preserves_native_root_and_region(self):
        import nibabel as nib
        with tempfile.TemporaryDirectory(dir=os.environ.get('VISPA_TEST_ROOT')) as directory:
            tool = object.__new__(VisPa)
            tool.sample_id = '251637'
            tool.output_dir = directory
            tool.get_high_res_soma_window = mock.Mock(return_value=(
                np.ones((2, 3, 4), dtype=np.uint16), (10, 20, 30), (1, 2, 3)))
            tool.plot_soma_block = mock.Mock(return_value={})
            gui = object.__new__(NeuroVisGUI)
            gui._plot_region_context = {'display_label': 'Right PrCO'}
            gui._soma_window_px = mock.Mock(return_value=12)
            request = SimpleNamespace(soma_xyz=(11, 22, 33), neuron_id='004.swc',
                                      output_dir=directory, save_outputs=True,
                                      save_soma_nifti=True)
            panel = gui._render_soma(tool, request, directory)
            path = panel['_soma_nifti']
            self.assertIn('atlas_R_PrCO', Path(path).name)
            self.assertNotIn('(', Path(path).name)
            self.assertNotIn('[', Path(path).name)
            metadata = json.loads(Path(path + '.json').read_text())
            self.assertEqual(metadata['center_xyz_um'], [11, 22, 33])
            self.assertEqual(metadata['origin_xyz_um'], [10, 20, 30])
            image = nib.load(path)
            soma_voxel = (np.linalg.inv(image.affine)
                          @ np.asarray([11, 22, 33, 1.0]))
            np.testing.assert_allclose(soma_voxel[:3], [1, 1, 1])

    def test_declared_missing_context_renders_empty_panel_and_trio(self):
        from vispa.renderers import microscopy_panels as panels
        with tempfile.TemporaryDirectory(dir=os.environ.get('VISPA_TEST_ROOT')) as directory:
            tool = object.__new__(VisPa)
            tool.sample_id = '252383'
            tool.output_dir = directory
            declared = {'samples': {'252383': {'resample_5um': None}},
                        'visual_toolkit': {'missing_context_samples': ['252383']}}
            with mock.patch.object(panels, 'ACTIVE_CONFIG', declared):
                context = tool.plot_unavailable_context('001.swc', output_dir=directory)
                self.assertTrue(context['unavailable'])
                self.assertIsNone(context['display'])
                self.assertEqual(context['context_source_status'],
                                 'missing_declared_5um_source')
                self.assertEqual(context['markers'], [])
                with Image.open(context['output_png']) as png:
                    png.verify()
                fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
                try:
                    tool._draw_panel(ax, context)
                    fig.canvas.draw()
                    bounds = ax.get_window_extent(fig.canvas.get_renderer())
                    self.assertAlmostEqual(bounds.width / bounds.height, 1.0,
                                           places=6)
                    self.assertEqual(len(ax.images), 0)
                finally:
                    plt.close(fig)
                ordinary = {'display': np.ones((12, 12)), 'fov_um': (12, 12),
                            'depth_um': 1, 'resolution_um': (1, 1),
                            'scale_bar_um': 0, 'markers': []}
                trio = tool.plot_tri_plot([ordinary, context, ordinary], '001.swc',
                                          output_dir=directory)
                with Image.open(trio) as png:
                    png.verify()
            tool.sample_id = '252527'
            with mock.patch.object(panels, 'ACTIVE_CONFIG', declared):
                with self.assertRaisesRegex(ValueError, 'not authorized'):
                    tool.plot_unavailable_context('001.swc', output_dir=directory)

    def test_display_region_name_strips_only_hemisphere_id_prefix(self):
        native = {'status': 'verified', 'side': 'Right',
                  'source': {'atlas_region': 'CR_M1'}}
        self.assertEqual(region_display_label('M1_79', native),
                         'Portal: M1_79 | Atlas: Right M1 · atlas_CR_M1')
        self.assertEqual(atlas_source_token(native), 'atlas_CR_M1')
        self.assertEqual(display_region_name('CL_M1', 'Left'), 'M1')
        self.assertEqual(display_region_name('CR_M1', 'Left'), 'CR_M1')
        self.assertEqual(display_region_name('microCR_M1', 'Right'), 'microCR_M1')

    def test_all_panel_titles_use_one_region_section(self):
        tool = object.__new__(VisPa)
        tool.sample_id = "252384"
        combined = "Portal: Unassigned | Atlas: Left background"
        for suffix in ("Soma", "Context", "Sagittal"):
            title = tool._title_text(
                "003.swc", suffix, combined, (46139, 18014, 37393),
                (8000, 8000), 30)
            self.assertEqual(title.count("Region:"), 1)
            self.assertNotIn("| Atlas:", title)
            self.assertIn("Region: atlas_background", title)
            self.assertNotIn("nmt_corrected", title)
            corrected = tool._title_text(
                "003.swc", suffix, combined, (46139, 18014, 37393),
                (8000, 8000), 30, nmt_corrected="  Right   PrCO  ")
            self.assertIn(
                "Region: atlas_background · nmt_corrected=Right PrCO",
                corrected)
            self.assertNotIn("  ", corrected.splitlines()[1])
        simple = tool._title_text(
            "003.swc", "Context", "PrCO_49", (46139, 18014, 37393),
            (8000, 8000), 30)
        self.assertIn("Region: atlas_PrCO_49", simple)
        sourced = tool._title_text(
            "011.swc", "Sagittal", "ion_atlas=M1_79", (1, 2, 3),
            (57870, 49300), 100)
        self.assertIn("Region: atlas_M1_79", sourced)
        self.assertNotIn("nmt_portal=", sourced)
        checked = tool._title_text(
            "011.swc", "Context", "checked_region=M1_79", (1, 2, 3),
            (8000, 8000), 30)
        self.assertIn("Region: checked_region=M1_79", checked)
        vispa = tool._title_text(
            "011.swc", "Sagittal", "Portal: M1_79 | Atlas: Right CR_M1",
            (1, 2, 3), (57870, 49300), 100, hemisphere="Right")
        self.assertIn("Region: atlas_CR_M1", vispa)
        self.assertNotIn("Right_hemisphere", vispa)
        combined = tool._title_text(
            "011.swc", "Soma", "checked_region=M1_79 | Portal: M1_79 | Atlas: Right CR_M1",
            (1, 2, 3), (351, 351), 270)
        self.assertIn("Region: checked_region=M1_79 · atlas_CR_M1", combined)
        self.assertEqual(tool._region_title_value("nmt_portal=Left CL_M1"),
                         "atlas_CL_M1")
        self.assertEqual(tool._region_title_value("nmt_portal=Right microCR_M1"),
                         "atlas_microCR_M1")
        self.assertEqual(tool._region_title_value("nmt_portal=Right CR_M1",
                                                   "Left CL_PrCO"),
                         "atlas_CR_M1 · nmt_corrected=Left PrCO")
        unknown = tool._title_text(
            "011.swc", "Context", "Portal: M1_79 | Atlas: unavailable",
            (1, 2, 3), (8000, 8000), 30)
        self.assertIn("atlas_unavailable · portal_region=M1_79", unknown)
        self.assertEqual(
            VisPa._filename_region_source(
                "Portal: Ial_42 | Atlas: Right Ial · atlas_Ial"),
            "atlas_R_Ial")

    def test_gui_fingerprint_records_requested_and_effective_crosshair(self):
        self.assertIn('marker.crosshair_px', FIXED_CROSSHAIR_NOTICE)
        gui = object.__new__(NeuroVisGUI)
        values = {'x_coord': '7', 'y_coord': '11', 'z_coord': '13',
                  'soma_cubes': '1.5', 'width_um': '8000',
                  'height_um': '8000', 'depth_um': '30',
                  'sample_id': '251637', 'neuron_id': '004.swc'}
        for name, value in values.items():
            setattr(gui, name, mock.Mock(get=lambda value=value: value))
        gui._file_sha256 = lambda path: 'fixture-hash'
        with mock.patch.dict(REVIEW_SETTINGS['marker'], {'crosshair_px': 60.0}):
            fingerprint = gui._fingerprint()
        self.assertEqual(fingerprint['review_settings']['marker']['crosshair_px'], 60.0)
        self.assertEqual(fingerprint['effective_marker']['crosshair_arm_px'], 60.0)
        self.assertEqual(fingerprint['effective_marker']['box_mode'], 'off')
        self.assertEqual(fingerprint['effective_marker']['box_side_scale'], 0.65)
        legacy = dict(fingerprint)
        legacy.pop('effective_marker')
        old_entry = {'fingerprint': legacy, 'key': gui._fingerprint_key(legacy),
                     'outputs': {}}
        with mock.patch.dict(REVIEW_SETTINGS['marker'], {'crosshair_px': 60.0}):
            self.assertEqual(gui._evaluate_cached(old_entry)[0], 'differs')
            current_entry = {'fingerprint': fingerprint,
                             'key': gui._fingerprint_key(fingerprint), 'outputs': {}}
            self.assertEqual(gui._evaluate_cached(current_entry)[0], 'same')

    def test_default_crosshair_is_bounded_and_centered_in_display_pixels(self):
        self.assertEqual(review_settings_schema()['settings']['marker.crosshair_px']['default'], 120.0)
        self.assertEqual(review_settings_schema()['settings']['marker.box_mode']['default'], 'off')
        tool = object.__new__(VisPa)
        fig, ax = plt.subplots(figsize=(6, 4), dpi=123)
        try:
            with mock.patch.dict(REVIEW_SETTINGS['marker'], {'crosshair_px': 60.0}):
                result = tool._draw_target_marker(ax, 7, 11, crosshair_px=60,
                                                  label_mode='none')
            self.assertEqual(result['crosshair_px'], 60.0)
            self.assertEqual(result['box_mode'], 'off')
            self.assertEqual(len(ax.collections), 0)
            self.assertEqual([tuple(a.xyann) for a in ax.texts],
                             [(60, 0), (-60, 0), (0, 60), (0, -60)])
            self.assertTrue(all(tuple(a.xy) == (7, 11) for a in ax.texts))
            self.assertTrue(all(a.arrow_patch.get_linewidth() == 1.0
                                for a in ax.texts))
        finally:
            plt.close(fig)

    def test_swc_trace_role_uses_explicit_file_type(self):
        self.assertEqual(TRACE_LABEL, "Processed neuron SWC")

    def test_marker_is_centered_and_uses_display_pixels(self):
        tool = object.__new__(VisPa)
        for dpi in (100, 123, 200):
            fig, ax = plt.subplots(figsize=(6, 4), dpi=dpi)
            try:
                tool._draw_target_marker(ax, 7, 11, size_um=None,
                                         min_px=12, crosshair_px=16,
                                         label_mode='none', box_mode='on')
                fig.canvas.draw()
                self.assertEqual(tuple(fig.get_size_inches()), (6, 4))
                self.assertEqual(fig.dpi, dpi)
                self.assertTrue(np.allclose(ax.collections[0].get_offsets()[0], (7, 11)))
                self.assertAlmostEqual(np.sqrt(ax.collections[0].get_sizes()[0]) * dpi / 72, 12 * 0.65)
                self.assertEqual(ax.collections[0].get_edgecolors()[0][:3].tolist(),
                                 [0.0, 229 / 255, 238 / 255])
                self.assertEqual([tuple(a.xyann) for a in ax.texts],
                                 [(16, 0), (-16, 0), (0, 16), (0, -16)])
                self.assertTrue(all(tuple(a.xy) == (7, 11) for a in ax.texts))
            finally:
                plt.close(fig)

    def test_marker_arms_are_clipped_to_panel(self):
        tool = object.__new__(VisPa)
        fig, ax = plt.subplots(figsize=(3, 3), dpi=100)
        try:
            ax.set_xlim(0, 10)
            ax.set_ylim(0, 10)
            tool._draw_target_marker(ax, 0.2, 9.8, crosshair_px=120)
            self.assertTrue(all(arm.get_clip_on() and arm.arrow_patch.get_clip_on()
                                for arm in ax.texts))
            self.assertTrue(all(arm.get_clip_box() is not None and
                                arm.arrow_patch.get_clip_box() is not None
                                for arm in ax.texts))
        finally:
            plt.close(fig)

    def test_style_settings_apply_to_shared_panel_artists(self):
        tool = object.__new__(VisPa)
        fig, ax = plt.subplots(figsize=(4, 4), dpi=100)
        panel = {'display': np.zeros((20, 20)), 'fov_um': (20, 20),
                 'depth_um': 1, 'resolution_um': (1, 1), 'scale_bar_um': 5,
                 'axis_labels': ('X', 'Y'), 'markers': [(10, 10, '#00e5ee', None, 'Target')]}
        try:
            with mock.patch.dict(REVIEW_SETTINGS['marker'], {'linewidth': 0.7}), \
                 mock.patch.dict(REVIEW_SETTINGS['figure'],
                                 {'axis_label_fontsize': 8, 'tick_fontsize': 7,
                                  'scale_bar_linewidth': 1.5, 'scale_bar_fontsize': 9}):
                tool._draw_panel(ax, panel)
            self.assertEqual(ax.lines[-1].get_linewidth(), 1.5)
            self.assertEqual(ax.xaxis.label.get_fontsize(), 8)
            self.assertEqual(ax.get_xticklabels()[0].get_fontsize(), 7)
            self.assertEqual(ax.texts[-1].get_fontsize(), 9)
            self.assertTrue(all(arm.arrow_patch.get_linewidth() == 0.7
                                for arm in ax.texts[:4]))
            schema = review_settings_schema()['settings']
            for key in ('marker.linewidth', 'figure.panel_title_fontsize',
                        'figure.review_title_fontsize', 'figure.scale_bar_linewidth'):
                self.assertIn(key, schema)
        finally:
            plt.close(fig)

    def test_strict_renderer_rejects_mutated_global_style(self):
        import json
        import hashlib
        from vispa.config import load, resolve_settings
        from vispa.renderers import microscopy_panels as panels
        with tempfile.TemporaryDirectory(dir=os.environ.get('VISPA_TEST_ROOT')) as directory:
            path = Path(directory) / 'strict.json'
            path.write_text(json.dumps({'version': 1, 'visual_toolkit': {
                'enforce_render_config': True}}), encoding='utf-8')
            config = load(path)
            settings = resolve_settings('review', config=config)
            tool = object.__new__(VisPa)
            with mock.patch.object(panels, 'ACTIVE_CONFIG', config), \
                 mock.patch.object(panels, 'ACTIVE_CONFIG_SHA256',
                                   hashlib.sha256(path.read_bytes()).hexdigest()), \
                 mock.patch.object(panels, 'REVIEW_SETTINGS', settings):
                tool._assert_render_config()
                settings['marker']['linewidth'] = 8.0
                with self.assertRaisesRegex(ValueError, 'saved config'):
                    tool._assert_render_config()

    def test_strict_sagittal_entry_rejects_unsaved_display_variants(self):
        from vispa.renderers import microscopy_panels as panels
        with tempfile.TemporaryDirectory(dir=os.environ.get('VISPA_TEST_ROOT')) as directory:
            output = Path(directory) / 'not-created' / 'legacy.png'
            with mock.patch.object(panels, 'ACTIVE_CONFIG',
                                   {'visual_toolkit': {'enforce_render_config': True}}), \
                 mock.patch.dict(panels.SAMPLE_PATHS, {'SYNTH': {}}, clear=False):
                for options in ({'style': 'legacy'}, {'crop_half_width_mm': 5.0}):
                    with self.assertRaisesRegex(ValueError, 'saved config'):
                        panels.render_sagittal_context('SYNTH', '001', (1, 2, 3),
                                                       output, **options)
            self.assertFalse(output.parent.exists())

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

    def test_anisotropic_panel_keeps_full_extent_and_physical_aspect(self):
        tool = object.__new__(VisPa)
        fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
        try:
            panel = {'display': np.zeros((493, 643)), 'fov_um': (57870, 49300),
                     'resolution_um': (90, 100), 'scale_bar_um': 0,
                     'markers': []}
            tool._draw_panel(ax, panel)
            self.assertAlmostEqual(ax.get_aspect(), 100 / 90)
            self.assertEqual(tuple(ax.get_xlim()), (-0.5, 642.5))
            self.assertEqual(tuple(ax.get_ylim()), (492.5, -0.5))
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
                with mock.patch.object(tool, '_assert_render_config'):
                    result = tool._save_panel_plot(
                        panel, '001', 'Soma', output_dir=output)
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
