"""Type-2 leaf table for terminal Context QC.

Version: 1.11.0.dev19 (local/unreleased)
Last updated: 2026-10-26
Change history: ../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from vispa.sources import read_swc
from vispa.terminal_qc import (
    charm_names, list_terminal_rows, load_atlas, pair_processed, region_line, select_rows,
    table_from_swc, terminal_table)


SWC = """\
1 1 10 10 10 2.0 -1
2 2 20 10 10 1.0 1
3 2 30 10 10 0.5 2
4 3 10 20 10 0.5 1
5 2 10 30 10 0.5 1
"""


class TerminalTableTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "neuron.swc"
        self.path.write_text(SWC, encoding="ascii")
        self.tree = read_swc(self.path)

    def test_only_childless_nonroot_type2_nodes_are_rows(self):
        rows = list_terminal_rows(self.tree)
        self.assertEqual([row.node_id for row in rows], [3, 5])
        self.assertTrue(all(row.node_type == 2 and row.parent_id != -1 for row in rows))

    def test_render_selection_comes_from_the_table(self):
        rows = list_terminal_rows(self.tree)
        self.assertEqual([row.node_id for row in select_rows(rows, [5])], [5])
        random_rows = select_rows(rows, n=1, seed=1)
        self.assertEqual(len(random_rows), 1)
        self.assertIn(random_rows[0].node_id, {3, 5})
        with self.assertRaises(ValueError):
            select_rows(rows, [2])

    def test_table_counts_candidates_separately_from_all_leaves(self):
        table = table_from_swc(self.path)
        self.assertEqual(table["all_leaves"], 3)
        self.assertEqual(table["candidate_axon_endpoints"], 2)
        self.assertEqual(len(table["rows"]), 2)

    def test_charm_names_read_level_3_and_level_6(self):
        import numpy as np
        image = np.zeros((4, 4, 4, 1, 6), dtype=np.int16)
        image[1, 2, 3, 0, 2] = 17
        image[1, 2, 3, 0, 5] = 42
        atlas = self.path.with_suffix(".npy")
        key = self.path.with_suffix(".txt")
        np.save(atlas, image)
        key.write_text(
            "Index\tAbbreviation\tFull_Name\tFirst_Level\tLast_Level\n"
            "17\tCL_parent\tCL_parent_name\t3\t3\n"
            "42\tCL_Ial\tCL_lateral_agranular_insula_area\t6\t6\n",
            encoding="utf-8")
        lookup = charm_names((250.0, 500.0, 750.0), atlas, key)
        self.assertEqual(lookup["voxel"], [1, 2, 3])
        self.assertEqual(lookup["names"][3]["abbreviation"], "CL_parent")
        self.assertEqual(lookup["names"][6]["abbreviation"], "CL_Ial")
        self.assertEqual(region_line(lookup), "L3 CL_parent | L6 CL_Ial")
        outside = charm_names((5000.0, 0.0, 0.0), atlas, key)
        self.assertEqual(outside["names"][3]["abbreviation"], "Out_of_Bounds")

    def test_rounding_matches_region_analysis_half_to_even(self):
        import numpy as np
        image = np.zeros((4, 4, 4, 1, 6), dtype=np.int16)
        image[2, 0, 0, 0, 5] = 42
        atlas = self.path.with_suffix(".npy")
        key = self.path.with_suffix(".txt")
        np.save(atlas, image)
        key.write_text("Index\tAbbreviation\tFull_Name\n42\tCL_Ial\tCL_Ial\n", encoding="utf-8")
        lookup = charm_names((625.0, 0.0, 0.0), atlas, key)
        self.assertEqual(lookup["voxel"], [2, 0, 0])
        self.assertEqual(lookup["names"][6]["abbreviation"], "CL_Ial")

    def test_regions_come_from_processed_frame_by_node_id(self):
        import numpy as np
        processed = self.path.with_name("processed.swc")
        processed.write_text(
            "1 1 250 250 250 2.0 -1\n"
            "2 2 500 250 250 1.0 1\n"
            "3 2 500 500 250 0.5 2\n"
            "4 3 250 500 250 0.5 1\n"
            "5 2 250 750 250 0.5 1\n",
            encoding="ascii")
        image = np.zeros((4, 4, 4, 1, 6), dtype=np.int16)
        image[2, 2, 1, 0, 5] = 42
        atlas_path = self.path.with_suffix(".npy")
        key = self.path.with_suffix(".txt")
        np.save(atlas_path, image)
        key.write_text("Index\tAbbreviation\tFull_Name\n42\tCL_Ial\tCL_Ial\n", encoding="utf-8")
        table = terminal_table(self.path, processed, load_atlas(atlas_path, key), levels=(6,))
        rows = {row["node_id"]: row for row in table["rows"]}
        self.assertEqual(rows[3]["raw_xyz_um"], [30.0, 10.0, 10.0])
        self.assertEqual(rows[3]["processed_xyz_um"], [500.0, 500.0, 250.0])
        self.assertEqual(rows[3]["region"]["names"][6]["abbreviation"], "CL_Ial")
        self.assertEqual(rows[5]["region"]["names"][6]["abbreviation"], "background")

    def test_processed_graph_must_match_raw_graph(self):
        processed = self.path.with_name("processed.swc")
        processed.write_text(
            "1 1 250 250 250 2.0 -1\n"
            "2 2 500 250 250 1.0 1\n"
            "3 2 500 500 250 0.5 1\n"
            "4 3 250 500 250 0.5 1\n"
            "5 2 250 750 250 0.5 1\n",
            encoding="ascii")
        with self.assertRaisesRegex(ValueError, "node 3"):
            pair_processed(self.tree, read_swc(processed))

    def test_terminal_branch_walks_to_the_branch_point(self):
        from vispa.terminal_qc import SwcGraph, terminal_branch
        branch = terminal_branch(SwcGraph(self.tree), 3)
        self.assertEqual(branch.node_ids, (3, 2, 1))
        self.assertEqual(branch.branch_start_id, 1)
        self.assertAlmostEqual(branch.length_um, 20.0)
        self.assertEqual(branch.branch_order, 1)
        self.assertEqual(branch.compartment_transitions, 1)
        self.assertEqual(table_from_swc(self.path)["rows"][0]["branch"]["leaf_id"], 3)

    def test_invalid_geometry_parameters_are_rejected(self):
        from vispa.terminal_qc import SwcGraph, terminal_branch, atlas_names, HierarchyAtlas
        import numpy as np
        graph = SwcGraph(self.tree)
        for bad in (0.0, -1.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                terminal_branch(graph, 3, bad)
        atlas = HierarchyAtlas(np.zeros((2, 2, 2), dtype=int), {}, "fixture", "fixture")
        for bad in (0.0, -1.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                atlas_names((0, 0, 0), atlas, scale_um=bad)
        with self.assertRaises(ValueError):
            atlas_names((float("nan"), 0, 0), atlas)

    def test_file_byte_provenance_and_memory_unknown(self):
        import hashlib
        from vispa.terminal_qc import terminal_table
        table = terminal_table(self.path)
        record = table["input_provenance"]["raw_swc"]
        self.assertEqual(record["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(record["provenance_status"], "source_hash_recorded")
        memory = terminal_table(self.tree)
        self.assertIsNone(memory["input_provenance"]["raw_swc"]["source_sha256"])
        self.assertEqual(memory["input_provenance"]["raw_swc"]["provenance_status"],
                         "source_identity_unknown")

    def test_loaded_atlas_provenance_is_reused_across_tables(self):
        import numpy as np
        from unittest import mock
        from vispa import terminal_qc
        atlas_path = self.path.with_suffix(".npy")
        key_path = self.path.with_suffix(".txt")
        np.save(atlas_path, np.zeros((2, 2, 2, 1, 6), dtype=np.int16))
        key_path.write_text("Index\tAbbreviation\tFull_Name\n", encoding="utf-8")
        atlas = load_atlas(atlas_path, key_path)
        with mock.patch.object(terminal_qc, "_input_record", wraps=terminal_qc._input_record) as record:
            first = terminal_qc.terminal_table(self.tree, atlas=atlas)
            second = terminal_qc.terminal_table(self.tree, atlas=atlas)
        self.assertEqual(record.call_count, 4)  # raw and absent processed, twice
        self.assertEqual(first["input_provenance"]["atlas"]["sha256"],
                         second["input_provenance"]["atlas"]["sha256"])
