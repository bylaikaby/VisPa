"""Import boundaries and shared-state compatibility after the module refactor.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
"""
import importlib
from pathlib import Path
import subprocess
import sys
import unittest


class ModuleLayoutTests(unittest.TestCase):
    def test_config_resolves_without_loading_renderers(self):
        code = '''
import sys
from vispa import config
for scope in config.SCOPES:
    config.resolve_settings(scope)
assert not any(name in sys.modules for name in (
    "numpy", "matplotlib", "PIL", "OpenGL", "remap")), sorted(sys.modules)
assert not any(name.startswith("vispa.renderers.") for name in sys.modules)
'''
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_legacy_names_share_canonical_modules(self):
        pairs = {
            'dataset_config': 'config',
            'settings': 'config',
            'config_editor': 'config',
            'sources': 'data_input_adaptor',
            'toolkit': 'renderers.microscopy_panels',
            'opengl': 'renderers.swc_brain_view',
            'volume_montage': 'renderers.brain_volume_montage',
            'cli': 'commands',
            'review_cli': 'commands',
            'gui': 'reviewer',
            'review_gui': 'reviewer',
            'review_lock': 'batch_run_lock',
            'fnt': 'fnt_tracer_launcher',
            'readiness': 'input_resource_check',
            'terminal_qc': 'swc_terminal_candidates',
        }
        for old, canonical in pairs.items():
            with self.subTest(old=old):
                self.assertIs(importlib.import_module('vispa.' + old),
                              importlib.import_module('vispa.' + canonical))

    def test_one_packaged_profile_in_configs_folder(self):
        from vispa import config
        profile = config.packaged_config_path()
        self.assertEqual(profile.name, 'config_deb.yaml')
        self.assertEqual(profile.parent.name, 'configs')
        self.assertFalse(profile.parent.parent.joinpath('config_deb.yaml').exists())
        self.assertEqual([p.name for p in profile.parent.glob('*.yaml')], ['config_deb.yaml'])


if __name__ == '__main__':
    unittest.main()
