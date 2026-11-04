"""Exact processed IONData source checks.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../CHANGELOG.md
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vispa.data_input_adaptor import (IONData, load_processed_neuron,
                                      processed_neuron_plan, set_iondata_provider_factory)


VALID = b"1 1 0 0 0 1 -1\n2 2 1 0 0 1 1\n"


class ProcessedSourceTest(unittest.TestCase):
    def test_cache_first_and_explicit_fetch(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "work") as folder:
            root = Path(folder)
            config = {"sources": {"http_host": "http://example.test"}}
            plan = processed_neuron_plan(config, "251637", "004.swc", cache_root=root)
            self.assertIsNone(plan["local_path"])
            with self.assertRaises(FileNotFoundError):
                load_processed_neuron(config, "251637", "004.swc", cache_root=root)
            with mock.patch("vispa.data_input_adaptor._read_bounded_swc", return_value=VALID) as read:
                self.assertEqual(load_processed_neuron(config, "251637", "004.swc",
                                                       cache_root=root, allow_download=True), VALID.decode())
                self.assertEqual(load_processed_neuron(config, "251637", "004.swc",
                                                       cache_root=root, allow_download=True), VALID.decode())
                self.assertEqual(read.call_count, 1)

    def test_invalid_fetch_does_not_cache(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "work") as folder:
            root = Path(folder)
            config = {"sources": {"http_host": "http://example.test"}}
            with mock.patch("vispa.data_input_adaptor._read_bounded_swc", return_value=b"invalid"):
                with self.assertRaises(ValueError):
                    load_processed_neuron(config, "251637", "004.swc",
                                          cache_root=root, allow_download=True)
            self.assertFalse((root / "251637" / "004.swc").exists())

    def test_refresh_preserves_changed_version(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "work") as folder:
            root = Path(folder)
            config = {"sources": {"http_host": "http://example.test"}}
            target = root / "251637" / "004.swc"
            changed = b"1 1 0 0 0 1 -1\n2 2 2 0 0 1 1\n"
            with mock.patch("vispa.data_input_adaptor._read_bounded_swc", side_effect=[VALID, VALID, changed]):
                for _ in range(3):
                    load_processed_neuron(config, "251637", "004.swc", cache_root=root,
                                          allow_download=True, refresh=True)
            import hashlib
            prior = next((root / "251637" / ".history" / "004.swc").glob("*.swc"))
            self.assertEqual(prior.read_text().replace("\r\n", "\n"), VALID.decode())
            self.assertEqual(target.read_text().replace("\r\n", "\n"), changed.decode())
            import json
            receipt = json.loads((root / "251637" / "004.swc.source.json").read_text())
            self.assertTrue(receipt["changed"])
            self.assertEqual(receipt["previous_sha256"], hashlib.sha256(prior.read_bytes()).hexdigest())

    def test_raw_refresh_then_managed_cached_only(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "work") as folder:
            root = Path(folder)
            config = {"defaults": {"cache_root": root},
                      "samples": {}, "sources": {"http_host": "http://example.test",
                                                   "raw_swc_base": "http://raw.test"}}
            with mock.patch("vispa.data_input_adaptor.load", return_value=config), mock.patch(
                    "vispa.data_input_adaptor.PortalSWCProvider._read",
                    side_effect=[b'[{"project_id":"p"}]', VALID]) as read:
                provider = IONData()
                self.assertEqual(provider.getRawNeuronTreeByID("251637", "004.swc", refresh=True).root.x, 0)
                self.assertEqual(provider.getRawNeuronTreeByID("251637", "004.swc", refresh=False).root.x, 0)
                self.assertEqual(read.call_count, 2)
            self.assertTrue((root / "swc_raw" / "251637" / "004.swc").is_file())

    def test_offline_missing_and_injected_provider(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "work") as folder:
            config = {"defaults": {"cache_root": Path(folder)}, "samples": {}, "sources": {}}
            class Remote:
                def getRawNeuronTreeByID(self, sample, neuron):
                    return (sample, neuron)
            set_iondata_provider_factory(lambda: Remote())
            try:
                with mock.patch("vispa.data_input_adaptor.load", return_value=config):
                    provider = IONData()
                    self.assertEqual(provider.getRawNeuronTreeByID("251637", "004.swc", refresh=True),
                                     ("251637", "004.swc"))
                    with self.assertRaises(FileNotFoundError):
                        provider.getRawNeuronTreeByID("251637", "004.swc", refresh=False)
            finally:
                set_iondata_provider_factory(None)

    def test_live_error_does_not_overwrite_cached_raw(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "work") as folder:
            root = Path(folder)
            config = {"defaults": {"cache_root": root}, "samples": {},
                      "sources": {"http_host": "http://example.test",
                                  "raw_swc_base": "http://raw.test"}}
            target = root / "swc_raw" / "251637" / "004.swc"
            target.parent.mkdir(parents=True)
            target.write_bytes(VALID)
            with mock.patch("vispa.data_input_adaptor.load", return_value=config), mock.patch(
                    "vispa.data_input_adaptor.PortalSWCProvider._read",
                    side_effect=ConnectionError("offline")):
                provider = IONData()
                with self.assertRaises(ConnectionError):
                    provider.getRawNeuronTreeByID("251637", "004.swc", refresh=True)
                self.assertEqual(provider.getRawNeuronTreeByID("251637", "004.swc", refresh=False).root.x, 0)
            self.assertEqual(target.read_bytes(), VALID)

    def test_shared_processed_root_cannot_be_managed_cache(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "work") as folder:
            root = Path(folder)
            config = {"sources": {"http_host": "http://example.test",
                                  "brain_view": {"processed_swc_root": str(root)}}}
            with self.assertRaises(ValueError):
                processed_neuron_plan(config, "251637", "004.swc", cache_root=root / "active")


if __name__ == "__main__":
    unittest.main()
