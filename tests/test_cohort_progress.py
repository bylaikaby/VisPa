"""Check the VisPa adapter for the shared ReMAP progress feature.

Version: 1.21.8.dev1 (local/unreleased)
Last updated: 2026-11-18
Change history: ../CHANGELOG.md
2026-11-18: verify sibling dispatch and the optional-dependency error.
"""
import unittest
from unittest.mock import patch

from vispa import cohort_progress
from vispa._version import __version__


class CohortProgressAdapterTests(unittest.TestCase):
    def test_shared_report_retains_vispa_receipt_schema(self):
        counts = {"schema": "remap.cohort_progress.v1", "remap_version": "0.2.2.dev3"}
        with patch.object(cohort_progress, "_progress_backend") as bridge:
            bridge.return_value.build_report.return_value = counts
            report = cohort_progress.build_report("progress.csv", "receipt.json", sample="251637")
            bridge.return_value.build_report.assert_called_once_with(
                "progress.csv", "receipt.json", sample="251637"
            )
        self.assertEqual(report["schema"], "vispa.cohort_progress.v1")
        self.assertEqual(report["vispa_version"], __version__)
        self.assertEqual(report["remap_version"], counts["remap_version"])

    def test_missing_backend_has_an_actionable_error(self):
        with patch.dict("sys.modules", {"remap": None}):
            with self.assertRaisesRegex(RuntimeError, "ReMAP.*run_vispa.py"):
                cohort_progress.build_report("progress.csv")
