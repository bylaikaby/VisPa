"""Focused lossless common-settings checks.

Version: 1.11.0.dev4 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md
"""
import unittest
from types import SimpleNamespace

from vispa.config_editor import FIELDS, apply_fields, field_value


class ConfigEditorTests(unittest.TestCase):
    def test_central_source_routes_are_exposed_without_fixed_hosts(self):
        paths = {key for _, key, _, _ in FIELDS}
        self.assertTrue({
            'defaults.ds00_root', 'defaults.resample_5um_root',
            'defaults.swc_root', 'defaults.swc_cache_root',
            'defaults.cache_root', 'defaults.output_root',
            'sources.neuron_catalog.host', 'sources.neuron_catalog.mode',
            'sources.neuron_catalog.path', 'sources.dataset_manifest',
            'sources.dataset_manifest_relative',
            'sources.legacy_raw_swc_root', 'sources.raw_swc_base',
            'sources.http_host', 'sources.http_path',
            'sources.brain_view.mesh_path', 'sources.brain_view.processed_swc_root',
            'visual_toolkit.fnt_tracer.server_base_url',
            'visual_toolkit.fnt_tracer.catalog_base_url',
            'visual_toolkit.fnt_tracer.cache_root',
            'sources.public_example.source_url', 'sources.public_example.metadata_url',
            'sources.public_example.record_id', 'sources.public_example.record_file',
            'sources.public_example.sha256',
        }.issubset(paths))
        self.assertFalse(any('10.10.' in label for _, _, label, _ in FIELDS))

    def test_form_round_trip_preserves_unexposed_scientific_values(self):
        source = {'version': 1, 'samples': {'252385': {'ds00_sha256': 'abc',
                  'resample_5um_policy': {'corrected': True, 'collection_counts': {'sections': 8262}}}},
                  'defaults': {'ds00_root': '../source'},
                  'visual_toolkit': {'settings': {'review': {'marker.min_px': 8.0}},
                                     'auto_load': False}}
        values = {key: (bool(field_value(source, key)) if kind == 'bool'
                        else '' if field_value(source, key) is None
                        else str(field_value(source, key))) for _, key, _, kind in FIELDS}
        self.assertEqual(apply_fields(source, values), source)
        values['defaults.ds00_root'] = '../changed'
        updated = apply_fields(source, values)
        self.assertEqual(updated['defaults']['ds00_root'], '../changed')
        self.assertEqual(updated['samples'], source['samples'])
        self.assertEqual(updated['visual_toolkit']['settings'], source['visual_toolkit']['settings'])
        self.assertEqual(source['defaults']['ds00_root'], '../source')

    def test_positive_timeout_is_validated(self):
        with self.assertRaisesRegex(ValueError, 'positive number'):
            apply_fields({'version': 1}, {'sources.neuron_catalog.timeout_seconds': '0'})
        with self.assertRaisesRegex(ValueError, 'positive whole number'):
            apply_fields({'version': 1}, {'visual_toolkit.fnt_tracer.timeout_seconds': '1.5'})
        with self.assertRaisesRegex(ValueError, 'live-iondata or csv'):
            apply_fields({'version': 1}, {'sources.neuron_catalog.mode': 'mystery'})
        with self.assertRaisesRegex(ValueError, '64 hexadecimal'):
            apply_fields({'version': 1}, {'sources.public_example.sha256': 'not-a-hash'})

    def test_fnt_controls_keep_own_cache_and_other_data(self):
        source = {'version': 1, 'visual_toolkit': {'fnt_tracer': {
            'auto_download': True, 'cache_root': None,
            'server_base_url': 'http://example.test/fnt',
            'catalog_base_url': 'http://example.test/catalog',
            'timeout_seconds': 30, 'max_response_bytes': 67108864}},
            'samples': {'252385': {'resample_5um_policy': {'corrected': True}}}}
        changed = apply_fields(source, {
            'visual_toolkit.fnt_tracer.auto_download': False,
            'visual_toolkit.fnt_tracer.cache_root': '',
            'visual_toolkit.fnt_tracer.timeout_seconds': '45'})
        self.assertFalse(changed['visual_toolkit']['fnt_tracer']['auto_download'])
        self.assertEqual(changed['visual_toolkit']['fnt_tracer']['timeout_seconds'], 45)
        self.assertIsNone(changed['visual_toolkit']['fnt_tracer']['cache_root'])
        self.assertEqual(changed['visual_toolkit']['fnt_tracer']['max_response_bytes'], 67108864)
        self.assertEqual(changed['samples'], source['samples'])

    def test_render_with_matching_cached_figures_still_fetches_fnt(self):
        from vispa.gui import NeuroVisGUI
        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        request = SimpleNamespace(sample_id='251637', neuron_id='003.swc')
        events = []
        gui._capture_processing_request = lambda: request
        gui._fingerprint = lambda: {'sample': '251637'}
        gui._find_cached_figures = lambda sample, neuron: ([], {'Soma': 'cached.png'}, {'key': 'matching'})
        gui._evaluate_cached = lambda entry, roles: ('same', [])
        gui.preview_label = object()
        gui.preview_files = {}
        gui._refresh_preview_tabs = lambda: events.append('preview')
        gui._show_role = lambda role: events.append(role)
        gui.update_status = lambda message: events.append('status')
        gui._append_log = lambda message: events.append('log')
        gui._start_fnt_fetch = lambda sample, neuron: events.append(('fnt', sample, neuron))
        gui._launch_processing = lambda process: events.append('rerender')
        gui.run_selected(roles=['Soma'])
        self.assertEqual(events.count(('fnt', '251637', '003')), 1)
        self.assertNotIn('rerender', events)
        self.assertEqual(gui.preview_files, {'Soma': 'cached.png'})

    def test_manifest_relative_and_explicit_switch_without_noop_loss(self):
        source = {'version': 1, 'defaults': {'ds00_root': r'\\server\DS00'},
                  'sources': {'dataset_manifest_relative': 'manifest.json',
                              'raw_swc_base': 'http://example.test/swc'}}
        self.assertEqual(apply_fields(source, {
            'sources.dataset_manifest_relative': 'manifest.json',
            'sources.dataset_manifest': ''}), source)
        explicit = apply_fields(source, {
            'sources.dataset_manifest_relative': 'manifest.json',
            'sources.dataset_manifest': r'D:\Data\manifest.json'})
        self.assertEqual(explicit['sources']['dataset_manifest'], r'D:\Data\manifest.json')
        self.assertNotIn('dataset_manifest_relative', explicit['sources'])
        self.assertEqual(explicit['sources']['raw_swc_base'], source['sources']['raw_swc_base'])
        relative = apply_fields(explicit, {
            'sources.dataset_manifest_relative': 'different/manifest.json',
            'sources.dataset_manifest': r'D:\Data\manifest.json'})
        self.assertEqual(relative['sources']['dataset_manifest_relative'], 'different/manifest.json')
        self.assertNotIn('dataset_manifest', relative['sources'])
        with self.assertRaisesRegex(ValueError, 'choose a path'):
            apply_fields({'version': 1, 'sources': {}}, {
                'sources.dataset_manifest_relative': 'manifest.json',
                'sources.dataset_manifest': r'D:\Data\manifest.json'})


if __name__ == '__main__':
    unittest.main()
