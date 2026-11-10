"""Read-only operator and native FNT integration checks.

Version: 1.21.4 (local/unreleased)
Last updated: 2026-11-08
Change history: ../CHANGELOG.md
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from vispa import cli


class RefactorIntegrationTests(unittest.TestCase):
    def test_gui_context_placeholder_requires_saved_missing_source_policy(self):
        from vispa.reviewer import NeuroVisGUI
        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        gui._plot_region_context = {'display_label': 'Portal: M1_79 | Atlas: unavailable'}
        request = SimpleNamespace(sample_id='252383', neuron_id='001.swc',
                                  soma_xyz=(1, 2, 3), width_um=8000,
                                  height_um=8000, depth_um=30)
        config = {'visual_toolkit': {'missing_context_samples': ['252383']},
                  'samples': {'252383': {'resample_5um': None}}}
        toolkit, ion = mock.Mock(), mock.Mock()
        toolkit.plot_unavailable_context.return_value = {
            'unavailable': True, 'context_source_status': 'missing_declared_5um_source',
            'unavailable_reason': '5 µm source missing', 'output_png': 'context.png'}
        panel = gui._render_context(toolkit, ion, request, 'output', config=config)
        self.assertTrue(panel['unavailable'])
        toolkit.plot_unavailable_context.assert_called_once()
        ion.getRawNeuronTreeByID.assert_not_called()
        configured_source = {'visual_toolkit': config['visual_toolkit'],
                             'samples': {'252383': {'resample_5um': 'declared/source'}}}
        ion.getRawNeuronTreeByID.return_value = None
        with self.assertRaisesRegex(ValueError, 'Raw neuron'):
            gui._render_context(toolkit, ion, request, 'output', config=configured_source)
        toolkit.plot_unavailable_context.assert_called_once()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / '252383' / 'neurons' / '001_Unassigned'
            output.mkdir(parents=True)
            png = output / '252383_001_Context_Plot.png'
            png.write_bytes(b'bounded placeholder fixture')
            gui._write_receipt(str(output),
                               {'sample': '252383', 'neuron': '001.swc',
                                'review_settings': {}},
                               {'Context': str(png)},
                               specs={'Context': gui._panel_spec(panel)})
            current = json.loads((Path(folder) / '252383' / 'process_log.json')
                                 .read_text(encoding='utf-8'))['neurons']['001.swc']['current']
            self.assertEqual(current['omissions'][0]['source_status'],
                             'missing_declared_5um_source')
            self.assertEqual(current['outputs']['Context']['availability']['reason'],
                             '5 µm source missing')

    def test_gui_folder_uses_verified_side_and_shared_animal_process_log(self):
        from vispa.reviewer import NeuroVisGUI, _figure_folder
        with tempfile.TemporaryDirectory() as folder:
            right = Path(_figure_folder(folder, '252527', '001.swc', 'M1_79', side='Right'))
            unknown = Path(_figure_folder(folder, '252527', '003.swc', 'M1_79'))
            self.assertEqual(right.name, '001_R_M1')
            self.assertEqual(unknown.name, '003_M1')
            right.mkdir(parents=True)
            plots = right / 'plots'
            plots.mkdir()
            png = plots / '252527_001_Soma_Plot.png'
            gui = NeuroVisGUI.__new__(NeuroVisGUI)
            gui._active_render_config = {
                'visual_toolkit': {'separate_plot_subfolder': 'plots'}}
            target = gui._target_for(SimpleNamespace(save_outputs=True,
                                                     output_dir=str(right)), True)
            self.assertEqual(target, str(plots))
            fingerprint = {'sample': '252527', 'neuron': '001.swc',
                           'config_sha256': 'config', 'review_settings': {}}
            png.write_bytes(b'first image')
            gui._write_receipt(str(right), fingerprint, {'Soma': str(png)})
            png.write_bytes(b'updated image')
            gui._write_receipt(str(right), fingerprint, {'Soma': str(png)})
            process_log = Path(folder) / '252527' / 'process_log.json'
            animal = json.loads(process_log.read_text(encoding='utf-8'))
            self.assertEqual(len(animal['neurons']['001.swc']['history']), 1)
            self.assertEqual(gui._read_receipt(str(right), '001')['output_dir'], str(right))
            gui.figure_output_root = folder
            gui.output_root = folder
            _folders, found, _entry = gui._find_cached_figures(
                '252527', '001', current_folder=str(right))
            self.assertEqual(found['Soma'], str(png))
            self.assertFalse((right / 'visual_gui_receipt.json').exists())

    def test_gui_worker_reloads_saved_profile_before_request_and_fingerprint(self):
        from vispa import reviewer
        from vispa.config import review_settings_snapshot
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'active.yaml'
            profile.write_text('revision: one\n', encoding='utf-8')
            first_sha = reviewer.hashlib.sha256(profile.read_bytes()).hexdigest()
            gui = reviewer.NeuroVisGUI.__new__(reviewer.NeuroVisGUI)
            gui.config_path = str(profile)
            gui.manual_path_set = True
            gui._ui_call = lambda callback, *args: callback(*args)
            gui._show_progress = mock.Mock()
            gui._hide_progress = mock.Mock()
            gui._apply_profile_fields = mock.Mock()
            gui._set_resolved_output_folder = mock.Mock()
            gui._store_render_region = mock.Mock()
            gui._log_operation = mock.Mock()
            gui._finish = mock.Mock()
            gui._fetch_fnt = mock.Mock()
            gui._launch_processing = lambda process: process()
            gui._resolve_plot_region = lambda req, config: {
                'display_label':
                    'Portal: M1_79 | Atlas: Right CR_M1 · atlas_CR_M1'}
            request = reviewer.make_processing_request(
                '252527', '001.swc', (1, 2, 3), 1, 100, 100, 30,
                str(Path(folder) / 'figures'), save_outputs=False, soma_cubes=1.5)
            seen = []
            settings = review_settings_snapshot()
            settings['context'].update(width_um=300, height_um=400, depth_um=50)
            settings['soma_window']['cubes_xy'] = 2.0
            config = {'path': profile, 'visual_toolkit': {'figure_output_root': folder}}
            with mock.patch('vispa.config.load', return_value=config), \
                 mock.patch('vispa.config.resolve_render_settings', return_value=settings), \
                 mock.patch('vispa.config.config_version_report', return_value={}), \
                 mock.patch('vispa.reviewer.configure_data_sources'), \
                 mock.patch('vispa.reviewer.VisPa') as toolkit:
                gui._run_worker(request, lambda worker, fresh, fingerprint: (
                    seen.append((fresh, fingerprint)) or ([], [])),
                    lambda req: 'done')
                profile.write_text('revision: two\n', encoding='utf-8')
                settings['context']['width_um'] = 600
                gui._run_worker(request, lambda worker, fresh, fingerprint: (
                    seen.append((fresh, fingerprint)) or ([], [])),
                    lambda req: 'done')
            fresh, fingerprint = seen[0]
            self.assertEqual((fresh.width_um, fresh.height_um, fresh.depth_um,
                              fresh.soma_cubes), (300, 400, 50, 2.0))
            self.assertEqual(fresh.output_dir,
                             reviewer._figure_folder(folder, '252527', '001.swc', 'Unassigned'))
            self.assertEqual(fingerprint['config_sha256'], first_sha)
            self.assertEqual(fingerprint['region']['display_label'],
                             'Portal: M1_79 | Atlas: Right CR_M1 · atlas_CR_M1')
            self.assertEqual(seen[1][0].width_um, 600)
            self.assertNotEqual(fingerprint['config_sha256'],
                                seen[1][1]['config_sha256'])
            self.assertEqual(seen[1][1]['config_sha256'],
                             reviewer.hashlib.sha256(profile.read_bytes()).hexdigest())
            self.assertEqual(toolkit.return_value.close.call_count, 2)

    def test_gui_uses_one_exact_catalog_and_native_atlas_label_for_panels(self):
        from vispa.reviewer import NeuroVisGUI
        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        gui.config_path = "active.yaml"
        gui._ui_call = mock.Mock()
        request = SimpleNamespace(sample_id="252527", neuron_id="001.swc",
                                  soma_xyz=(1, 2, 3), soma_cubes=1,
                                  save_outputs=False, save_soma_nifti=False,
                                  width_um=100, height_um=100, depth_um=100)
        catalog = {"rows": [{"neuron_id": "001.swc", "portal_region": "M1_79"}],
                   "source_kind": "catalog", "sha256": "abc"}
        native = {"status": "verified", "side": "Right",
                  "source": {"atlas_region": "CR_M1", "method": "native_atlas"}}
        with mock.patch("vispa.config.load", return_value={}), \
             mock.patch("vispa.reviewer.IT.list_neurons", return_value=catalog), \
             mock.patch("vispa.reviewer.IT.acquire_neuron_side", return_value=native):
            resolved = gui._resolve_plot_region(request)
        self.assertEqual(resolved["display_label"],
                         "Portal: M1_79 | Atlas: Right M1 · atlas_CR_M1")
        self.assertEqual(resolved["portal_source"]["sha256"], "abc")
        gui._plot_region_context = resolved
        toolkit = mock.Mock()
        toolkit.get_high_res_soma_window.return_value = ("volume", (0, 0, 0), (1, 1, 1))
        toolkit.get_low_res_widefield.return_value = ("volume", (0, 0, 0), (1, 1, 1))
        toolkit.render_sagittal_context_from_ds.return_value = {"panel": {}}
        gui._render_soma(toolkit, request, "target")
        gui._render_context(toolkit, mock.Mock(), request, "target")
        with mock.patch("vispa.renderers.microscopy_panels.resolve_swc_path",
                        return_value=(Path("001.swc"), {})):
            gui._render_sagittal(toolkit, request, "target")
        for call in (toolkit.plot_soma_block.call_args,
                     toolkit.plot_widefield_context.call_args,
                     toolkit.render_sagittal_context_from_ds.call_args):
            self.assertEqual(call.kwargs["soma_region"], resolved["display_label"])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / '252527' / 'neurons' / '252527_001_M1'
            output.mkdir(parents=True)
            png = output / "Soma_Plot.png"
            png.write_bytes(b"bounded fixture")
            gui._write_receipt(str(output), {"sample": "252527", "neuron": "001.swc"},
                               {"Soma": str(png)}, region_resolution=resolved)
            entry = json.loads((Path(folder) / '252527' / gui.RECEIPT_NAME).read_text())[
                "neurons"]["001.swc"]["current"]
            self.assertEqual(entry["region_resolution"]["portal_region"], "M1_79")
            self.assertEqual(entry["region_resolution"]["atlas_region"], "CR_M1")

    def test_gui_region_lookup_failure_keeps_unavailable_label(self):
        from vispa.reviewer import NeuroVisGUI
        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        gui.config_path = "active.yaml"
        request = SimpleNamespace(sample_id="252527", neuron_id="061.swc")
        with mock.patch("vispa.config.load", return_value={}), \
             mock.patch("vispa.reviewer.IT.list_neurons", side_effect=OSError("catalog offline")), \
             mock.patch("vispa.reviewer.IT.acquire_neuron_side", side_effect=OSError("atlas offline")):
            resolved = gui._resolve_plot_region(request)
        self.assertEqual(resolved["display_label"],
                         "Portal: Unassigned | Atlas: unavailable · atlas_unavailable")
        self.assertEqual(resolved["portal_error"], "catalog offline")
        self.assertEqual(resolved["atlas_error"], "atlas offline")

    def test_inputs_is_read_only_and_exact(self):
        config = {'sources': {'legacy_raw_swc_root': '/declared/raw'}, 'samples': {}}
        output = io.StringIO()
        with mock.patch('vispa.dataset_config.load', return_value=config), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(['inputs', '--sample', '0007', '--neuron', '001.swc', '--dry-run']), 0)
        plan = json.loads(output.getvalue())
        self.assertTrue(plan['dry_run'])
        self.assertEqual(plan['sample_id'], '0007')
        self.assertEqual(plan['resources']['processed_swc'], None)

    def test_native_plan_can_prepare_without_project(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root / 'raw' / '0007'
            raw.mkdir(parents=True)
            (raw / '001.swc').write_text('1 1 0 0 0 1 -1\n')
            exe = root / 'fnt.exe'
            converter = root / 'fnt-from-swc.exe'
            exe.write_bytes(b'executable fixture')
            converter.write_bytes(b'converter fixture')
            config = {'sources': {'legacy_raw_swc_root': raw.parent},
                      'visual_toolkit': {'fnt_tracer': {'executable': exe,
                                                        'converter_executable': converter,
                                                        'catalog_base_url': 'https://example.org/monkeydata',
                                                        'cache_root': root / 'cache'}}}
            plan = cli.fnt_plan(config, '0007', '001.swc')
            self.assertTrue(plan['can_prepare'])
            self.assertFalse(plan['ready'])
            self.assertIsNone(plan['project'])
            self.assertEqual(plan['raw_path'], str((raw / '001.swc').resolve()))

    def test_gui_fnt_handler_starts_background_worker(self):
        from vispa.gui import NeuroVisGUI
        instance = mock.Mock()
        instance.sample_id.get.return_value = '0007'
        instance.neuron_id.get.return_value = '001.swc'
        threads = []
        with mock.patch('vispa.gui.threading.Thread', side_effect=lambda **kwargs: threads.append(kwargs) or mock.Mock()):
            NeuroVisGUI._on_fnt_tracer(instance)
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]['name'], 'vispa-fnt-tools')

    def test_gui_fnt_worker_calls_borrowed_legacy_function(self):
        from vispa.reviewer import NeuroVisGUI
        instance = mock.Mock()
        instance.sample_id.get.return_value = '251637'
        instance.neuron_id.get.return_value = '004.swc'
        instance.config_path = 'lab.yaml'
        instance._ui_call = lambda callback, *args: callback(*args)
        threads = []
        result = {'project_path': '/cache/004.swc.fnt', 'pid': 123,
                  'log_path': '/cache/fnt.log'}
        with mock.patch('vispa.reviewer.threading.Thread', side_effect=lambda **kw: threads.append(kw) or mock.Mock()):
            NeuroVisGUI._on_fnt_tracer(instance)
        with mock.patch('vispa.config.load', return_value={'source': 'fixture'}), \
                mock.patch('vispa.fnt.swc_fnt_tracer', return_value=result) as legacy:
            threads[0]['target']()
        legacy.assert_called_once_with({'source': 'fixture'}, '251637', '004.swc')


if __name__ == '__main__':
    unittest.main()
