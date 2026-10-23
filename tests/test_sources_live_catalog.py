"""Bounded live IONData catalog and dated-snapshot selection contracts.

Version: 1.11.0.dev6 (local/unreleased)
Last updated: 2026-10-23
Change history: ../CHANGELOG.md
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("VISUAL_TOOLKIT_TEST_INSTALLED") != "1":
    sys.path.insert(0, str(ROOT / "src"))

from vispa.cli import main
from vispa.dataset_config import load
from vispa.sources import (
    catalog_selection_id,
    catalog_snapshot_unchanged,
    list_neurons,
)


class _Response:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status
        self.read_limit = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def getcode(self):
        return self.status

    def read(self, limit):
        self.read_limit = limit
        return self.body[:limit]


class LiveNeuronCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vispa-live-catalog-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_config(self, catalog, *, extra_sources=None):
        sources = {"neuron_catalog": catalog}
        sources.update(extra_sources or {})
        path = self.root / "config.json"
        path.write_text(json.dumps({"version": 1, "sources": sources}), encoding="utf-8")
        return load(path)

    def response_rows(self):
        return json.dumps([
            {"name": "001.swc", "sampleid": "250432L", "region": "M1_79",
             "type": "neuron", "exclude": "0", "comment": "preserve"},
            {"name": "002.swc", "sampleid": "250432L", "region": "",
             "type": "neuron", "exclude": "0", "comment": ""},
        ], separators=(",", ":")).encode("utf-8")

    def live_config(self, **overrides):
        catalog = {"mode": "live-iondata", "host": "http://catalog.example:8080",
                   "timeout_seconds": 7, "max_response_bytes": 4096}
        catalog.update(overrides)
        return self.write_config(catalog)

    def test_live_listing_uses_exact_sample_and_returns_bounded_provenance(self):
        config = self.live_config()
        response = _Response(self.response_rows())
        with mock.patch("vispa.sources.urllib.request.urlopen", return_value=response) as urlopen:
            result = list_neurons("250432L", config)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url,
                         "http://catalog.example:8080/neuronbrowser/api/user/selectNeurons?id=250432L")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7.0)
        self.assertEqual(response.read_limit, 4097)
        self.assertEqual(result["source_kind"], "live-iondata")
        self.assertEqual(result["request_url"], request.full_url)
        self.assertEqual(result["source_path"], request.full_url)
        self.assertEqual(result["source_size"], len(self.response_rows()))
        self.assertRegex(result["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(result["fetched_at"].endswith("Z"))
        self.assertTrue(catalog_snapshot_unchanged(result))
        self.assertEqual([row["neuron_id"] for row in result["rows"]], ["001.swc", "002.swc"])
        self.assertEqual(result["rows"][0]["sample_id"], "250432L")
        self.assertEqual(result["rows"][0]["portal_region"], "M1_79")
        self.assertEqual(result["rows"][0]["comment"], "preserve")
        self.assertEqual(catalog_selection_id("250432L", "250432L", result, result["rows"][0]), "001.swc")
        self.assertIsNone(catalog_selection_id("250432L", "250432", result, result["rows"][0]))

    def test_live_api_rows_reject_mismatched_sample_duplicates_and_paths(self):
        config = self.live_config()
        bad_rows = [
            [{"name": "001.swc", "sampleid": "250432", "region": ""}],
            [{"name": "001.swc", "sampleid": "250432L", "region": ""},
             {"name": "001.swc", "sampleid": "250432L", "region": ""}],
            [{"name": "..\\001.swc", "sampleid": "250432L", "region": ""}],
        ]
        for rows in bad_rows:
            with self.subTest(rows=rows), mock.patch(
                    "vispa.sources.urllib.request.urlopen",
                    return_value=_Response(json.dumps(rows).encode("utf-8"))):
                with self.assertRaises(ValueError):
                    list_neurons("250432L", config)

    def test_live_response_limit_and_json_shape_fail_clearly(self):
        config = self.live_config(max_response_bytes=1024)
        with mock.patch("vispa.sources.urllib.request.urlopen",
                        return_value=_Response(b" " * 1025)):
            with self.assertRaisesRegex(ValueError, "1024-byte response limit"):
                list_neurons("250432L", config)
        with mock.patch("vispa.sources.urllib.request.urlopen",
                        return_value=_Response(b"{}")):
            with self.assertRaisesRegex(ValueError, "JSON array"):
                list_neurons("250432L", config)

    def test_network_error_does_not_fall_back_to_configured_snapshot(self):
        snapshot = self.root / "snapshot.csv"
        snapshot.write_text("sample,neuron_id,portal_region\n250432L,001.swc,M1\n", encoding="utf-8")
        config = self.live_config(snapshot_path=str(snapshot))
        with mock.patch("vispa.sources.urllib.request.urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(OSError, "offline"):
                list_neurons("250432L", config)
        selected = list_neurons("250432L", config, source="csv")
        self.assertEqual(selected["source_kind"], "csv")
        self.assertEqual(selected["rows"][0]["neuron_id"], "001.swc")

    def test_legacy_csv_profile_keeps_default_offline_and_allows_live_opt_in(self):
        snapshot = self.root / "snapshot.csv"
        snapshot.write_text("sample,neuron_id,portal_region\n250432L,001.swc,M1\n", encoding="utf-8")
        config = self.write_config({"path": str(snapshot)})
        with mock.patch("vispa.sources.urllib.request.urlopen") as urlopen:
            default_result = list_neurons("250432L", config)
        urlopen.assert_not_called()
        self.assertEqual(default_result["source_kind"], "csv")
        config["sources"]["neuron_catalog"]["host"] = "http://10.10.48.110"
        response = _Response(self.response_rows())
        with mock.patch("vispa.sources.urllib.request.urlopen", return_value=response) as urlopen:
            opted_in = list_neurons("250432L", config, source="live-iondata")
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.args[0].full_url,
                         "http://10.10.48.110/neuronbrowser/api/user/selectNeurons?id=250432L")
        self.assertEqual(opted_in["source_kind"], "live-iondata")

    def test_config_validation_bounds_live_timeout_and_response_size(self):
        for updates, expected in [
            ({"timeout_seconds": 0.5}, "timeout_seconds"),
            ({"timeout_seconds": 61}, "timeout_seconds"),
            ({"max_response_bytes": 999}, "max_response_bytes"),
            ({"host": "http://catalog.example/api"}, r"HTTP\(S\) origin"),
        ]:
            catalog = {"mode": "live-iondata", "host": "http://catalog.example"}
            catalog.update(updates)
            path = self.root / "bad.json"
            path.write_text(json.dumps({"version": 1, "sources": {"neuron_catalog": catalog}}),
                            encoding="utf-8")
            with self.subTest(updates=updates), self.assertRaisesRegex(ValueError, expected):
                load(path)

    def test_raw_swc_cache_defaults_to_local_persistent_path_without_creating_it(self):
        local_appdata = self.root / "user-data"
        config_path = self.root / "shared" / "profile.json"
        config_path.parent.mkdir()
        config_path.write_text(json.dumps({"version": 1, "sources": {
            "http_host": "http://catalog.example",
            "raw_swc_base": "http://raw.example/swc/newswc"}}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}):
            config = load(config_path)
        expected = local_appdata / "VisPa" / "cache" / "swc_raw"
        self.assertEqual(config["sources"]["legacy_raw_swc_root"], expected)
        self.assertFalse(expected.exists())

        config_path.write_text(json.dumps({"version": 1, "sources": {
            "http_host": "http://catalog.example",
            "raw_swc_base": "http://raw.example/swc/newswc",
            "legacy_raw_swc_root": "explicit/raw-cache"}}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}):
            explicit = load(config_path)
        self.assertEqual(explicit["sources"]["legacy_raw_swc_root"],
                         (config_path.parent / "explicit/raw-cache").resolve())

    def test_config_check_catalog_dry_run_does_not_request_network(self):
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps({"version": 1, "sources": {"neuron_catalog": {
            "mode": "live-iondata", "host": "http://catalog.example"}}}), encoding="utf-8")
        output = io.StringIO()
        with mock.patch("vispa.sources.urllib.request.urlopen") as urlopen, contextlib.redirect_stdout(output):
            status = main(["config-check", "--catalog", "--sample", "250432L",
                           "--config", str(config_path), "--dry-run"])
        self.assertEqual(status, 0)
        urlopen.assert_not_called()
        plan = json.loads(output.getvalue())
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["request_url"],
                         "http://catalog.example/neuronbrowser/api/user/selectNeurons?id=250432L")
        self.assertEqual(plan["source_kind"], "live-iondata")

    def test_config_check_catalog_fetches_only_the_requested_sample(self):
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps({"version": 1, "sources": {"neuron_catalog": {
            "mode": "live-iondata", "host": "http://catalog.example"}}}), encoding="utf-8")
        output = io.StringIO()
        response = _Response(self.response_rows())
        with mock.patch("vispa.sources.urllib.request.urlopen", return_value=response) as urlopen, \
                contextlib.redirect_stdout(output):
            status = main(["config-check", "--catalog", "--sample", "250432L",
                           "--config", str(config_path)])
        self.assertEqual(status, 0)
        self.assertEqual(urlopen.call_count, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["result"]["count"], 2)
        self.assertEqual(payload["result"]["source_kind"], "live-iondata")
        self.assertEqual(payload["result"]["sample_id"], "250432L")


if __name__ == "__main__":
    unittest.main()
