"""Tests for the extracted volume-rendering API.

Version: 1.12.0.dev1 (local/unreleased)
Last updated: 2026-10-29
Change history: vispa/CHANGELOG.md
Status: candidate
"""

import hashlib
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("VISPA_TEST_INSTALLED") != "1":
    sys.path.insert(0, str(ROOT / "src"))

from vispa import volume_montage as montage
from vispa import cli


def _synthetic_lps_nifti(path: Path) -> None:
    coords = np.indices((32, 34, 30), dtype=np.float32)
    x = (coords[0] - 15.0) / 12.5
    y = (coords[1] - 16.0) / 14.0
    z = (coords[2] - 13.0) / 11.0
    radius = x * x + y * y + z * z
    volume = np.zeros(radius.shape, dtype=np.float32)
    mask = radius < 1
    volume[mask] = 90 + 12 * (x[mask] + 1) + 7 * (y[mask] + 1) + 5 * (z[mask] + 1)
    volume[(x + 0.45) ** 2 + (y - 0.3) ** 2 + (z + 0.1) ** 2 < 0.08] = 155
    volume[(coords[0] > 16) & (coords[0] < 20) & (coords[1] > 12) & (coords[1] < 18) & (coords[2] > 10) & (coords[2] < 16)] = 0
    affine = np.array(
        [[-0.5, 0, 0, 20], [0, -0.6, 0, 40], [0, 0, 0.7, -5], [0, 0, 0, 1]],
        dtype=float,
    )
    image = nib.Nifti1Image(volume, affine)
    image.header.set_xyzt_units(xyz="mm")
    nib.save(image, str(path))


