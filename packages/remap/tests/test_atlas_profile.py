"""Designated fMOST share atlas defaults.

Version: 0.2.2.dev1 (local/unreleased)
Last updated: 2026-11-17
Change history: ../CHANGELOG.md
- 2026-11-17: Make missing default atlas test independent of share availability.
Status: candidate

These checks resolve the packaged profile and override precedence. They do not
mount the share or read NIfTI bytes.
"""
import json
import unittest
from unittest.mock import patch
from pathlib import Path

import remap
from remap.atlas_profile import (
    NOT_DESIGNATED,
    SIBLING_ATLAS_TREE,
    apply_designated_atlas,
    designated_coordinate_scale_um,
    designated_population_paths,
    dormant_hierarchy_key_candidates,
    load_deb_atlas_profile,
    validate_share_atlas_path,
)
from remap.cli import build_parser
from remap.population_operator import plan_population


VISPA_COMMIT = "aed0077e1b9987a4a3aeac5507fc6f1a5688ff3c"
VISPA_ATLAS = {
    "root": r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\atlas\NMT_v2.1_sym\ARM_in_NMT_v2.1_sym.nii.gz",
    "key": r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\atlas\NMT_v2.1_sym\ARM_key_all.txt",
    "hemisphere_mask": r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\atlas\NMT_v2.1_sym\NMT_v2.1_sym_LR_plane.nii.gz",
    "version": "NMT_v2.1_sym",
    "coordinate_scale": 250,
}
TREE = r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\atlas\NMT_v2.1_sym"


def _population_files(tmp):
    root = Path(tmp)
    swc_dir = root / "swc"
    swc_dir.mkdir()
    (swc_dir / "001.swc").write_text("1 2 0 0 0 1 -1\n", encoding="utf-8")
    inputs = root / "inputs"
    inputs.mkdir()
    paths = {}
    for key, name in {
        "atlas": "atlas.nii.gz",
        "atlas_key": "key.txt",
        "template": "template.nii.gz",
        "hemisphere_mask": "mask.nii.gz",
        "cortex_hierarchy_csv": "charm.csv",
        "subcortical_hierarchy_csv": "sarm.csv",
    }.items():
        path = inputs / name
        path.write_bytes(b"local-override")
        paths[key] = str(path)
    config = {
        "sample_id": "sample1",
        "neuron_ids": ["001.swc"],
        "swc_source_dir": str(swc_dir),
        "output_base": str(root / "out"),
        "template": paths["template"],
        "cortex_hierarchy_csv": paths["cortex_hierarchy_csv"],
        "subcortical_hierarchy_csv": paths["subcortical_hierarchy_csv"],
    }
    return config, paths


