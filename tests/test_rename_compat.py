"""VisPa rename compatibility contracts.
Version: 1.11.0.dev1 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md
"""
import os,subprocess,sys,unittest
from unittest.mock import patch
class RenameCompatibilityTests(unittest.TestCase):
 def test_qualified_alias_shares_settings_module(self):
  import vispa.settings as primary
  import Visual_toolkit.settings as legacy
  self.assertIs(primary,legacy)
 def test_qualified_toolkit_and_class_identity(self):
  import vispa.toolkit as primary
  import Visual_toolkit.toolkit as legacy
  self.assertIs(primary,legacy)
  self.assertIs(primary.VisPa,primary.Visual_toolkit)
 def test_primary_env_precedence_and_old_fallback(self):
  from vispa.dataset_config import config_path
  with patch.dict(os.environ,{"VISPA_CONFIG":"primary.yaml","VISUAL_TOOLKIT_CONFIG":"old.yaml"}):
   self.assertEqual(str(config_path()),"primary.yaml")
  with patch.dict(os.environ,{"VISPA_CONFIG":"","VISUAL_TOOLKIT_CONFIG":"old.yaml"}):
   self.assertEqual(str(config_path()),"old.yaml")
 def test_legacy_import_keeps_optional_gl_lazy(self):
  result=subprocess.run([sys.executable,"-c","import Visual_toolkit,sys; assert not any(n.startswith('vispa.legacy_gl') for n in sys.modules)"],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)

 def test_nested_legacy_leaf_identity_both_import_orders(self):
  for first,second in [("vispa.legacy_gl.SwcLoader","Visual_toolkit.legacy_gl.SwcLoader"),("Visual_toolkit.legacy_gl.SwcLoader","vispa.legacy_gl.SwcLoader")]:
   code=f"import importlib; a=importlib.import_module({first!r}); b=importlib.import_module({second!r}); assert a is b; assert a.__package__=='vispa.legacy_gl'; assert a.__spec__.name=='vispa.legacy_gl.SwcLoader'"
   result=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
