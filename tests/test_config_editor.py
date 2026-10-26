"""Focused lossless common-settings checks.

Version: 1.11.0.dev17 (local/unreleased)
Last updated: 2026-10-26
Change history: ../CHANGELOG.md
"""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from vispa.config_editor import FIELDS, apply_fields, field_value
from vispa._version import __version__


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
        }.issubset(paths))
        self.assertFalse(any(section == 'Public example' for section, *_ in FIELDS))
        self.assertFalse(any('public_example' in key for _, key, _, _ in FIELDS))
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
        source = {'sources': {'public_example': {'record_id': 'kept'}}}
        with self.assertRaises(KeyError):
            apply_fields(source, {'sources.public_example.record_id': 'edited'})
        self.assertEqual(source['sources']['public_example']['record_id'], 'kept')

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

    def test_partial_render_logs_sagittal_and_trio_dependency(self):
        from vispa.gui import NeuroVisGUI
        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        request = SimpleNamespace(sample_id='SYNTH', neuron_id='001.swc',
                                  plot_soma=True, plot_context=True, plot_sagittal=True,
                                  save_soma_png=False, save_context_png=False,
                                  save_sagittal_png=False, save_trio_png=False,
                                  save_outputs=False, output_dir='unused')
        gui.sample_id = SimpleNamespace(get=lambda: 'SYNTH')
        gui.neuron_id = SimpleNamespace(get=lambda: '001.swc')
        gui.preview_files = {}
        gui._capture_processing_request = lambda: request
        gui._fingerprint = lambda: None
        gui._target_for = lambda *args: 'unused'
        gui._render_soma = lambda *args: {'png_path': 'soma.png'}
        gui._render_context = lambda *args: {'png_path': 'context.png'}
        gui._render_sagittal = lambda *args: (_ for _ in ()).throw(FileNotFoundError(
            'Live manifest-selected preprocessed DS volume is unavailable: selected.nii'))
        gui._panel_png = lambda panel: panel['png_path']
        gui._register_outputs = lambda paths: gui.preview_files.update(
            {'Soma': paths[0], 'Context': paths[1]})
        logs, statuses = [], []
        gui._append_log = logs.append
        gui.update_status = statuses.append
        gui._ui_call = lambda callback, *args: callback(*args)
        gui.make_review_figure = SimpleNamespace(get=lambda: True)
        toolkit = SimpleNamespace(plot_tri_plot=mock.Mock())
        def finish_work(req, work, message):
            paths, errors = work(toolkit)
            gui._finish(req, paths, message(req), errors)
        gui._run_worker = finish_work
        with mock.patch('vispa.gui.IT.IONData', return_value=object()):
            gui.run_selected(force_rerender=True)
        self.assertEqual(gui.preview_files, {'Soma': 'soma.png', 'Context': 'context.png'})
        self.assertTrue(any('Sagittal render failed: Live manifest-selected preprocessed DS volume '
                            'is unavailable: selected.nii' in line for line in logs))
        self.assertTrue(any('Sagittal: this sample has no registered processed-DS sagittal source'
                            in line for line in logs))
        self.assertTrue(any('TrioPlot: requires Soma, Context and Sagittal; missing Sagittal'
                            in line for line in logs))
        toolkit.plot_tri_plot.assert_not_called()

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


