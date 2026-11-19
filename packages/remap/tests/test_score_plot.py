"""Regression checks for the FNT score plot.

Version: 0.2.2.dev1 (local/unreleased)
Last updated: 2026-11-17
Change history: ../CHANGELOG.md
- 2026-11-17: Check dry-run, rendered provenance and output protection.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from PIL import Image
from tests.local_temp import local_temp


class ScorePlotTests(unittest.TestCase):
    def test_plot_and_existing_output_guard(self):
        with local_temp() as folder:
            root = Path(folder)
            joined, distance, output = (root / n for n in ("joined.fnt", "distance.tsv", "plot.png"))
            joined.write_text("0 Neuron a\n1 Neuron b\n2 Neuron c\n", encoding="utf-8")
            distance.write_text(
                "I\tJ\tScore\n0\t0\t0\n1\t1\t0\n2\t2\t0\n"
                "0\t1\t1\n0\t2\t2\n1\t2\t3\n", encoding="utf-8")
            args = [sys.executable, "-B", "-m", "remap.morph_clustering.score_plot",
                    "--distance", str(distance), "--joined-fnt", str(joined),
                    "--output", str(output), "--linkage", "complete"]
            dry = subprocess.run(args + ["--dry-run"], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(dry.stdout)["n_neurons"], 3)
            self.assertFalse(output.exists())
            subprocess.run(args, capture_output=True, text=True, check=True)
            with Image.open(output) as image:
                self.assertEqual(json.loads(image.info["Description"])["linkage"], "complete")
            before = output.read_bytes()
            failed = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()