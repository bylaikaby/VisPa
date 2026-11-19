"""Registration paths keep os.path.relpath and survive a cross-drive pair."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remap.registration_path import legacy_registration_path


class RegistrationPathTests(unittest.TestCase):
    def test_same_anchor_matches_relpath(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "out" / "book.xlsx"
            anchor = root / "group_analysis" / "registry.json"
            self.assertEqual(
                legacy_registration_path(target, anchor.parent),
                os.path.relpath(target, anchor.parent),
            )

    def test_cross_drive_keeps_the_finished_target(self):
        with patch("remap.registration_path.os.path.relpath", side_effect=ValueError("different drives")):
            self.assertEqual(
                legacy_registration_path(r"D:\out\book.xlsx", r"C:\registry"),
                r"D:\out\book.xlsx",
            )


if __name__ == "__main__":
    unittest.main()
