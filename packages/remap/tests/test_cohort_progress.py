"""Regression checks for the saved Progress Manager count contract.

Version: 0.2.2.dev3 (local/unreleased)
Last updated: 2026-11-18
Change history: ../CHANGELOG.md
2026-11-18: test blank selections and mismatches masked by equal totals.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from remap.cohort_progress import build_report


SNAPSHOT = (
    "generated_at,monkey_id,fmost_id,neurons_screened,selected_n,ARM_insula_n,"
    "arm_regions,insula_8_cohort\n"
    "2026-10-27,936,251637,10,2,1,Ial L 1 / R 0,DEB lab\n"
    ",747,250432,8,,1,Ig L 0 / R 1,Other lab\n"
    "2026-10-27,TOTAL,—,18,2,2,—,Table total\n"
)


class CohortProgressTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.csv = Path(directory.name) / "data_progress_table.csv"
        self.csv.write_text(SNAPSHOT, encoding="utf-8")
        self.receipt = Path(directory.name) / "receipt.json"
        self.entries = [
            dict(animal="936", neuron="251637_001", soma_side="L",
                 soma_region="CL_Ial", neuron_type="ITi"),
            dict(animal="747", neuron="250432_001", soma_side="R",
                 soma_region="CR_Ig", neuron_type="Unclassified"),
        ]

    def write_receipt(self):
        self.receipt.write_text(json.dumps(dict(selected_size=2, neurons=self.entries)),
                                encoding="utf-8")

    def test_preserves_blank_selection_and_counts_recorded_types(self):
        self.write_receipt()
        report = build_report(self.csv, self.receipt)
        self.assertEqual(report["totals"],
                         dict(left=1, right=1, screened=18, selected=2, atlas_insula=2))
        self.assertEqual(report["types"], {"ITi": 1, "Unclassified": 1})
        single = build_report(self.csv, sample="250432")
        self.assertIsNone(single["totals"]["selected"])
        self.assertIsNone(single["rows"][0]["source_row_date"])
        self.assertEqual(single["totals"]["atlas_insula"], 1)

    def test_rejects_side_mismatch_even_with_identical_cohort_size(self):
        self.entries[0].update(soma_side="R", soma_region="CR_Ial")
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "differ for 251637 / Ial"):
            build_report(self.csv, self.receipt)

    def test_rejects_duplicate_identities_and_unbalanced_progress_totals(self):
        self.entries[1] = self.entries[0]
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, "duplicate or unmatched cohort"):
            build_report(self.csv, self.receipt)
        self.csv.write_text(SNAPSHOT.replace("TOTAL,—,18", "TOTAL,—,19"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "totals or export date"):
            build_report(self.csv)
