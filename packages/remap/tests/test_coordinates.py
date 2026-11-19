"""Bounded coordinate contract and saved-root parity checks.

Version: 0.1.0.dev12 (local/unreleased)
Last updated: 2026-11-03
Change history: ../CHANGELOG.md
Status: candidate
"""
import hashlib
import json
import unittest
from pathlib import Path

import numpy as np

from remap.ds_normalisation.coordinates import (Points, apply_saved_point_chain, convert_length_unit,
                               legacy_divide_250, lps_to_ras_mm, ras_mm_to_voxel,
                               ras_to_lps_mm, raw_to_native, voxel_to_ras_mm)
from remap.ds_normalisation.coordinates import (CoordinateRoute, ProinsDs00Route, SavedBridge, native_to_raw,
                               raw_to_5um_grid, grid_5um_to_raw, legacy_multiply_250,
                               map_swc_rows)


class CoordinateTests(unittest.TestCase):
    def test_roundtrip_and_frame_failures(self):
        p = Points([[1, 2, 3]], "native", "voxel")
        affine = np.diag([-0.1, -0.09, 0.1, 1.0])
        ras = voxel_to_ras_mm(p, voxel_frame="native", ras_frame="ras", affine=affine)
        np.testing.assert_allclose(ras_mm_to_voxel(ras, ras_frame="ras", voxel_frame="native", affine=affine).xyz, p.xyz)
        np.testing.assert_allclose(lps_to_ras_mm(ras_to_lps_mm(ras, ras_frame="ras", lps_frame="lps"), lps_frame="lps", ras_frame="ras").xyz, ras.xyz)
        np.testing.assert_allclose(convert_length_unit(convert_length_unit(ras, to_unit="um"), to_unit="mm").xyz, ras.xyz)
        with self.assertRaisesRegex(ValueError, "expected"):
            voxel_to_ras_mm(ras, voxel_frame="native", ras_frame="ras", affine=affine)
        with self.assertRaisesRegex(ValueError, "historical"):
            legacy_divide_250(Points([[250, 0, 0]], "raw_swc_xyz", "um"), target_frame="legacy")
        np.testing.assert_allclose(legacy_divide_250(Points([[250, 0, 0]], "legacy_swc_xyz", "unknown"), target_frame="legacy").xyz, [[1, 0, 0]])

    def test_axis_candidates_and_747_converter(self):
        p = Points([[100, 200, 90]], "raw_swc_xyz", "um")
        a = raw_to_native(p, native_frame="n", shape=(618, 643, 493), spacing_um=(100, 90, 100), candidate="A", converter="generic")
        b = raw_to_native(p, native_frame="n", shape=(618, 643, 493), spacing_um=(100, 90, 100), candidate="B", converter="generic")
        np.testing.assert_allclose(a.xyz, [[1, 1, 490]])
        np.testing.assert_allclose(b.xyz, [[1, 200/90, 492-90/100]])
        # Converter's verified voxel mapping: original (i,j,k) -> (Nj-1-j,k,Ni-1-i).
        special = raw_to_native(p, native_frame="747_native", shape=(684, 726, 520), spacing_um=(100, 90, 100), candidate="A", converter="special_747")
        np.testing.assert_allclose(special.xyz, [[681, 1, 518]])
        with self.assertRaises(ValueError):
            raw_to_native(p, native_frame="n", shape=(1, 2, 3), spacing_um=(100, 90, 100), candidate="C", converter="generic")
        for candidate in ("A", "B"):
            for converter in ("generic", "special_747"):
                native = raw_to_native(p, native_frame="n", shape=(684, 726, 520), spacing_um=(100, 90, 100), candidate=candidate, converter=converter)
                back = native_to_raw(native, native_frame="n", shape=(684, 726, 520), spacing_um=(100, 90, 100), candidate=candidate, converter=converter)
                np.testing.assert_allclose(back.xyz, p.xyz, atol=1e-10)

    def test_declared_5um_and_legacy_inverse(self):
        p = Points([[10, 20, 30]], "raw_swc_xyz", "um")
        calibration = np.diag([.2, .2, .2, 1])
        grid = raw_to_5um_grid(p, grid_frame="5um_image", raw_um_to_grid_voxel=calibration)
        np.testing.assert_allclose(grid.xyz, [[2, 4, 6]])
        np.testing.assert_allclose(grid_5um_to_raw(grid, grid_frame="5um_image", raw_um_to_grid_voxel=calibration).xyz, p.xyz)
        legacy = Points([[1, 2, 3]], "processed_swc_legacy", "voxel")
        np.testing.assert_allclose(legacy_multiply_250(legacy, source_frame="processed_swc_legacy").xyz, [[250, 500, 750]])
        vispa_geometry = Path(r"D:\VisPa_publish_20261023\work\vispa_main_20261102\src\vispa\image_geometry.py")
        if vispa_geometry.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location("vispa_image_geometry_checked", vispa_geometry)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            origin, spacing = np.array([40., 60., 90.]), np.array([5., 5., 3.])
            matrix = np.eye(4)
            matrix[:3, :3] = np.diag(1 / spacing)
            matrix[:3, 3] = -origin / spacing
            raw = Points([[50., 75., 99.]], "raw_swc_xyz", "um")
            mapped = raw_to_5um_grid(raw, grid_frame="5um_image", raw_um_to_grid_voxel=matrix)
            np.testing.assert_allclose(mapped.xyz[0], module.native_to_index(raw.xyz[0], origin, spacing))

    def test_route_and_graph_roundtrip(self):
        identity = np.eye(4)
        route = CoordinateRoute("native", (10, 20, 30), (100, 90, 100), identity,
                                "pitch", identity, "nmt_grid", identity, "A", "generic",
                                SavedBridge("native_lps", "pitch_lps", ("forward_pitch",), ("reverse_pitch",)),
                                SavedBridge("pitch_lps", "nmt_grid_lps", ("forward_nmt",), ("reverse_nmt",)))
        shifts = {"forward_pitch": [1, 2, 3], "reverse_pitch": [-1, -2, -3],
                  "forward_nmt": [4, 5, 6], "reverse_nmt": [-4, -5, -6]}
        def apply(xyz, chain):
            return xyz + shifts[chain[0]]
        raw = Points([[100, 200, 90], [200, 100, 180]], "raw_swc_xyz", "um")
        nmt = route.convert(raw, "nmt_grid", apply=apply)
        np.testing.assert_allclose(route.convert(nmt, "raw_swc_xyz", apply=apply).xyz, raw.xyz, atol=1e-10)
        rows = [(7, 2, 100., 200., 90., 3., -1), (8, 3, 200., 100., 180., 2., 7)]
        mapped = map_swc_rows(rows, route, source_frame="raw_swc_xyz", target_frame="nmt_grid", apply=apply)
        self.assertEqual([(r[0], r[1], r[5], r[6]) for r in mapped], [(7, 2, 3., -1), (8, 3, 2., 7)])
        with self.assertRaises(ValueError):
            route.convert(Points([[1, 2, 3]], "nmt_grid", "mm"), "native", apply=apply)
        route_with_options = CoordinateRoute("native", (10, 20, 30), (100, 90, 100), identity,
                                "pitch", identity, "nmt_grid", identity, "A", "generic",
                                route.native_pitch, route.pitch_nmt,
                                "5um_grid", np.diag([.2, .2, .2, 1]),
                                "processed_swc", identity)
        image5 = route_with_options.convert(raw, "5um_grid", apply=apply)
        np.testing.assert_allclose(route_with_options.convert(image5, "raw_swc_xyz", apply=apply).xyz, raw.xyz)
        processed = route_with_options.convert(raw, "processed_swc", apply=apply)
        self.assertEqual(processed.unit, "stored")
        np.testing.assert_allclose(route_with_options.convert(processed, "raw_swc_xyz", apply=apply).xyz, raw.xyz)
        without_binding = CoordinateRoute("native", (10, 20, 30), (100, 90, 100), identity,
                                "pitch", identity, "nmt_grid", identity, "A", "generic",
                                route.native_pitch, route.pitch_nmt,
                                "5um_grid", None, "processed_swc", None)
        with self.assertRaisesRegex(ValueError, "binding is unverified"):
            without_binding.convert(raw, "processed_swc", apply=apply)

    def test_proins_ds00_stage_order_roundtrip(self):
        identity = np.eye(4)
        route = ProinsDs00Route(
            (10, 20, 30), (100, 90, 100), identity, "A", "generic",
            "ds00_945_rigid",
            SavedBridge("native_nifti_lps", "ds00_945_rigid_lps", ("rigid_f",), ("rigid_r",)),
            identity, identity, identity,
            SavedBridge("shared_pitch10_lps", "nmt_lps", ("nmt_f",), ("nmt_r",)),
        )
        shifts = {"rigid_f": [1, 0, 0], "rigid_r": [-1, 0, 0], "nmt_f": [0, 2, 0], "nmt_r": [0, -2, 0]}

        def apply(xyz, chain):
            return xyz + shifts[chain[0]]

        raw = Points([[100, 200, 90]], "raw_swc_xyz", "um")
        native = route.convert(raw, "native_nifti", apply=apply)
        n4 = route.convert(native, "native_n4", apply=apply)
        np.testing.assert_allclose(n4.xyz, native.xyz)
        self.assertEqual(n4.frame, "native_n4")
        nmt = route.convert(raw, "nmt", apply=apply)
        self.assertEqual(nmt.frame, "nmt")
        np.testing.assert_allclose(route.convert(nmt, "raw_swc_xyz", apply=apply).xyz, raw.xyz, atol=1e-8)
        self.assertEqual(route.convert(raw, "ds00_945_rigid", apply=apply).frame, "ds00_945_rigid")

    def test_injected_point_chain_contract(self):
        p = Points([[1, 2, 3]], "native_lps", "mm")
        out = apply_saved_point_chain(p, source_frame="native_lps", target_frame="pitch_lps", transforms=["saved-affine"], apply=lambda xyz, chain: xyz + [1, 0, 0])
        np.testing.assert_allclose(out.xyz, [[2, 2, 3]])
        with self.assertRaises(ValueError):
            apply_saved_point_chain(p, source_frame="other", target_frame="pitch_lps", transforms=["saved-affine"], apply=lambda xyz, chain: xyz)

    def test_four_saved_945_roots(self):
        path = Path(r"D:\VisPa_publish_20261023\work\ds00_portal_region_comparison_20261103\945_252527_rawAxisA_nativeDS00_fourCell_receipt.json")
        if not path.is_file():
            self.skipTest("local scientific receipt unavailable")
        receipt = json.loads(path.read_text())
        spacing = np.linalg.norm(np.asarray(receipt["native_affine"])[:3, :3], axis=0) * 1000
        for row in receipt["rows"]:
            raw = Path(row["raw_swc"])
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), row["raw_sha256"])
            root = np.asarray([float(v) for v in next(line for line in raw.read_text().splitlines() if line and not line.startswith("#")).split()[2:5]])
            ijk = raw_to_native(Points(root[None, :], "raw_swc_xyz", "um"), native_frame="945_native", shape=receipt["native_shape"], spacing_um=spacing, candidate="A", converter="generic")
            ras = voxel_to_ras_mm(ijk, voxel_frame="945_native", ras_frame="945_ras", affine=receipt["native_affine"])
            np.testing.assert_allclose(ijk.xyz[0], row["root_ijk"], atol=1e-8)
            np.testing.assert_allclose(ras.xyz[0], row["root_ras_mm"], atol=1e-8)


if __name__ == "__main__":
    unittest.main()
