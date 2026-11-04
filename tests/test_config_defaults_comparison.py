"""Read-only active/installed/frozen configuration comparison.

Version: 1.20.0 (local/unreleased)
Last updated: 2026-11-04
Change history: ../CHANGELOG.md
"""
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

import yaml

from vispa.config import compare_config_defaults, config_version_report, load, packaged_config_path


class ConfigDefaultsComparisonTests(unittest.TestCase):
    def test_version_metadata_is_first_class_and_legacy_files_remain_loadable(self):
        raw = yaml.safe_load(packaged_config_path().read_text(encoding="utf-8"))
        raw.update({
            "config_name": "ded_vispa_config",
            "config_version": "1.2.3",
            "config_updated_at": "2026-11-04T15:37:24+08:00",
        })
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ded_vispa_config_v1.0.6.yaml"
            path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            loaded = load(path)
            self.assertEqual(loaded["config_name"], "ded_vispa_config")
            self.assertEqual(loaded["config_version"], "1.2.3")
            report = config_version_report(path)
            self.assertEqual(report["config_name"], "ded_vispa_config")
            self.assertEqual(report["config_version"], "1.2.3")
            self.assertEqual(
                report["config_updated_at"], "2026-11-04T15:37:24+08:00")
            raw.pop("config_name")
            raw.pop("config_version")
            raw.pop("config_updated_at")
            legacy_path = Path(folder) / "legacy.yaml"
            legacy_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            self.assertEqual(load(legacy_path)["config_version"], "unversioned")

    def test_test_mode_only_redirects_writable_roots(self):
        raw = yaml.safe_load(packaged_config_path().read_text(encoding="utf-8"))
        raw["base_dir"] = str(Path(tempfile.gettempdir()) / "vispa-config-test")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ded_vispa_config_v1.0.6.yaml"
            path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            with mock.patch.dict(os.environ, {"VISPA_TEST_MODE": "1"}):
                loaded = load(path)
            self.assertTrue(loaded["test_mode"])
            self.assertEqual(loaded["samples"], load(path)["samples"])
            self.assertEqual(loaded["visual_toolkit"]["output_root"],
                             Path(raw["base_dir"]).parent / "output" / "vispa_test")
            self.assertEqual(loaded["defaults"]["cache_root"],
                             Path(raw["base_dir"]).parent / "cache" / "vispa_test")

    def test_report_preserves_active_bytes_and_separates_new_template_field(self):
        template = yaml.safe_load(packaged_config_path().read_text(encoding="utf-8"))
        active = yaml.safe_load(packaged_config_path().read_text(encoding="utf-8"))
        frozen = yaml.safe_load(packaged_config_path().read_text(encoding="utf-8"))
        active["sources"]["http_host"] = "http://local.example"
        active["sources"].pop("http_path")
        frozen["sources"].pop("http_path")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            active_path = root / "vispa_config.yaml"
            frozen_path = root / "vispa_config.default.yaml"
            active_path.write_text(yaml.safe_dump(active), encoding="utf-8")
            frozen_path.write_text(yaml.safe_dump(frozen), encoding="utf-8")
            before = active_path.read_bytes()
            report = compare_config_defaults(active_path)
            self.assertEqual(active_path.read_bytes(), before)
            self.assertIn("sources.http_path", report["missing_from_active"])
            self.assertIn("sources.http_path", report["introduced_since_frozen"])
            self.assertIn("sources.http_host", report["different_from_installed"])
            self.assertNotIn("http://local.example", str(report))
            self.assertEqual(template["sources"]["http_path"], "monkeydata")


if __name__ == "__main__":
    unittest.main()
