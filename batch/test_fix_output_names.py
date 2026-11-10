"""Tests for the current-record batch filename normalizer.

Version: 1.21.7 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from batch.fix_output_names import apply_sample, plan_sample
from vispa.render_records import animal_receipt_path


class BatchFilenameFixTests(unittest.TestCase):
    def test_plan_and_apply_canonical_names_and_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "figures" / "252385" / "neurons" / "031_L_G"
            plots = folder / "plots"
            plots.mkdir(parents=True)
            files = {
                "soma_plot": plots / "252385_031.swc_Left-G_old_Soma_Plot.png",
                "trio": folder / "252385_031.swc_Left-G_old_TriPlot.png",
                "nifti": folder / "252385_031.swc_Left-G_old_Soma.nii.gz",
                "swc": folder / "252385_031_L_G_3D_SWC.png",
            }
            for path in files.values():
                path.write_bytes(path.name.encode("utf-8"))
            nifti_sidecar = Path(str(files["nifti"]) + ".json")
            nifti_sidecar.write_text(json.dumps({
                "output_file": str(files["nifti"]),
            }), encoding="utf-8")
            swc_sidecar = files["swc"].with_suffix(".json")
            swc_sidecar.write_text(json.dumps({
                "snapshot_png": str(files["swc"]),
            }), encoding="utf-8")
            receipt = animal_receipt_path(root / "figures", "252385")
            receipt.write_text(json.dumps({
                "schema": "vispa.review.animal.v1",
                "sample_id": "252385",
                "current_batch": None,
                "batches": [],
                "neurons": {
                    "031.swc": {
                        "current": {
                            "outputs": {
                                "Soma": {"path": str(files["soma_plot"]), "sha256": "a"},
                                "TrioPlot": {"path": str(files["trio"]), "sha256": "b"},
                            },
                            "other_outputs": {
                                files["nifti"].name: {
                                    "path": str(files["nifti"]), "sha256": "c"},
                            },
                            "products": {
                                "SWC3D": {
                                    "output": {
                                        "path": str(files["swc"]), "sha256": "d"},
                                    "renderer": {"receipt": str(swc_sidecar)},
                                },
                            },
                        },
                        "history": [],
                    },
                },
            }), encoding="utf-8")
            template = "{sample}_{neuron}_{region_source}_{role}"
            plan = plan_sample(root / "figures", "252385", template)
            self.assertFalse(plan["conflicts"])
            apply_sample(plan)
            expected = {
                "soma_plot": folder / "plots" / "252385_031_atlas_L_G_Soma_Plot.png",
                "trio": folder / "252385_031_atlas_L_G_TrioPlot.png",
                "nifti": folder / "252385_031_atlas_L_G_Soma.nii.gz",
                "swc": folder / "252385_031_atlas_L_G_SWC3D.png",
            }
            for path in expected.values():
                self.assertTrue(path.is_file(), path)
            self.assertFalse(any(path.exists() for path in files.values()))
            record = json.loads(receipt.read_text(encoding="utf-8"))
            current = record["neurons"]["031.swc"]["current"]
            self.assertEqual(current["outputs"]["TrioPlot"]["path"], str(expected["trio"]))
            self.assertEqual(
                current["other_outputs"][expected["nifti"].name]["path"],
                str(expected["nifti"]))
            sidecar = json.loads(
                Path(str(expected["nifti"]) + ".json").read_text(encoding="utf-8"))
            self.assertEqual(sidecar["output_file"], str(expected["nifti"]))
            swc_receipt = json.loads(
                expected["swc"].with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(swc_receipt["snapshot_png"], str(expected["swc"]))


if __name__ == "__main__":
    unittest.main()
