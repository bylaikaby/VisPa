"""Focused checks for the bounded, public morphology-only example.

Version: 1.11.0.dev3 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from vispa import public_example as example


FIXTURE = b"1 1 0 0 0 1 -1\n2 3 1 2 3 0.5 1\n3 3 2 2 4 0.5 2\n"


def example_config(*, source_url="https://example.org/221747_1-qroot433.swc"):
    return {"defaults": {}, "sources": {"public_example": {
        "source_url": source_url,
        "metadata_url": "https://example.org/metadata.json",
        "record_id": "1", "record_file": "221747_1-qroot433.swc",
        "sha256": hashlib.sha256(FIXTURE).hexdigest(),
    }}}


class PublicExampleTests(unittest.TestCase):
    def test_cli_example_uses_builtin_source_when_profile_has_no_example_block(self):
        plan = example.run(dry_run=True, config={"defaults": {}, "sources": {}})["plan"]
        self.assertEqual(plan["source_url"], example.DEFAULT_SOURCE["source_url"])
        self.assertEqual(plan["source_sha256"], example.DEFAULT_SOURCE["sha256"])

    def test_swc_parser_rejects_invalid_tree_and_html(self):
        self.assertEqual(len(example.parse_swc(FIXTURE)), 3)
        for invalid in (
                b"<html>no swc</html>",
                b"1 1 0 0 0 1 -1\n1 2 1 0 0 1 1\n",
                b"1 1 0 0 0 1 -1\n2 3 nan 0 0 1 1\n",
                b"1 1 0 0 0 1 -1\n2 3 1 0 0 1 9\n",
                b"1 1 0 0 0 1 -1\n2 3 1 0 0 1 3\n",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    example.parse_swc(invalid)

    def test_dry_run_has_no_network_or_filesystem_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "out"
            cache = root / "cache"
            with mock.patch.object(example, "_read_url") as read_url:
                result = example.run(output_dir=output, cache_dir=cache, dry_run=True,
                                     config=example_config())
            read_url.assert_not_called()
            self.assertFalse(output.exists())
            self.assertFalse(cache.exists())
            self.assertFalse(result["written"])
            self.assertFalse(result["plan"]["network_access"])

    def test_profile_owns_urls_pin_and_cache_output_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            config = example_config(source_url="https://mirror.example.org/fixture.swc")
            config["defaults"] = {"cache_root": str(Path(folder) / "VisPa" / "cache"),
                                  "output_root": str(Path(folder) / "VisPa" / "output")}
            plan = example.run(config=config, dry_run=True)["plan"]
            original_plan = example.run(config=example_config(), dry_run=True)["plan"]
            self.assertEqual(plan["source_url"], "https://mirror.example.org/fixture.swc")
            self.assertNotEqual(Path(plan["cache_path"]).parent.name,
                                Path(original_plan["cache_path"]).parent.name)
            self.assertTrue(Path(plan["cache_path"]).is_relative_to(
                Path(folder) / "VisPa" / "cache" / "public-neuron-example"))
            self.assertTrue(Path(plan["output_png"]).is_relative_to(
                Path(folder) / "VisPa" / "output" / "public-neuron-example"))
            self.assertFalse((Path(folder) / "VisPa").exists())

    def test_missing_profile_pin_fails_before_cache_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            config = example_config()
            del config["sources"]["public_example"]["sha256"]
            with self.assertRaisesRegex(ValueError, "sources.public_example"):
                example.run(config=config, cache_dir=Path(folder) / "cache")
            self.assertFalse((Path(folder) / "cache").exists())
            config = example_config()
            config["sources"]["public_example"]["record_file"] = r"..\other.swc"
            with self.assertRaisesRegex(ValueError, "record_file"):
                example.run(config=config, dry_run=True, cache_dir=Path(folder) / "cache")
            self.assertFalse((Path(folder) / "cache").exists())

    def test_cached_source_validates_hash_and_render_receipt(self):
        digest = hashlib.sha256(FIXTURE).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache, output = root / "cache", root / "output"
            config = example_config()
            source = config["sources"]["public_example"]
            with mock.patch.object(example, "_read_url", return_value=FIXTURE) as read_url:
                result = example.run(output_dir=output, cache_dir=cache, dpi=100,
                                     config=config)
                self.assertTrue(Path(result["png"]).is_file())
                self.assertTrue(result["plan"]["network_access"])
                receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
                self.assertEqual(receipt["source"]["sha256"], digest)
                self.assertEqual(receipt["source"]["source_date"], None)
                self.assertEqual(receipt["source"]["coordinate_frame"], "unknown")
                self.assertEqual(receipt["source"]["coordinate_units"], "unknown")
                self.assertEqual(receipt["source"]["file"], "221747_1-qroot433.swc")
                self.assertEqual(receipt["geometry"]["node_count"], 3)
                self.assertEqual(receipt["processing"]["atlas"], None)
                self.assertFalse(receipt["processing"]["anatomical_acceptance"])
                self.assertEqual(receipt["render"]["output_sha256"], result["output_sha256"])
                self.assertEqual(receipt["render"]["renderer_code_sha256"],
                                 example._renderer_code_sha256())
                self.assertEqual(read_url.call_count, 1)
                with mock.patch.object(example, "_read_url", side_effect=AssertionError("cache miss")):
                    reused = example.run(output_dir=output, cache_dir=cache, dpi=100,
                                         config=config)
                self.assertTrue(reused["reused"])
                self.assertFalse(reused["written"])
                self.assertFalse(reused["plan"]["network_access"])
                self.assertEqual(reused["png"], result["png"])
                with mock.patch.object(example, "_renderer_code_sha256", return_value="f" * 64):
                    self.assertFalse(example._matching_existing(
                        Path(result["png"]), Path(result["receipt"]), digest, 100,
                        source))
                with mock.patch.object(example, "_read_url", side_effect=AssertionError("cache miss")):
                    source_path, rows, cached_hash, fetched = example._load_source(cache, source)
                self.assertEqual(cached_hash, digest)
                self.assertEqual(len(rows), 3)
                self.assertTrue(source_path.is_file())
                self.assertFalse(fetched)
                base_png = Path(result["png"])
                base_png.write_bytes(b"damaged existing image")
                with mock.patch.object(example, "_read_url", side_effect=AssertionError("cache miss")):
                    repaired = example.run(output_dir=output, cache_dir=cache, dpi=100,
                                           config=config)
                self.assertFalse(repaired["reused"])
                self.assertNotEqual(repaired["png"], str(base_png))
                self.assertEqual(base_png.read_bytes(), b"damaged existing image")
                source_path.write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "checksum"):
                    example._load_source(cache, source)

    def test_invalid_dpi_fails_before_cache_or_output_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            output, cache = Path(folder) / "out", Path(folder) / "cache"
            with self.assertRaisesRegex(ValueError, "dpi"):
                example.run(output_dir=output, cache_dir=cache, dpi=241,
                            config=example_config())
            self.assertFalse(output.exists())
            self.assertFalse(cache.exists())

    def test_config_defaults_and_cli_exposes_versioned_dry_run(self):
        from vispa._version import __version__
        import vispa.dataset_config as dataset_config
        from vispa.cli import _parser
        from vispa.gui import _parse_launch_args

        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "no-config.yaml"
            with mock.patch.object(dataset_config, "default_config_path", return_value=missing), \
                    mock.patch.object(dataset_config, "legacy_default_config_path",
                                       return_value=Path(temp) / "no-legacy.json"), \
                    mock.patch.dict(os.environ, {"VISPA_CONFIG": "",
                                                 "VISUAL_TOOLKIT_CONFIG": "",
                                                 "PROJECTOME_DATASETS": ""}):
                config = dataset_config.load()
        self.assertEqual(config["visual_toolkit"]["startup_mode"], "configured")
        self.assertEqual(config["visual_toolkit"]["default_sample"], "250432")
        self.assertEqual(config["visual_toolkit"]["default_neuron"], "001.swc")
        self.assertFalse(config["visual_toolkit"]["auto_load"])
        catalog = config["sources"]["neuron_catalog"]
        self.assertEqual(catalog["mode"], "live-iondata")
        self.assertEqual(catalog["host"], "http://10.10.48.110")
        parser = _parser()
        # Version appears in both command and subcommand help without loading data.
        for argv in (["--help"], ["example", "--help"]):
            output = io.StringIO()
            with self.subTest(argv=argv), mock.patch("sys.stdout", output):
                with self.assertRaises(SystemExit) as help_exit:
                    parser.parse_args(argv)
                self.assertEqual(help_exit.exception.code, 0)
                self.assertIn(__version__, output.getvalue())
        gui_output = io.StringIO()
        with mock.patch("sys.stdout", gui_output):
            with self.assertRaises(SystemExit) as gui_help:
                _parse_launch_args(["--help"])
        self.assertEqual(gui_help.exception.code, 0)
        self.assertIn(__version__, gui_output.getvalue())

if __name__ == "__main__":
    unittest.main()
