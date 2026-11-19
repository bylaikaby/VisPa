"""Bounded FNT operator invariants.

Version: 0.1.0.dev9 (local/unreleased)
Last updated: 2026-10-30
Change history: ../CHANGELOG.md
"""
from tests.local_temp import local_temp
import unittest
from unittest.mock import patch
import json
from pathlib import Path

import numpy as np

from remap.morph_clustering.fnt_pipeline import analysis_matrix, hierarchy, preprocess_swc, run_pipeline, run_saved_analysis, sha256, validate_settings, _prepare_analysis_fnt


class FntPipelineTests(unittest.TestCase):
    def test_saved_cli_accepts_real_receipt_shape_offline(self):
        from remap.cli import run
        import contextlib, io
        with local_temp() as folder:
            root=Path(folder); joined=root/'joined.fnt'; distance=root/'distance.tsv'
            joined.write_text('0 Neuron s_a\n1 Neuron s_b\n2 Neuron s_c\n')
            distance.write_text('I\tJ\tScore\tMatch\tNoMatch\n0\t0\t0\t1\t0\n1\t1\t0\t1\t0\n2\t2\t0\t1\t0\n0\t1\t1\t1\t1\n0\t2\t2\t1\t1\n1\t2\t3\t1\t1\n')
            cases=[{'uid':f's|{n}.swc','sample_id':'s','neuron_id':f'{n}.swc','swc_path':str(root/'missing'/f'{n}.swc'),'swc_sha256':'a'*64} for n in 'abc']
            receipt=root/'receipt.json'; receipt.write_text(json.dumps({'plan':{'cases':cases,'binary_dir':str(root/'missing-bin')},'cases':cases,'distance':str(distance),'distance_sha256':sha256(distance),'joined_fnt':str(joined),'joined_sha256':sha256(joined)}))
            config=root/'config.json'; config.write_text(json.dumps({'workspace_root':str(root),'output_root':str(root/'work'/'analysis'),'clustering':{'enabled':True,'penalty_factor':0,'representation':'raw','linkage':'average','candidate_k':[2]}}))
            with contextlib.redirect_stdout(io.StringIO()):
                result=run(['fnt-analyze','--producer-receipt',str(receipt),'--config',str(config),'--max-cases','3','--dry-run'])
            self.assertEqual(result['candidate_hierarchy']['identity_order'],[c['uid'] for c in cases])
            self.assertFalse((root/'work').exists())

    def test_offline_settings_accept_missing_inputs_and_reject_bad_controls(self):
        case = {'sample_id':'s', 'neuron_id':'a.swc', 'swc_path':'missing.swc', 'swc_sha256':'a'*64}
        cfg = {'binary_dir':'missing-bin', 'output_root':'missing-output', 'cases':[case]}
        self.assertEqual(validate_settings(cfg, offline=True)['cases'][0]['uid'], 's|a.swc')
        for invalid in ({**cfg, 'cases':[{**case, 'swc_sha256':'bad'}]},
                        {**cfg, 'clustering':{'enabled':'false'}},
                        {**cfg, 'cases':[case, {**case, 'neuron_id':'A.swc'}]}):
            with self.assertRaises(ValueError):
                validate_settings(invalid, offline=True)

    def test_small_weighted_parser_and_failure_boundaries(self):
        from remap.morph_clustering.clustering_validation import read_fnt_distances
        with local_temp() as folder:
            root = Path(folder)
            joined, dist = root / "joined.fnt", root / "distance.tsv"
            joined.write_text("0 Neuron a\n1 Neuron b\n")
            header = "I\tJ\tScore\tMatch\tNoMatch\n"
            rows = "0\t0\t0\t1\t-1e-10\n1\t1\t0\t1\t0\n0\t1\t3\t1\t1\n"
            dist.write_text(header + rows)
            matrix, meta = read_fnt_distances(dist, joined)
            self.assertEqual(matrix.iloc[0, 1], 3)
            self.assertEqual(meta["minimum_no_match"], -1e-10)
            dist.write_text(header + rows.replace("-1e-10", "-1e-7"))
            with self.assertRaisesRegex(ValueError, "weights"):
                read_fnt_distances(dist, joined)
            dist.write_text(header + rows.replace("0\t1\t3", "0\t1\tnan"))
            with self.assertRaises(ValueError):
                read_fnt_distances(dist, joined)

    def test_explicit_undecimated_control_preserves_bytes_and_skips_binary(self):
        with local_temp() as folder:
            root = Path(folder)
            source, target = root / "converted.fnt", root / "analysis.undecimated.fnt"
            source.write_bytes(b"unchanged geometry fixture\n")
            with patch("remap.morph_clustering.fnt_pipeline._command", side_effect=AssertionError("decimator called")):
                _prepare_analysis_fnt(source, target, {"enabled": False}, "unused", root / "log", 60)
            self.assertEqual(target.read_bytes(), source.read_bytes())
            _prepare_analysis_fnt(source, target, {"enabled": False}, "unused", root / "log", 60)
            self.assertEqual(target.read_bytes(), source.read_bytes())
            target.unlink()
            with patch("remap.morph_clustering.fnt_pipeline._command") as command:
                _prepare_analysis_fnt(source, target, {"distance": 5000, "area": 5000}, "tool", root / "log", 60)
                self.assertEqual(command.call_args.args[0][1:5], ["-d", 5000, "-a", 5000])

    def test_transform_crossing_and_rigid_reflection(self):
        with local_temp() as folder:
            root = Path(folder)
            source = root / "source.swc"
            source.write_text("1 1 33000 0 0 1 -1\n2 2 31000 0 0 1 1\n")
            folded, whole, none = [root / f"{name}.swc" for name in ("folded", "whole", "none")]
            preprocess_swc(source, folded, "legacy_nodewise_fold", 32000)
            preprocess_swc(source, whole, "whole_neuron_reflect", 32000)
            preprocess_swc(source, none, "none", 32000)
            self.assertEqual([float(row.split()[2]) for row in folded.read_text().splitlines()], [31000, 31000])
            self.assertEqual([float(row.split()[2]) for row in whole.read_text().splitlines()], [31000, 33000])
            self.assertEqual([float(row.split()[2]) for row in none.read_text().splitlines()], [33000, 31000])

    def test_preprocess_rejects_late_malformed_graph_before_write(self):
        with local_temp() as folder:
            root = Path(folder)
            source, output = root / "bad.swc", root / "processed.swc"
            for content in (
                "1 1 33000 0 0 1 -1\n2 2 nan 0 0 1 1\n",
                "1 1 33000 0 0 1 -1\n2 2 31000 0 0 1 99\n",
                "1 1 33000 0 0 1 -1\n2 2 31000 0 0 1 1 extra\n",
            ):
                source.write_text(content)
                with self.assertRaises(ValueError):
                    preprocess_swc(source, output, "legacy_nodewise_fold", 32000)
                self.assertFalse(output.exists())

    def test_ward_presquared_julia_fixture(self):
        # Clustering.jl via the Gou monkeyrec Julia project, same D/order:
        # hclust(d, linkage=:ward_presquared).heights = [4, 28/3, 79/6].
        # Non-tied distances give the same merge topology, too.
        d = np.array([[0, 4, 8, 9], [4, 0, 8, 10], [8, 8, 0, 14], [9, 10, 14, 0]], float)
        z = hierarchy(d, "ward_presquared")
        np.testing.assert_allclose(z[:, 2], [4, 28 / 3, 79 / 6])
        self.assertEqual(z[:, :2].astype(int).tolist(), [[0, 1], [2, 4], [3, 5]])

    def test_settings_reject_collision_stale_source_and_dryrun_writes(self):
        with local_temp() as folder:
            root = Path(folder)
            source = root / "a.swc"
            source.write_text("1 1 1 2 3 1 -1\n")
            tools = root / "bin"
            tools.mkdir()
            for name in ("fnt-from-swc.exe", "fnt-decimate.exe", "fnt-join.exe", "fnt-dist.exe"):
                (tools / name).write_bytes(b"fixture")
            case = {"sample_id": "s1", "neuron_id": "n_1.swc", "swc_path": str(source), "swc_sha256": sha256(source)}
            cfg = {"output_root": str(root / "output"), "binary_dir": str(tools), "cases": [case]}
            with self.assertRaisesRegex(ValueError, "boolean"):
                validate_settings({**cfg, "decimation": {"enabled": "false"}})
            self.assertTrue(validate_settings(cfg)["decimation"]["enabled"])
            self.assertFalse(validate_settings(cfg, {"decimation_enabled": False})["decimation"]["enabled"])
            for bad in ({**cfg, "decimation": {"distnace": 5000}},
                        {**cfg, "preprocessing": {"midline": 32000}},
                        {**cfg, "clustering": {"represenation": "raw"}},
                        {**cfg, "cohort_tabel": {}}):
                with self.assertRaisesRegex(ValueError, "Unknown"):
                    validate_settings(bad)
                self.assertFalse(Path(cfg["output_root"]).exists())
            with self.assertRaisesRegex(ValueError, "at most 32"):
                validate_settings({**cfg, "cases": [case] * 33})
            with self.assertRaisesRegex(ValueError, "1..32"):
                run_pipeline({"output_root": str(root / "tampered"), "cases": [case] * 33})
            self.assertFalse((root / "tampered").exists())
            with self.assertRaisesRegex(ValueError, "Duplicate exact"):
                validate_settings({**cfg, "cases": [case, case]})
            with self.assertRaisesRegex(ValueError, "Invalid case"):
                validate_settings({**cfg, "cases": [{**case, "neuron_id": "../n.swc"}]})
            plan = validate_settings(cfg)
            self.assertFalse(Path(plan["output_root"]).exists())
            source.write_text("1 1 4 5 6 1 -1\n")
            with self.assertRaisesRegex(ValueError, "Source changed since dry-run"):
                run_pipeline(plan)
            self.assertFalse(Path(plan["output_root"]).exists())

    def test_penalty_and_incomplete_pair_parser(self):
        d = np.array([[0, 1, 2], [1, 0, 3], [2, 3, 0]], float)
        adjusted = analysis_matrix(d, "raw", 0.5, ["A", "A", "B"])
        np.testing.assert_allclose(adjusted, [[0, 1, 3.5], [1, 0, 4.5], [3.5, 4.5, 0]])
        from remap.morph_clustering.clustering_validation import read_fnt_distances
        with local_temp() as folder:
            root = Path(folder)
            joined = root / "joined.fnt"
            joined.write_text("0 Neuron a\n1 Neuron b\n2 Neuron c\n")
            dist = root / "distance.tsv"
            dist.write_text("I\tJ\tScore\n0\t0\t0\n1\t1\t0\n2\t2\t0\n0\t1\t1\n0\t2\t2\n")
            with self.assertRaisesRegex(ValueError, "Missing FNT pairs"):
                read_fnt_distances(dist, joined)

    def test_saved_analysis_hash_identity_and_no_producer(self):
        with local_temp() as folder:
            root = Path(folder)
            joined = root / "joined.fnt"
            joined.write_text("0 Neuron s_a\n1 Neuron s_b\n2 Neuron s_c\n")
            distance = root / "distance.tsv"
            distance.write_text("I\tJ\tScore\tMatch\tNoMatch\n0\t0\t0\t1\t0\n1\t1\t0\t1\t0\n2\t2\t0\t1\t0\n0\t1\t1\t1\t1\n0\t2\t2\t1\t1\n1\t2\t3\t1\t1\n")
            ids = ["s|a.swc", "s|b.swc", "s|c.swc"]
            receipt = root / "producer.json"
            receipt.write_text(json.dumps({"distance": str(distance), "distance_sha256": sha256(distance),
                                           "joined_fnt": str(joined), "joined_sha256": sha256(joined),
                                           "cases": [{"uid": uid} for uid in ids]}))
            plan = {"output_root": str(root / "analysis"), "cases": [{"uid": uid} for uid in ids],
                    "clustering": {"enabled": True, "score_mode": "raw", "representation": "raw",
                                   "linkage": "average", "penalty_factor": 0.0, "penalty_absolute": 0.0,
                                   "candidate_k": [2], "type_by_uid": {}}}
            with patch("subprocess.run", side_effect=AssertionError("producer called")):
                dry = run_saved_analysis(receipt, plan, dry_run=True)
                self.assertIsNone(dry["candidate_hierarchy"]["final_k"])
                self.assertFalse((root / "analysis").exists())
                result = run_saved_analysis(receipt, plan)
            self.assertIsNone(result["final_k"])
            with self.assertRaisesRegex(ValueError, "identities/order differ"):
                run_saved_analysis(receipt, {**plan, "cases": list(reversed(plan["cases"]))}, dry_run=True)
            distance.write_text(distance.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                run_saved_analysis(receipt, plan, dry_run=True)

    def test_server_fnt_bin_precedes_local(self):
        from remap.morph_clustering import fnt_pipeline as fnt
        with local_temp() as folder:
            root = Path(folder)
            server, local = root / "server", root / "local"
            for directory, marker in ((server, b"server"), (local, b"local")):
                directory.mkdir()
                for name in fnt.FNT_TOOLS:
                    (directory / name).write_bytes(marker)
            with patch.object(fnt, "SERVER_FNT_BIN", server), patch.object(fnt, "LOCAL_FNT_BIN", local):
                chosen, source = fnt.resolve_fnt_binaries(str(local))
                self.assertEqual(source, "server")
                self.assertEqual(chosen, server)
                (server / fnt.FNT_TOOLS[0]).unlink()
                chosen, source = fnt.resolve_fnt_binaries(None)
                self.assertEqual(source, "local")
                self.assertEqual(chosen, local)

    def test_failed_run_removes_only_an_unreceipted_directory(self):
        from remap.morph_clustering.fnt_pipeline import _discard_unreceipted
        with local_temp() as folder:
            root = Path(folder)
            done = root / "done"
            done.mkdir()
            (done / "receipt.json").write_text("{}")
            partial = root / "partial"
            partial.mkdir()
            (partial / "commands.log").write_text("stopped")
            _discard_unreceipted(done)
            _discard_unreceipted(partial)
            self.assertTrue((done / "receipt.json").is_file())
            self.assertFalse(partial.exists())
            source = root / "a.swc"
            source.write_text("1 1 1 2 3 1 -1\n")
            tools = root / "bin"
            tools.mkdir()
            for name in ("fnt-from-swc.exe", "fnt-decimate.exe", "fnt-join.exe", "fnt-dist.exe"):
                (tools / name).write_bytes(b"fixture")
            case = {"sample_id": "s1", "neuron_id": "n_1.swc", "swc_path": str(source), "swc_sha256": sha256(source)}
            plan = validate_settings({"output_root": str(root / "output"), "binary_dir": str(tools), "cases": [case]})
            with self.assertRaises(FileExistsError):
                run_pipeline({**plan, "output_root": str(done)})
            self.assertTrue((done / "receipt.json").is_file())
            with self.assertRaises(Exception) as caught:
                run_pipeline(plan)
            self.assertNotIsInstance(caught.exception, FileExistsError)
            self.assertFalse(Path(plan["output_root"]).exists())
            self.assertTrue(source.is_file())

if __name__ == "__main__":
    unittest.main()