class SettingsWindowTests(unittest.TestCase):
    def test_sections_raw_roundtrip_and_external_change_guard(self):
        import tkinter as tk
        from tkinter import ttk
        from vispa.gui import NeuroVisGUI

        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tk display unavailable: {exc}')
        root.withdraw()
        try:
            work = Path(__file__).parents[1] / 'work'
            work.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=work) as folder:
                path = Path(folder) / 'vispa_config.yaml'
                source = Path(__file__).parents[1] / 'src' / 'vispa' / 'config_deb.yaml'
                path.write_bytes(source.read_bytes())
                gui = NeuroVisGUI.__new__(NeuroVisGUI)
                gui.root, gui.config_path = root, str(path)
                gui._refresh_dataset_sources = lambda: None
                gui.update_status = lambda _message: None
                gui._open_config_yaml()
                root.update()
                window = gui._config_window

                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)

                widgets = list(descendants(window))
                tabs = next(item for item in widgets if isinstance(item, ttk.Notebook))
                section_list = next(item for item in widgets if isinstance(item, tk.Listbox))
                raw_text = next(item for item in widgets if isinstance(item, tk.Text))
                buttons = {item.cget('text'): item for item in widgets
                           if isinstance(item, ttk.Button)}
                self.assertEqual([tabs.tab(tab, 'text') for tab in tabs.tabs()],
                                 ['Organized editor', 'Raw YAML', 'Default YAML'])
                self.assertEqual(tabs.tab(tabs.select(), 'text'), 'Organized editor')
                self.assertEqual(section_list.get(0, 'end'),
                                 ('Data folders', 'Sources', 'Brain view', 'FNT', 'Startup'))
                self.assertIn(__version__, window.title())
                self.assertNotIn('Apply YAML to form', buttons)
                gui._on_fnt_setup()
                self.assertEqual(window._settings_section.get(), 'FNT')
                window._settings_section.set('Data folders')

                original = path.read_bytes()
                buttons['Save settings'].invoke()
                self.assertEqual(path.read_bytes(), original)

                folders = next(item for item in widgets if isinstance(item, ttk.LabelFrame)
                               and item.cget('text') == 'Data folders')
                entries = [item for item in folders.winfo_children()
                           if isinstance(item, ttk.Entry)]
                output_entry = next(item for item in entries if item.grid_info()['row'] == 5)
                root.setvar(output_entry.cget('textvariable'), 'D:/test_output')
                tabs.select(1)
                root.update()
                self.assertIn('output_root: D:/test_output', raw_text.get('1.0', 'end-1c'))
                edited = raw_text.get('1.0', 'end-1c').replace(
                    'output_root: D:/test_output', 'output_root: D:/another_output', 1)
                raw_text.delete('1.0', 'end')
                raw_text.insert('1.0', edited)
                tabs.select(0)
                root.update()
                self.assertEqual(root.getvar(output_entry.cget('textvariable')),
                                 'D:/another_output')
                buttons['Save settings'].invoke()
                self.assertIn(b'D:/another_output', path.read_bytes())
                self.assertIn(b'250432', path.read_bytes())

                tabs.select(1)
                root.update()
                invalid = raw_text.get('1.0', 'end-1c').replace(
                    'auto_download: true', 'auto_download: "false"', 1)
                raw_text.delete('1.0', 'end')
                raw_text.insert('1.0', invalid)
                tabs.select(0)
                root.update()
                self.assertEqual(tabs.tab(tabs.select(), 'text'), 'Raw YAML')
                self.assertNotIn(b'auto_download: "false"', path.read_bytes())
                buttons['Reload'].invoke()
                root.update()
                path.write_bytes(path.read_bytes() + b'\n# external edit\n')
                tabs.select(0)
                root.update()
                root.setvar(output_entry.cget('textvariable'), 'D:/third_output')
                buttons['Save settings'].invoke()
                self.assertIn(b'# external edit', path.read_bytes())
                self.assertNotIn(b'D:/third_output', path.read_bytes())

                window.destroy()
                path.write_bytes(original.replace(b'auto_download: true',
                                                  b'auto_download: "false"', 1))
                gui._open_config_yaml()
                root.update()
                repaired_window = gui._config_window
                repaired_widgets = list(descendants(repaired_window))
                repaired_tabs = next(item for item in repaired_widgets
                                     if isinstance(item, ttk.Notebook))
                repaired_text = next(item for item in repaired_widgets
                                     if isinstance(item, tk.Text))
                self.assertEqual(repaired_tabs.tab(repaired_tabs.select(), 'text'),
                                 'Raw YAML')
                self.assertIn('auto_download: "false"', repaired_text.get('1.0', 'end-1c'))
                error_labels = [root.getvar(item.cget('textvariable'))
                                for item in repaired_widgets if isinstance(item, ttk.Label)
                                and item.cget('textvariable')]
                self.assertTrue(any('needs correction' in value for value in error_labels))
                repaired_text.delete('1.0', 'end')
                repaired_text.insert('1.0', original.decode('utf-8'))
                repaired_tabs.select(0)
                root.update()
                self.assertEqual(repaired_tabs.tab(repaired_tabs.select(), 'text'),
                                 'Organized editor')

                repaired_window.destroy()
                path.write_bytes(b'version: [\n')
                gui._open_config_yaml()
                root.update()
                syntax_window = gui._config_window
                syntax_widgets = list(descendants(syntax_window))
                syntax_tabs = next(item for item in syntax_widgets
                                   if isinstance(item, ttk.Notebook))
                syntax_raw = next(item for item in syntax_widgets if isinstance(item, tk.Text))
                self.assertEqual(syntax_tabs.tab(syntax_tabs.select(), 'text'), 'Raw YAML')
                self.assertEqual(syntax_raw.get('1.0', 'end-1c'), 'version: [\n')
                syntax_raw.delete('1.0', 'end')
                syntax_raw.insert('1.0', original.decode('utf-8'))
                syntax_tabs.select(0)
                root.update()
                self.assertEqual(syntax_tabs.tab(syntax_tabs.select(), 'text'),
                                 'Organized editor')
        finally:
            root.destroy()

    def test_default_tab_reset_restore_and_distinct_backups(self):
        import tkinter as tk
        from tkinter import ttk
        from vispa.gui import NeuroVisGUI

        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tk display unavailable: {exc}')
        root.withdraw()
        try:
            work = Path(__file__).parents[1] / 'work'
            work.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=work) as folder:
                path = Path(folder) / 'vispa_config.yaml'
                source = Path(__file__).parents[1] / 'src' / 'vispa' / 'config_deb.yaml'
                original = source.read_bytes()
                path.write_bytes(original)
                gui = NeuroVisGUI.__new__(NeuroVisGUI)
                gui.root, gui.config_path = root, str(path)
                gui._refresh_dataset_sources = lambda: None
                gui.update_status = lambda _message: None
                gui._open_config_yaml()
                root.update()
                window = gui._config_window

                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)

                widgets = list(descendants(window))
                tabs = next(item for item in widgets if isinstance(item, ttk.Notebook))
                raw = next(item for item in widgets if isinstance(item, tk.Text))
                readonly = window._default_text
                buttons = {item.cget('text'): item for item in widgets
                           if isinstance(item, ttk.Button)}
                default_path = path.with_name('vispa_config.default.yaml')
                self.assertEqual(default_path.read_bytes(), original)
                self.assertEqual(readonly.cget('state'), 'disabled')
                folders = next(item for item in widgets if isinstance(item, ttk.LabelFrame)
                               and item.cget('text') == 'Data folders')
                output_entry = next(item for item in folders.winfo_children()
                                    if isinstance(item, ttk.Entry)
                                    and item.grid_info()['row'] == 5)
                root.setvar(output_entry.cget('textvariable'), 'D:/form_draft')
                tabs.select(2)
                root.update()
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(root.getvar(output_entry.cget('textvariable')),
                                 'D:/form_draft')
                tabs.select(1)
                root.update()
                self.assertIn('output_root: D:/form_draft', raw.get('1.0', 'end-1c'))
                raw_draft = raw.get('1.0', 'end-1c').replace(
                    'output_root: D:/form_draft', 'output_root: D:/raw_draft', 1)
                raw.delete('1.0', 'end')
                raw.insert('1.0', raw_draft)
                tabs.select(2)
                root.update()
                buttons['Save settings'].invoke()
                self.assertEqual(path.read_bytes(), original)
                tabs.select(1)
                root.update()
                self.assertEqual(raw.get('1.0', 'end-1c'), raw_draft)
                buttons['Save settings'].invoke()
                changed = path.read_bytes()
                self.assertIn(b'D:/raw_draft', changed)
                backups = path.parent / 'config_backups'
                first = list(backups.glob('vispa_config_*.yaml'))
                self.assertEqual(len(first), 1)
                self.assertEqual(first[0].read_bytes(), original)

                tabs.select(2)
                root.update()
                buttons['Reset to default'].invoke()
                root.update()
                self.assertEqual(path.read_bytes(), changed)
                self.assertEqual(default_path.read_bytes(), original)
                self.assertEqual(tabs.tab(tabs.select(), 'text'), 'Raw YAML')
                buttons['Save settings'].invoke()
                self.assertEqual(path.read_bytes().replace(b'\r\n', b'\n'),
                                 original.replace(b'\r\n', b'\n'))
                second = list(backups.glob('vispa_config_*.yaml'))
                self.assertEqual(len(second), 2)
                self.assertEqual(len({item.name for item in second}), 2)
                previous = next(item for item in second if item != first[0])
                self.assertEqual(previous.read_bytes(), changed)

                with mock.patch('vispa.gui.filedialog.askopenfilename',
                                return_value=str(previous)):
                    buttons['Restore backup…'].invoke()
                self.assertNotIn(b'D:/raw_draft', path.read_bytes())
                buttons['Save settings'].invoke()
                self.assertIn(b'D:/raw_draft', path.read_bytes())
                self.assertEqual(default_path.read_bytes(), original)

                before_failed_save = path.read_bytes()
                raw.insert('end', '\n# attempted edit')
                with (mock.patch('vispa.gui.os.makedirs', side_effect=OSError('backup unavailable')),
                      mock.patch('vispa.gui.messagebox.showerror') as show_error):
                    buttons['Save settings'].invoke()
                self.assertEqual(path.read_bytes(), before_failed_save)
                show_error.assert_called_once()

                window.destroy()
                default_path.write_bytes(b'version: [\n')
                gui._open_config_yaml()
                root.update()
                fallback_window = gui._config_window
                self.assertEqual(default_path.read_bytes(), b'version: [\n')
                self.assertEqual(fallback_window._default_text.get('1.0', 'end-1c').replace('\r\n', '\n'),
                                 original.decode('utf-8').replace('\r\n', '\n'))
                fallback_labels = [root.getvar(item.cget('textvariable'))
                                   for item in descendants(fallback_window)
                                   if isinstance(item, ttk.Label) and item.cget('textvariable')]
                self.assertTrue(any('Local default copy could not be used' in value
                                    for value in fallback_labels))
                with mock.patch('vispa.gui.messagebox.showerror') as protected_error:
                    self.assertFalse(gui._save_config_text(default_path, 'version: 1\n'))
                self.assertEqual(default_path.read_bytes(), b'version: [\n')
                protected_error.assert_called_once()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
