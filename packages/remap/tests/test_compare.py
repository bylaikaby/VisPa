"""Regression for saved-score comparison CLI.

Version: 0.2.2.dev1 (local/unreleased)
Last updated: 2026-11-17
Change history: ../CHANGELOG.md
- 2026-11-17: Check dry-run, ratio mode, output hashes and no-clobber.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tests.local_temp import local_temp


class CompareTests(unittest.TestCase):
    def test_comparison_and_output_guard(self):
        with local_temp() as folder:
            root = Path(folder)
            joined, distance, output = (root / n for n in ("joined.fnt", "distance.tsv", "run"))
            joined.write_text("".join(f"{i} Neuron n{i}\n" for i in range(5)), encoding="utf-8")
            distance.write_text("I\tJ\tScore\n" + "".join(
                f"{i}\t{j}\t{abs(i-j)}\n" for i in range(5) for j in range(i, 5)),
                encoding="utf-8")
            args = [sys.executable, "-B", "-m", "remap.morph_clustering.compare",
                    "--distance", str(distance), "--joined-fnt", str(joined), "--output", str(output),
                    "--min-k", "2", "--max-k", "2", "--repeats", "2"]
            dry = subprocess.run(args + ["--dry-run"], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(dry.stdout)["n_neurons"], 5)
            self.assertFalse(output.exists())
            subprocess.run(args, capture_output=True, text=True, check=True)
            self.assertTrue((output / "candidate_cluster_assignments.csv").is_file())
            before = (output / "metadata.json").read_bytes()
            metadata = json.loads(before)
            import hashlib
            expected_hash = hashlib.sha256((output / "candidate_cluster_assignments.csv").read_bytes()).hexdigest()
            self.assertEqual(metadata["result_sha256"]["candidate_cluster_assignments.csv"], expected_hash)
            self.assertFalse((output / "metadata.json.pending").exists())
            ratio_output = root / "ratio"
            distance.write_text("I\tJ\tScore\tMatch\tNoMatch\n" + "".join(
                f"{i}\t{j}\t{abs(i-j)}\t1\t1\n" for i in range(5) for j in range(i, 5)),
                encoding="utf-8")
            ratio_args = args.copy()
            ratio_args[ratio_args.index(str(output))] = str(ratio_output)
            ratio = subprocess.run(ratio_args + ["--score-mode", "ratio"], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(ratio.stdout)["score_mode"], "ratio")
            retry = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(retry.returncode, 0)
            self.assertEqual((output / "metadata.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()