"""Bounded processed SWC source contracts.

Version: 0.1.0.dev14 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
"""
from tests.local_temp import local_temp
import unittest
from pathlib import Path
from unittest import mock

from remap.region_analysis.neuron_swc import NeuronTracer
from remap.population_operator import INPUT_NAMES, plan_population


SWC = "1 1 0 0 0 1 -1\n2 2 250 0 0 1 1\n"


class ProcessedLoadingTest(unittest.TestCase):
    def test_local_path_with_spaces_without_vispa(self):
        with local_temp() as folder:
            path = Path(folder) / "folder with spaces"
            path.mkdir()
            swc = path / "004.swc"
            swc.write_text(SWC, encoding="utf-8")
            tracer = NeuronTracer()
            with mock.patch.dict("sys.modules", {"vispa": None}):
                tracer.process("251637", "004.swc", swc=str(swc))
            self.assertEqual(tracer.nodes[2].x_nii, 1.0)

    def test_text_and_explicit_source_without_vispa(self):
        tracer = NeuronTracer()
        tracer.process("251637", "004.swc", swc="1 1 0 0 0 1 -1")
        self.assertEqual(len(tracer.nodes), 1)
        with self.assertRaises(FileNotFoundError):
            tracer.process("251637", "004.swc")
        tracer.process("251637", "004.swc", swc=SWC)
        self.assertEqual(len(tracer.nodes), 2)

    def test_invalid_source_does_not_change_existing_graph(self):
        tracer = NeuronTracer()
        tracer.process("251637", "004.swc", swc=SWC)
        old_root, old_nodes = tracer.root, tracer.nodes
        with self.assertRaises(ValueError):
            tracer.process("251637", "004.swc", swc="1 1 0 0 0 1 -1\n2 2 bad 0 0 1 1")
        self.assertIs(tracer.root, old_root)
        self.assertIs(tracer.nodes, old_nodes)

    def test_portal_plan_exact_missing_id_no_network_or_output(self):
        with local_temp() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            inputs = root / "inputs"
            inputs.mkdir()
            fixture = inputs / "fixture.txt"
            fixture.write_text("fixture", encoding="utf-8")
            config = {"sample_id": "251637", "neuron_ids": ["004.swc"],
                      "swc_source_dir": str(source), "iondata_host": "http://example.test",
                      "output_base": str(root / "output")}
            config.update({name: str(fixture) for name in INPUT_NAMES})
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network attempted")):
                plan = plan_population(config)
            self.assertTrue(plan["swcs"]["004.swc"]["fetch_required"])
            self.assertEqual(plan["iondata_host"], "http://example.test")
            self.assertFalse(plan["refresh_swc"])
            self.assertFalse((root / "output").exists())
            present = source / "004.swc"
            present.write_text(SWC, encoding="utf-8")
            config["neuron_ids"] = ["004.swc"]
            config["refresh_swc"] = True
            plan = plan_population(config)
            self.assertTrue(plan["refresh_swc"])
            self.assertTrue(plan["swcs"]["004.swc"]["fetch_required"])
            self.assertIsNotNone(plan["swcs"]["004.swc"]["sha256"])


if __name__ == "__main__":
    unittest.main()
