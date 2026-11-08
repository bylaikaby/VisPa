"""Bounded GUI bulk command and receipt-path contracts.

Version: 1.21.0 (local/unreleased)
Last updated: 2026-11-08
Change history: ../CHANGELOG.md
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from vispa.review_bulk_dialog import batch_receipt_path, bulk_command


class BulkReviewDialogContractTests(unittest.TestCase):
    def test_explicit_scope_and_receipt_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "profile.yaml"
            config.write_text("profile: test\n", encoding="utf-8")
            jobs = root / "jobs.json"
            jobs.write_text(json.dumps({"sample_id": "252527", "output_layout": "sample_neurons",
                                        "vispa_config": str(config)}),
                            encoding="utf-8")
            values = {"sample": "252527", "config": str(config), "jobs": str(jobs),
                      "output": str(root / "figures"), "cache": str(root / "cache"),
                      "source": "catalog", "csv": "", "raw_roots": "",
                      "source_receipt": "", "allow_download": False}
            preview = bulk_command("prepare_one_preview", values)
            self.assertIn("vispa.review_bulk_prepare", preview)
            self.assertEqual(preview[-3:], ["--limit", "1", "--dry-run"])
            self.assertNotIn("--allow-download", preview)
            prepared = bulk_command("prepare_all", values)
            self.assertEqual(prepared[-1], "--all")
            self.assertNotIn("--dry-run", prepared)
            render = bulk_command("render_all", values)
            self.assertIn("vispa.review_bulk_render", render)
            self.assertEqual(render[-2:], ["--all", "--resume"])
            resume = bulk_command("resume_all", values)
            self.assertEqual(resume[-2:], ["--all", "--resume"])
            digest = hashlib.sha256(jobs.read_bytes()).hexdigest()[:12]
            self.assertEqual(batch_receipt_path(jobs, root / "figures"),
                             (root / "figures").resolve() / "252527" / "bulk_runs" /
                             f"bulk_{digest}" / "batch_receipt.json")


if __name__ == "__main__":
    unittest.main()
