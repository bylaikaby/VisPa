"""Exact native FNT route, cache, and catalog-binding checks.

Version: 1.11.0.dev4 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md
"""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vispa.fnt import ensure_fnt, resolve_fnt_plan


class _Response(io.BytesIO):
    def __init__(self, data, declared_length=None, status=200):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if declared_length is None else declared_length)}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FNTFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {"visual_toolkit": {"fnt_tracer": {
            "cache_root": self.temp.name,
            "server_base_url": "http://10.10.48.110/www/upload/neuron",
            "catalog_base_url": "http://10.10.48.110/monkeydata",
            "timeout_seconds": 3,
            "max_response_bytes": 4096,
            "auto_download": True,
        }}}
        self.body = (b"Fast Neurite Tracer Session File 1.0\nNONE\n"
                     b"viewer.color.1=255\nBEGIN_TRACING_DATA\n1\n1\n")

    def test_exact_route_and_dry_run_have_no_side_effects(self):
        plan = resolve_fnt_plan(self.config, "250432", "001.swc")
        self.assertEqual(plan["url"], "http://10.10.48.110/www/upload/neuron/250432/250432/merge/250432-001-merge.fnt")
        with patch("vispa.fnt.urllib.request.urlopen") as opener:
            result = ensure_fnt(self.config, "250432", "001.swc", dry_run=True)
        self.assertEqual(result["status"], "planned")
        opener.assert_not_called()
        self.assertFalse(Path(plan["source_path"]).exists())

    def test_endpoint_urls_must_come_from_editable_config(self):
        config = {"visual_toolkit": {"fnt_tracer": {"cache_root": self.temp.name}}}
        result = ensure_fnt(config, "250432", "001.swc", dry_run=True)
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("server_base_url and catalog_base_url", result["errors"][0])

    def test_shared_vispa_cache_root_is_used_when_fnt_override_is_null(self):
        self.config["defaults"] = {"cache_root": str(Path(self.temp.name) / "VisPa" / "cache")}
        self.config["visual_toolkit"]["fnt_tracer"]["cache_root"] = None
        plan = resolve_fnt_plan(self.config, "250432", "001.swc")
        self.assertTrue(Path(plan["source_path"]).is_relative_to(
            Path(self.temp.name) / "VisPa" / "cache" / "fnt"))

    def test_sample_suffix_and_case_are_preserved(self):
        plan = resolve_fnt_plan(self.config, "252384ch2", "001.swc")
        self.assertEqual(plan["url"],
                         "http://10.10.48.110/www/upload/neuron/252384ch2/252384ch2/merge/252384ch2-001-merge.fnt")
        self.assertEqual(plan["catalog_url"],
                         "http://10.10.48.110/monkeydata/252384ch2/catalog")

    def test_download_binds_catalog_and_reuses_exact_cache(self):
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(self.body)) as opener:
            first = ensure_fnt(self.config, "250432", "001.swc")
        self.assertEqual(first["status"], "downloaded")
        opener.assert_called_once()
        source = Path(first["source_path"])
        bound = Path(first["project_path"])
        self.assertEqual(source.read_bytes(), self.body)
        self.assertEqual(bound.read_bytes().splitlines()[1], b"http://10.10.48.110/monkeydata/250432/catalog")
        self.assertEqual(source.read_bytes().splitlines()[2:], bound.read_bytes().splitlines()[2:])
        with patch("vispa.fnt.urllib.request.urlopen") as opener:
            second = ensure_fnt(self.config, "250432", "001.swc")
        self.assertEqual(second["status"], "cached")
        self.assertEqual(second["sha256"], first["sha256"])
        opener.assert_not_called()

    def test_matching_catalog_avoids_duplicate(self):
        current = self.body.replace(b"NONE", b"http://10.10.48.110/monkeydata/250432/catalog", 1)
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(current)):
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(result["project_path"], result["source_path"])
        self.assertFalse(Path(resolve_fnt_plan(self.config, "250432", "001")["bound_path"]).exists())

    def test_known_source_catalog_with_wrong_sample_is_not_rebound(self):
        wrong = self.body.replace(b"NONE", b"http://bap.cebsit.ac.cn/monkeydata/251637/catalog", 1)
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(wrong)):
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "failed")
        self.assertIn("different SampleID", result["errors"][0])
        plan = resolve_fnt_plan(self.config, "250432", "001")
        self.assertEqual(Path(plan["source_path"]).read_bytes(), wrong)
        self.assertFalse(Path(plan["bound_path"]).exists())
        self.assertFalse(Path(plan["receipt_path"]).exists())

    def test_bad_existing_cache_is_preserved_and_never_refetched(self):
        source = Path(resolve_fnt_plan(self.config, "250432", "001")["source_path"])
        source.parent.mkdir(parents=True)
        source.write_bytes(b"corrupt")
        with patch("vispa.fnt.urllib.request.urlopen") as opener:
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(source.read_bytes(), b"corrupt")
        opener.assert_not_called()

    def test_receipted_valid_source_mutation_fails_without_rewriting_any_file(self):
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(self.body)):
            first = ensure_fnt(self.config, "250432", "001")
        source = Path(first["source_path"])
        bound = Path(first["project_path"])
        receipt = Path(first["receipt_path"])
        source.write_bytes(source.read_bytes().replace(b"viewer.color.1=255", b"viewer.color.1=254"))
        before = (source.read_bytes(), bound.read_bytes(), receipt.read_bytes())
        with patch("vispa.fnt.urllib.request.urlopen") as opener:
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "failed")
        self.assertIn("SHA-256", result["errors"][0])
        self.assertEqual(before, (source.read_bytes(), bound.read_bytes(), receipt.read_bytes()))
        opener.assert_not_called()

    def test_receipted_bound_mutation_fails_without_rewriting_any_file(self):
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(self.body)):
            first = ensure_fnt(self.config, "250432", "001")
        source = Path(first["source_path"])
        bound = Path(first["project_path"])
        receipt = Path(first["receipt_path"])
        bound.write_bytes(bound.read_bytes().replace(b"viewer.color.1=255", b"viewer.color.1=254"))
        before = (source.read_bytes(), bound.read_bytes(), receipt.read_bytes())
        with patch("vispa.fnt.urllib.request.urlopen") as opener:
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "failed")
        self.assertIn("bound FNT SHA-256", result["errors"][0])
        self.assertEqual(before, (source.read_bytes(), bound.read_bytes(), receipt.read_bytes()))
        opener.assert_not_called()

    def test_unsupported_id_and_oversize_are_nonfatal(self):
        self.assertEqual(ensure_fnt(self.config, "250432", "L001.swc")["status"], "unsupported")
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(self.body)):
            self.config["visual_toolkit"]["fnt_tracer"]["max_response_bytes"] = 20
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(Path(resolve_fnt_plan(self.config, "250432", "001")["source_path"]).exists())

    def test_partial_http_response_is_not_cached(self):
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(self.body, declared_length=len(self.body) + 5)):
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(Path(resolve_fnt_plan(self.config, "250432", "001")["source_path"]).exists())

    def test_http_partial_content_is_rejected(self):
        with patch("vispa.fnt.urllib.request.urlopen", return_value=_Response(self.body, status=206)):
            result = ensure_fnt(self.config, "250432", "001")
        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
