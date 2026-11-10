"""Desktop launcher planning uses the installed package icon by default.

Version: 1.21.7 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from vispa.shortcuts import install_desktop_shortcuts, shortcut_specs


class ShortcutTests(unittest.TestCase):
    def test_dry_run_uses_packaged_icon_for_both_launchers(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "vispa_config.yaml"
            config.write_text("config_name: fixture\n", encoding="utf-8")
            plan = install_desktop_shortcuts(config, dry_run=True)
        self.assertTrue(plan["dry_run"])
        self.assertEqual({item["name"] for item in plan["specs"]},
                         {"VisPa.lnk", "VisPa Settings.lnk"})
        for item in plan["specs"]:
            icon = Path(item["icon_location"].rsplit(",", 1)[0])
            self.assertEqual(icon.name, "vispa.ico")
            self.assertTrue(icon.is_file())
            self.assertIn(
                f'-m vispa gui --config "{config}"', item["arguments"])
            self.assertTrue(
                item["target"].lower().endswith(("python.exe", "pythonw.exe")))
        settings = next(item for item in plan["specs"]
                        if item["name"] == "VisPa Settings.lnk")
        self.assertIn("--settings", settings["arguments"])
        self.assertIn("--no-autoload", settings["arguments"])

    def test_missing_active_config_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            shortcut_specs("D:/missing/VisPa/vispa_config.yaml")


if __name__ == "__main__":
    unittest.main()
