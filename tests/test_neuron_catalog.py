"""Exact-source catalog and stale GUI selection checks.

Version: 1.11.0.dev9 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if os.environ.get("VISPA_TEST_INSTALLED") != "1":
    sys.path.insert(0, str(SRC))

from vispa.dataset_config import load
from vispa.sources import (
    catalog_matches_sample, catalog_selection_id, catalog_snapshot_unchanged,
    list_neurons,
)


class NeuronCatalogTests(unittest.TestCase):
    def write_config(self, folder, rows, *, source_date="20261009"):
        folder = Path(folder)
        catalog = folder / "portal_snapshot.csv"
        with catalog.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("sample", "neuron_id", "portal_region", "registry_animal"))
            writer.writeheader()
            writer.writerows(rows)
        config_path = folder / "visual_toolkit.json"
        config_path.write_text(json.dumps({
            "version": 1,
            "sources": {"neuron_catalog": {
                "path": "portal_snapshot.csv",
                "source_date": source_date,
                "columns": {"sample": "sample", "neuron_id": "neuron_id",
                            "portal_region": "portal_region", "monkey": "registry_animal"},
            }},
        }), encoding="utf-8")
        return config_path, catalog

    def test_reads_all_exact_sample_rows_and_preserves_ids_and_blank_regions(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path, catalog = self.write_config(temp, [
                {"sample": "250442", "neuron_id": "001.swc", "portal_region": "M1_79", "registry_animal": "331"},
                {"sample": "250442L", "neuron_id": "001.swc", "portal_region": "wrong-suffix", "registry_animal": "804"},
                {"sample": "250442", "neuron_id": "003.swc", "portal_region": "", "registry_animal": "331"},
            ])
            result = list_neurons("250442", load(config_path))
            self.assertEqual(result["sha256"], hashlib.sha256(catalog.read_bytes()).hexdigest())
            self.assertTrue(catalog_snapshot_unchanged(result))
        self.assertEqual([row["neuron_id"] for row in result["rows"]], ["001.swc", "003.swc"])
        self.assertEqual([row["portal_region"] for row in result["rows"]], ["M1_79", ""])
        self.assertEqual(result["source_date"], "20261009")
        self.assertEqual(result["monkey_id"], "331")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["source_path"], str(catalog.resolve()))

    def test_config_resolves_catalog_brain_view_and_worker_paths_from_base(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config_path = folder / "config.json"
            config_path.write_text(json.dumps({
                "version": 1,
                "visual_toolkit": {"worker_python": "workers/python.exe"},
                "sources": {
                    "neuron_catalog": {"path": "catalog.csv", "source_date": "20261009",
                                       "columns": {"sample": "sample", "neuron_id": "neuron_id",
                                                   "portal_region": "portal_region"}},
                    "brain_view": {"mesh_path": "brain.obj", "processed_swc_root": "swc",
                                   "settings": {"opacity": 0.25}},
                },
            }), encoding="utf-8")
            config = load(config_path)
        self.assertEqual(config["sources"]["neuron_catalog"]["path"], (folder / "catalog.csv").resolve())
        self.assertEqual(config["sources"]["brain_view"]["mesh_path"], (folder / "brain.obj").resolve())
        self.assertEqual(config["sources"]["brain_view"]["processed_swc_root"], (folder / "swc").resolve())
        self.assertNotIn("coordinate_frame", config["sources"]["brain_view"])
        self.assertNotIn("coordinate_units", config["sources"]["brain_view"])
        self.assertEqual(config["sources"]["brain_view"]["settings"], {"opacity": 0.25})
        self.assertEqual(config["visual_toolkit"]["worker_python"], (folder / "workers/python.exe").resolve())

    def test_row_selection_returns_only_exact_id_for_current_sample_and_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path, _ = self.write_config(temp, [
                {"sample": "252527", "neuron_id": "001.swc", "portal_region": "M1_79", "registry_animal": "945"},
            ])
            snapshot = list_neurons("252527", load(config_path))
            row = snapshot["rows"][0]
            self.assertEqual(catalog_selection_id("252527", "252527", snapshot, row), "001.swc")
            self.assertIsNone(catalog_selection_id("252527", "252527L", snapshot, row))
            wrong_sample_row = dict(row, sample_id="252527L")
            self.assertIsNone(catalog_selection_id("252527", "252527", snapshot, wrong_sample_row))

    def test_snapshot_change_invalidates_loaded_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path, catalog = self.write_config(temp, [
                {"sample": "252527", "neuron_id": "048.swc", "portal_region": "Iai_41", "registry_animal": "945"},
            ])
            snapshot = list_neurons("252527", load(config_path))
            catalog.write_text(catalog.read_text(encoding="utf-8") + "252527,049.swc,,945\n", encoding="utf-8")
            self.assertFalse(catalog_snapshot_unchanged(snapshot))

    def test_duplicate_neuron_identity_fails_even_when_regions_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path, _ = self.write_config(temp, [
                {"sample": "252527", "neuron_id": "048.swc", "portal_region": "Iai_41", "registry_animal": "945"},
                {"sample": "252527", "neuron_id": "048.swc", "portal_region": "PrCO_49", "registry_animal": "945"},
            ])
            with self.assertRaisesRegex(ValueError, "duplicate neuron ID '048.swc'.*first seen"):
                list_neurons("252527", load(config_path))

    def test_catalog_rejects_pathlike_or_unsafe_neuron_ids_without_normalizing(self):
        for neuron_id in ("../x.swc", "a/b.swc", "a\\b.swc", "C:001.swc", "foo..swc"):
            with self.subTest(neuron_id=neuron_id), tempfile.TemporaryDirectory() as temp:
                config_path, _ = self.write_config(temp, [
                    {"sample": "252527", "neuron_id": neuron_id,
                     "portal_region": "M1_79", "registry_animal": "945"},
                ])
                with self.assertRaisesRegex(ValueError, "safe basename"):
                    list_neurons("252527", load(config_path))

    def test_sample_id_must_be_string_to_preserve_exact_identity(self):
        with self.assertRaisesRegex(TypeError, "exact string"):
            list_neurons(252527, {"sources": {}})

    def test_gui_selection_only_sets_neuron_id(self):
        from vispa.gui import NeuroVisGUI

        class Variable:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Table:
            def selection(self):
                return ("row-0",)

        with tempfile.TemporaryDirectory() as temp:
            config_path, _ = self.write_config(temp, [
                {"sample": "252527", "neuron_id": "001.swc", "portal_region": "M1_79",
                 "registry_animal": "945"},
            ])
            snapshot = list_neurons("252527", load(config_path))
        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        gui.sample_id = Variable("252527")
        gui.neuron_id = Variable("999.swc")
        gui._catalog_sample_id = "252527"
        gui._catalog_snapshot = snapshot
        gui._catalog_rows_by_iid = {"row-0": snapshot["rows"][0]}
        gui.neuron_catalog_table = Table()
        gui.load_and_autofill = mock.Mock()
        gui.run_selected = mock.Mock()
        with mock.patch("vispa.sources.catalog_snapshot_unchanged", return_value=True):
            gui._on_neuron_catalog_selected()
        self.assertEqual(gui.neuron_id.get(), "001.swc")
        gui.load_and_autofill.assert_not_called()
        gui.run_selected.assert_not_called()

    def test_gui_legacy_csv_profile_offers_explicit_live_source(self):
        from vispa.gui import NeuroVisGUI

        class Variable:
            def __init__(self, *args, value=""):
                self.value = value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            catalog_path = folder / "catalog.csv"
            catalog_path.write_text(
                "sample,neuron_id,portal_region,registry_animal\n"
                "250432,001.swc,Area X,747\n", encoding="utf-8")
            config_path = folder / "config.yaml"
            config_path.write_text(
                "version: 1\nsources:\n  neuron_catalog:\n"
                "    mode: csv\n    path: catalog.csv\n", encoding="utf-8")
            gui = NeuroVisGUI.__new__(NeuroVisGUI)
            gui.config_path = str(config_path)
            parent = object()
            with mock.patch("vispa.gui.tk.StringVar", side_effect=Variable), \
                 mock.patch("vispa.gui.ttk.Label") as label, \
                 mock.patch("vispa.gui.ttk.Combobox") as combobox:
                gui._configure_catalog_source_control(parent)

        self.assertEqual(gui._catalog_source, "csv")
        self.assertEqual(gui._catalog_source_choices, {
            "Live IONData": "live-iondata", "Dated CSV snapshot": "csv"})
        self.assertEqual(combobox.call_args.kwargs["values"],
                         ("Live IONData", "Dated CSV snapshot"))
        label.assert_called_once()

    def test_gui_discards_stale_sample_result_without_populating_dialog(self):
        from vispa.gui import NeuroVisGUI

        class Variable:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Window:
            def winfo_exists(self):
                return True

        class Table:
            def __init__(self):
                self.inserted = []

            def get_children(self):
                return ()

            def insert(self, *args, **kwargs):
                self.inserted.append((args, kwargs))

        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        gui.sample_id = Variable("252527L")
        gui.neuron_id = Variable("999.swc")
        gui._catalog_request_id = 5
        gui._neuron_catalog_window = Window()
        gui.neuron_catalog_table = Table()
        gui.neuron_catalog_load_button = mock.Mock()
        gui.neuron_catalog_info = Variable("")
        gui.update_status = mock.Mock()
        stale_result = {"sample_id": "252527", "rows": [{
            "sample_id": "252527", "neuron_id": "001.swc", "portal_region": "M1_79",
        }]}
        gui._apply_neuron_catalog(5, "252527", stale_result, None)
        self.assertEqual(gui.neuron_catalog_table.inserted, [])
        self.assertEqual(gui.neuron_id.get(), "999.swc")
        gui.update_status.assert_called_once()

    def test_gui_ignores_pending_result_after_dialog_close(self):
        from vispa.gui import NeuroVisGUI

        class Window:
            def __init__(self):
                self.destroyed = False

            def destroy(self):
                self.destroyed = True

        gui = NeuroVisGUI.__new__(NeuroVisGUI)
        window = Window()
        gui._neuron_catalog_window = window
        gui._catalog_request_id = 8
        gui.neuron_catalog_table = object()
        gui.neuron_catalog_load_button = object()
        gui._catalog_sample_id = "252527"
        gui._catalog_snapshot = {"source_path": "does-not-need-to-be-read"}
        gui._catalog_rows_by_iid = {}
        gui.sample_id = type("Variable", (), {"get": lambda self: "252527"})()
        gui._close_neuron_catalog()
        self.assertTrue(window.destroyed)
        self.assertEqual(gui._catalog_request_id, 9)
        self.assertIsNone(gui._neuron_catalog_window)
        self.assertIsNone(gui.neuron_catalog_table)
        # The widget may deliver a queued selection event after close; this must be safe.
        gui._on_neuron_catalog_selected()
        gui._apply_neuron_catalog(8, "252527", {"sample_id": "252527"}, None)

    def test_explicit_brain_view_declarations_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / "config.json"
            path.write_text(json.dumps({"version": 1, "sources": {"brain_view": {
                "mesh_path": "brain.obj", "processed_swc_root": "swc",
                "coordinate_frame": "RAS", "coordinate_units": "mm"}}}), encoding="utf-8")
            brain = load(path)["sources"]["brain_view"]
        self.assertEqual(brain["coordinate_frame"], "RAS")
        self.assertEqual(brain["coordinate_units"], "mm")

    def test_missing_source_and_missing_columns_are_actionable(self):
        with self.assertRaisesRegex(ValueError, "sources.neuron_catalog.path"):
            list_neurons("252527", {"sources": {}})
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            catalog = folder / "bad.csv"
            catalog.write_text("sample,neuron_id\n252527,001.swc\n", encoding="utf-8")
            config_path = folder / "config.json"
            config_path.write_text(json.dumps({"version": 1, "sources": {"neuron_catalog": {
                "path": "bad.csv", "columns": {"sample": "sample", "neuron_id": "neuron_id",
                "portal_region": "portal_region"}}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required column"):
                list_neurons("252527", load(config_path))

    def test_sample_guard_rejects_stale_results_but_keeps_exact_suffixes(self):
        self.assertTrue(catalog_matches_sample("250442L", "250442L"))
        self.assertFalse(catalog_matches_sample("250442", "250442L"))
        self.assertFalse(catalog_matches_sample("250442L", "250442"))


if __name__ == "__main__":
    unittest.main()