class AtlasProfileTests(unittest.TestCase):
    def test_profile_copies_vispa_deb_atlas_paths(self):
        profile = load_deb_atlas_profile()
        atlas = profile["sources"]["atlas"]
        self.assertEqual(atlas, VISPA_ATLAS)
        self.assertEqual(profile["copied_from"]["commit"], VISPA_COMMIT)
        self.assertEqual(profile["copied_from"]["path"], "src/vispa/configs/config_deb.yaml")
        self.assertEqual(profile["copied_from"]["config_version"], "1.0.12")
        self.assertEqual(tuple(profile["not_designated"]), NOT_DESIGNATED)
        resolved = designated_population_paths()
        self.assertEqual(resolved["atlas"], VISPA_ATLAS["root"])
        self.assertEqual(resolved["atlas_key"], VISPA_ATLAS["key"])
        self.assertEqual(resolved["hemisphere_mask"], VISPA_ATLAS["hemisphere_mask"])
        self.assertEqual(designated_coordinate_scale_um(), 250.0)
        self.assertEqual(profile["sources"]["atlas"]["coordinate_scale"], 250)
        for path in resolved.values():
            self.assertTrue(path.startswith(TREE + "\\"))
            self.assertFalse(path.startswith(SIBLING_ATLAS_TREE + "\\"))
        text = json.dumps(profile)
        self.assertNotIn("projectome_analysis", text)
        self.assertNotIn("VisPa_publish", text)
        package = Path(remap.__file__).resolve().parent
        packaged = [path for path in package.rglob("*") if path.name.endswith((".nii", ".nii.gz"))]
        self.assertEqual(packaged, [])
        profile_yaml = package / "configs" / "config_deb.yaml"
        raw = profile_yaml.read_text(encoding="utf-8")
        self.assertIn("\\resources\\dependencies\\atlas\\", raw)
        self.assertNotIn("\\resources\\atlas\\", raw)
        self.assertFalse((package / "configs" / "deb_atlas.json").exists())
        self.assertLess(profile_yaml.stat().st_size, 10000)
        sibling = SIBLING_ATLAS_TREE + r"\NMT_v2.1_sym\ARM_in_NMT_v2.1_sym.nii.gz"
        with self.assertRaisesRegex(ValueError, "dependencies"):
            validate_share_atlas_path(sibling, "root")

    def test_omitted_paths_use_profile_and_explicit_paths_win(self):
        original = {"template": "/your/template.nii.gz", "atlas": None}
        merged = apply_designated_atlas(original)
        self.assertEqual(merged["atlas"], VISPA_ATLAS["root"])
        self.assertEqual(merged["atlas_key"], VISPA_ATLAS["key"])
        self.assertEqual(merged["hemisphere_mask"], VISPA_ATLAS["hemisphere_mask"])
        self.assertEqual(merged["template"], original["template"])
        self.assertNotIn("cortex_hierarchy_csv", merged)
        self.assertIsNone(original["atlas"])
        self.assertNotIn("atlas_key", original)
        custom = apply_designated_atlas({
            "atlas": r"D:\custom\atlas.nii.gz",
            "atlas_key": r"D:\custom\key.txt",
        })
        self.assertEqual(custom["atlas"], r"D:\custom\atlas.nii.gz")
        self.assertEqual(custom["atlas_key"], r"D:\custom\key.txt")
        self.assertEqual(custom["hemisphere_mask"], VISPA_ATLAS["hemisphere_mask"])
        with self.assertRaisesRegex(ValueError, "hemisphere_mask"):
            apply_designated_atlas({"hemisphere_mask": "  "})

    def test_population_override_precedes_share_default(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            config, paths = _population_files(folder)
            config.update({
                "atlas": paths["atlas"],
                "atlas_key": paths["atlas_key"],
                "hemisphere_mask": paths["hemisphere_mask"],
                "coordinate_scale": 250,
            })
            plan = plan_population(config)
            for name in ("atlas", "atlas_key", "hemisphere_mask"):
                self.assertEqual(plan["inputs"][name]["path"], str(Path(paths[name]).resolve()))
                self.assertNotIn("NMT_v2.1_sym", plan["inputs"][name]["path"])
            self.assertEqual(plan["atlas_profile"]["overrides"], ["atlas", "atlas_key", "hemisphere_mask"])
            self.assertEqual(plan["atlas_profile"]["vispa_commit"], VISPA_COMMIT)
            self.assertEqual(plan["declared_space"], "NMT_v2.1_sym atlas voxel index (caller declaration)")

    def test_population_omitted_atlas_resolves_to_share_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            config, paths = _population_files(folder)
            config["atlas_key"] = paths["atlas_key"]
            config["hemisphere_mask"] = paths["hemisphere_mask"]
            original_resolve = type(Path()).resolve

            def resolve_with_missing_atlas(path, *args, **kwargs):
                if str(path) == VISPA_ATLAS["root"] and kwargs.get("strict"):
                    raise FileNotFoundError(2, "fixture missing atlas", str(path))
                return original_resolve(path, *args, **kwargs)

            with patch.object(type(Path()), "resolve", resolve_with_missing_atlas):
                with self.assertRaises(FileNotFoundError) as caught:
                    plan_population(config)
            self.assertIn("ARM_in_NMT_v2.1_sym.nii.gz", caught.exception.filename)
            self.assertTrue(caught.exception.filename.startswith(TREE + "\\"))

    def test_population_requires_undesignated_inputs(self):
        with self.assertRaisesRegex(ValueError, "template"):
            plan_population({
                "sample_id": "sample1",
                "neuron_ids": ["001.swc"],
                "swc_source_dir": "swc",
                "output_base": "out",
                "cortex_hierarchy_csv": "charm.csv",
                "subcortical_hierarchy_csv": "sarm.csv",
            })
        with self.assertRaisesRegex(ValueError, "Unknown population config"):
            plan_population({"projectome_analysis": r"D:\projectome_analysis\atlas"})

    def test_one_defaults_match_profile_until_overridden(self):
        parser = build_parser()
        base = [
            "one", "--swc", "004.swc", "--sample-id", "251637", "--neuron-id", "004.swc",
            "--declared-space", "NMT_v2.1_sym atlas voxel index (caller declaration)",
            "--coordinate-scale", "250", "--output", "out.json",
        ]
        args = parser.parse_args(base)
        self.assertEqual(str(args.atlas), VISPA_ATLAS["root"])
        self.assertEqual(str(args.atlas_key), VISPA_ATLAS["key"])
        overridden = parser.parse_args(base + [
            "--atlas", r"D:\custom\atlas.nii.gz",
            "--atlas-key", r"D:\custom\key.txt",
        ])
        self.assertEqual(str(overridden.atlas), str(Path(r"D:\custom\atlas.nii.gz")))
        self.assertEqual(str(overridden.atlas_key), str(Path(r"D:\custom\key.txt")))
        self.assertNotEqual(str(overridden.atlas), VISPA_ATLAS["root"])
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as caught:
                build_parser().parse_args(["one", "--help"])
        self.assertEqual(caught.exception.code, 0)
        help_text = buffer.getvalue()
        self.assertIn(VISPA_ATLAS["root"], help_text)
        self.assertIn(VISPA_ATLAS["key"], help_text)
        population_buffer = io.StringIO()
        with contextlib.redirect_stdout(population_buffer):
            with self.assertRaises(SystemExit) as population_exit:
                build_parser().parse_args(["population", "--help"])
        self.assertEqual(population_exit.exception.code, 0)
        population_help = population_buffer.getvalue()
        self.assertIn(VISPA_ATLAS["root"], population_help)
        self.assertIn(VISPA_ATLAS["hemisphere_mask"], population_help)

    def test_dormant_hierarchy_search_prefers_share_key(self):
        candidates = dormant_hierarchy_key_candidates(r"D:\code\remap\region_analysis")
        self.assertEqual(candidates[0], VISPA_ATLAS["key"])
        self.assertFalse(any("projectome_analysis" in path for path in candidates))
        self.assertFalse(any("VisPa_publish" in path for path in candidates))


if __name__ == "__main__":
    unittest.main()
