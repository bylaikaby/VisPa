"""Bounded job-preparation tests for exact animal identities and raw cache.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from batch.prepare_review_bulk import plan_jobs, prepare_jobs


class PrepareReviewBulkTests(unittest.TestCase):
    def test_exact_sources_are_cached_and_frozen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources" / "251637"
            sources.mkdir(parents=True)
            first = sources / "001.swc"
            second = sources / "002.swc"
            first.write_text("1 1 1 2 3 1 -1\n", encoding="utf-8")
            second.write_text("1 1 4 5 6 1 -1\n", encoding="utf-8")
            identities = root / "identities.csv"
            identities.write_text("sample,neuron_id\n251637,002.swc\n251637,001.swc\n")
            receipt = root / "sources.json"
            receipt.write_text(json.dumps({
                "sample_id": "251637", "raw_folder": str(sources), "manifest_count": 2,
                "source_files": [
                    {"id": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in (first, second)],
            }), encoding="utf-8")
            config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            cache = root / "cache" / "swc_raw"
            jobs_path = root / "jobs" / "prepared.json"
            plan = plan_jobs(config, "251637", identities, False, [sources.parent], cache,
                             receipt, None, True)
            self.assertEqual((plan["selected_count"], plan["available_count"]), (2, 2))
            self.assertFalse(cache.exists())
            result = prepare_jobs(plan, jobs_path, dry_run=False, allow_download=False)
            self.assertEqual(result["status"], "prepared")
            jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
            self.assertEqual([job["neuron_id"] for job in jobs["jobs"]], ["001.swc", "002.swc"])
            self.assertEqual(jobs["jobs"][0]["soma_xyz"], [1.0, 2.0, 3.0])
            self.assertEqual(jobs["jobs"][1]["soma_xyz"], [4.0, 5.0, 6.0])
            self.assertEqual(jobs["output_layout"], "sample_neurons")
            self.assertEqual(hashlib.sha256((cache / "251637/001.swc").read_bytes()).hexdigest(),
                             jobs["jobs"][0]["raw_swc_sha256"])

    def test_missing_cache_only_job_is_explicitly_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sources" / "251637"
            source.mkdir(parents=True)
            (source / "001.swc").write_text("1 1 1 2 3 1 -1\n", encoding="utf-8")
            identities = root / "identities.csv"
            identities.write_text("sample,neuron_id\n251637,001.swc\n251637,002.swc\n")
            config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            plan = plan_jobs(config, "251637", identities, False, [source.parent],
                             root / "cache", None, None, True)
            self.assertEqual(plan["missing_count"], 1)
            result = prepare_jobs(plan, root / "jobs/prepared.json", dry_run=False,
                                  allow_download=False)
            self.assertEqual((result["status"], result["prepared_count"], result["failed_count"]),
                             ("partial", 1, 1))

    def test_catalog_source_is_frozen_by_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = Path(__file__).parents[1] / "src/vispa/configs/config_deb.yaml"
            snapshot = {"source_kind": "live-iondata", "sha256": "a" * 64,
                        "count": 1, "rows": [{"neuron_id": "001.swc"}]}
            with mock.patch("batch.prepare_review_bulk.list_neurons", return_value=snapshot):
                plan = plan_jobs(config, "251637", None, True, [], root / "cache",
                                 None, 1, False)
            self.assertEqual(plan["identity_source"]["sha256"], "a" * 64)
            self.assertEqual(plan["jobs"][0]["neuron_id"], "001.swc")


if __name__ == "__main__":
    unittest.main()