class VolumeMontageTests(unittest.TestCase):
    def test_synthetic_lps_render_covers_full_input_extent(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "synthetic.nii.gz"
            _synthetic_lps_nifti(source)
            result = montage.render_volume(source)
        self.assertEqual(montage.VIEW_KEYS, ("frontal", "superior", "back", "bottom", "coronal"))
        self.assertEqual(len(result["frames"]), 5)
        self.assertTrue(all(frame.ndim == 3 and frame.shape[-1] == 3 for frame in result["frames"]))
        self.assertTrue(all(float(frame.sum()) > 0 for frame in result["frames"]))
        self.assertEqual(len(result["extents_mm"]), 5)
        self.assertEqual(result["affine"][0], [-0.5, 0.0, 0.0, 20.0])
        self.assertEqual(result["voxel_axis_codes"], ["L", "P", "S"])
        self.assertEqual(result["world_axis_convention"], "RAS+")
        self.assertEqual(result["projection_bounds_source"],
                         "full input voxel-cell bounds; source affine; eight corners")
        source_affine = np.asarray(result["affine"])
        centroid = np.asarray(result["projection_origin_ras_world_mm"])
        axes = montage.anatomical_axes(source_affine)
        for key, extent in zip(montage.VIEW_KEYS, result["extents_mm"]):
            forward, up = montage.view_forward_up(axes, key)
            expected = montage.full_volume_projection_bounds((32, 34, 30), source_affine,
                                                               centroid, forward, up)
            np.testing.assert_allclose(extent, expected[:4], atol=1e-8)
        self.assertAlmostEqual(result["extents_mm"][0][1] - result["extents_mm"][0][0], 16.0, places=5)
        self.assertAlmostEqual(result["extents_mm"][0][3] - result["extents_mm"][0][2], 21.0, places=5)

    def test_generic_png_has_five_views_and_declared_projected_axes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "synthetic.nii.gz"
            output = Path(folder) / "one-case.png"
            _synthetic_lps_nifti(source)
            result = montage.render_volume(source)
            montage.save_single_volume_montage(result["frames"], result["extents_mm"], output, "synthetic local volume")
            with Image.open(output) as image:
                self.assertEqual(image.format, "PNG")
                self.assertGreater(image.width, image.height)
                self.assertGreater(output.stat().st_size, 1000)

    def test_settings_are_copied_and_invalid_values_fail(self):
        base = {"display_gamma": 1.1}
        result = montage.resolve_settings({"foreground_threshold": 0.1}, base=base)
        self.assertEqual(result["display_gamma"], 1.1)
        self.assertEqual(result["foreground_threshold"], 0.1)
        self.assertEqual(base, {"display_gamma": 1.1})
        with self.assertRaisesRegex(ValueError, "unknown montage setting"):
            montage.resolve_settings({"unknown": 1})
        with self.assertRaisesRegex(ValueError, "display_gamma"):
            montage.resolve_settings({"display_gamma": 0})

    def test_original_lps_guard_remains(self):
        with self.assertRaisesRegex(RuntimeError, "expected LPS axcodes"):
            montage.anatomical_axes(np.eye(4))

    def test_projected_axis_labels_follow_each_camera_basis(self):
        affine = np.array([[-1, 0, 0, 0], [0, -1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        self.assertEqual(montage.view_axis_labels(affine, "frontal"),
                         ("Left → Right (RAS+ mm)", "Inferior → Superior (RAS+ mm)"))
        self.assertEqual(montage.view_axis_labels(affine, "back"),
                         ("Right → Left (RAS+ mm)", "Inferior → Superior (RAS+ mm)"))
        self.assertEqual(montage.view_axis_labels(affine, "superior"),
                         ("Right → Left (RAS+ mm)", "Posterior → Anterior (RAS+ mm)"))
        self.assertEqual(montage.view_axis_labels(affine, "bottom"),
                         ("Left → Right (RAS+ mm)", "Posterior → Anterior (RAS+ mm)"))
        self.assertIn("oblique", montage.view_axis_labels(affine, "coronal")[0])

    def test_cli_dry_run_resolves_header_without_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "synthetic.nii.gz"
            output = root / "new-folder" / "montage.png"
            _synthetic_lps_nifti(source)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = cli.main(["montage", "--input", str(source), "--output", str(output),
                                 "--units", "mm", "--set", "max_dimension=100", "--dry-run"])
            plan = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(plan["schema"], "visual-toolkit.montage.v2")
            self.assertEqual(plan["shape_ijk"], [32, 34, 30])
            self.assertEqual(plan["settings"]["max_dimension"], 100)
            self.assertEqual(plan["coordinate_frame"], "NIfTI voxel order LPS; world coordinates RAS+; no additional transform")
            self.assertEqual(plan["voxel_axis_codes"], ["L", "P", "S"])
            self.assertEqual(plan["world_axis_convention"], "RAS+")
            self.assertIn("affine_ijk_to_world", plan)
            self.assertEqual(plan["declared_coordinate_units"], "mm")
            self.assertFalse(output.parent.exists())
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".json").exists())

    def test_cli_writes_one_png_and_hash_bound_receipt_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "synthetic.nii.gz"
            output = root / "result" / "montage.png"
            _synthetic_lps_nifti(source)
            original_input_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(cli.main(["montage", "--input", str(source), "--output", str(output),
                                       "--units", "mm", "--set", "figure_size_inches=[8,2]",
                                       "--set", "figure_dpi=72"]), 0)
            receipt_path = output.with_suffix(".json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], "visual-toolkit.montage.v2")
            self.assertEqual(receipt["projection_bounds_source"],
                             "full input voxel-cell bounds; source affine; eight corners")
            self.assertIn("projection_origin_ras_world_mm", receipt)
            self.assertIn("projected_extent_centroid_relative_mm", receipt["views"][0])
            self.assertNotIn("projected_extent_ras_world_mm", receipt["views"][0])
            self.assertEqual(receipt["status"], "rendered_candidate")
            self.assertEqual(receipt["input_sha256"], original_input_hash)
            self.assertEqual(receipt["sform_code"], 2)
            self.assertEqual(receipt["qform_code"], 0)
            self.assertEqual(receipt["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(len(receipt["views"]), 5)
            self.assertEqual(receipt["views"][0]["axis_labels"],
                             ["Left → Right (RAS+ mm)", "Inferior → Superior (RAS+ mm)"])
            self.assertEqual(receipt["settings"]["figure_size_inches"], [8.0, 2.0])
            self.assertEqual(receipt["settings"]["figure_dpi"], 72)
            self.assertTrue(receipt["runtime"]["volume_montage_sha256"])
            with Image.open(output) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (576, 144))
            with self.assertRaises(SystemExit):
                cli.main(["montage", "--input", str(source), "--output", str(output), "--units", "mm"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_input_hash)

    def test_cli_uses_scoped_yaml_settings_then_explicit_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "synthetic.nii.gz"
            output = root / "new" / "montage.png"
            config = root / "settings.json"
            _synthetic_lps_nifti(source)
            config.write_text(json.dumps({"version": 1, "visual_toolkit": {"settings": {
                "montage": {"display_gamma": 0.91, "figure_dpi": 72}}}}), encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = cli.main(["montage", "--input", str(source), "--output", str(output),
                                 "--units", "mm", "--config", str(config),
                                 "--set", "display_gamma=0.8", "--dry-run"])
            self.assertEqual(code, 0)
            plan = json.loads(stream.getvalue())
            self.assertEqual(plan["settings"]["display_gamma"], 0.8)
            self.assertEqual(plan["settings"]["figure_dpi"], 72)
            self.assertEqual(Path(plan["settings_config_path"]), config.resolve())
            self.assertFalse(output.parent.exists())

    def test_cli_rejects_non_lps_and_over_bound_inputs_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ras = root / "ras.nii.gz"
            ras_image = nib.Nifti1Image(np.ones((8, 9, 10), dtype=np.float32), np.eye(4))
            ras_image.header.set_xyzt_units(xyz="mm")
            nib.save(ras_image, str(ras))
            output = root / "review" / "candidate.png"
            with self.assertRaises(SystemExit):
                cli.main(["montage", "--input", str(ras), "--output", str(output), "--units", "mm", "--dry-run"])
            lps = root / "lps.nii.gz"
            lps_image = nib.Nifti1Image(np.ones((8, 9, 10), dtype=np.float32),
                                        np.diag([-1.0, -1.0, 1.0, 1.0]))
            lps_image.header.set_xyzt_units(xyz="mm")
            nib.save(lps_image, str(lps))
            with self.assertRaises(SystemExit):
                cli.main(["montage", "--input", str(lps), "--output", str(output),
                          "--units", "mm", "--max-voxels", "10", "--dry-run"])
            self.assertFalse(output.parent.exists())

    def test_cli_rejects_non_mm_header_units(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "meter-units.nii.gz"
            image = nib.Nifti1Image(np.ones((8, 9, 10), dtype=np.float32),
                                    np.diag([-1.0, -1.0, 1.0, 1.0]))
            image.header.set_xyzt_units(xyz="meter")
            nib.save(image, str(source))
            output = root / "review" / "candidate.png"
            with self.assertRaises(SystemExit):
                cli.main(["montage", "--input", str(source), "--output", str(output),
                          "--units", "mm", "--dry-run"])
            self.assertFalse(output.parent.exists())


if __name__ == "__main__":
    unittest.main()
