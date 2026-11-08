"""Bounded GUI bulk command and receipt-path contracts.

Version: 1.21.1 (local/unreleased)
Last updated: 2026-11-08
Change history: ../CHANGELOG.md
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from vispa.review_bulk_dialog import BulkReviewDialog, batch_receipt_path, bulk_command


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

    def test_region_filter_is_forwarded_and_frozen_jobs_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "profile.yaml"
            config.write_text("profile: test\n", encoding="utf-8")
            output = root / "figures"
            jobs = root / "jobs.json"
            payload = {"sample_id": "252527", "vispa_config": str(config),
                       "figure_output_root": str(output),
                       "cache_root": str(root / "cache"),
                       "vispa_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                       "region_filter": {"labels": ["Iai_41", "M1_79"]}}
            jobs.write_text(json.dumps(payload), encoding="utf-8")
            values = {"sample": "252527", "config": str(config), "jobs": str(jobs),
                      "output": str(output), "cache": str(root / "cache"),
                      "source": "catalog", "csv": "", "raw_roots": "",
                      "source_receipt": "", "allow_download": False,
                      "regions": ["M1_79", "Iai_41"]}
            command = bulk_command("prepare_all", values)
            self.assertEqual(command[-5:], ["--all", "--region", "Iai_41",
                                            "--region", "M1_79"])
            BulkReviewDialog._validate_jobs(jobs, values, require_exists=True)
            with self.assertRaisesRegex(ValueError, "region selection"):
                BulkReviewDialog._validate_jobs(jobs, {**values, "regions": []})
            config.write_text("profile: revised\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "older profile revision"):
                BulkReviewDialog._validate_jobs(jobs, values)
            BulkReviewDialog._validate_jobs(jobs, values, view_only=True)
            payload.pop("figure_output_root")
            payload.pop("cache_root")
            jobs.write_text(json.dumps(payload), encoding="utf-8")
            BulkReviewDialog._validate_jobs(jobs, values, view_only=True)


if __name__ == "__main__":
    unittest.main()
