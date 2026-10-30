"""Read-only operator and native FNT integration checks.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vispa import cli


class RefactorIntegrationTests(unittest.TestCase):
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
