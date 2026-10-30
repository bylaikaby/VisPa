"""Exact native FNT route, cache, and catalog-binding checks.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
"""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vispa.fnt import (ensure_fnt, prepare_manual_project, resolve_fnt_plan,
                       resolve_native_fnt_plan, prepare_native_fnt, validate_native_fnt,
                       launch_native_fnt, swc_fnt_tracer)
from vispa.cli import legacy_fnt_plan as fnt_plan
from vispa.cli import fnt_plan as native_cli_fnt_plan


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

    def test_manual_project_precedence_and_verified_catalog_copy(self):
        root = Path(self.temp.name) / "projects"
        root.mkdir()
        exe = root / "fnt-tracer.exe"
        exe.write_bytes(b"fixture")
        manual = root / "250432_001.fnt"
        manual.write_bytes(self.body)
        (root / "250432_001.decimate.fnt").write_bytes(self.body)
        self.config["visual_toolkit"]["fnt_tracer"].update(executable=str(exe), project_root=str(root))
        before = {p.name for p in root.iterdir()}
        plan = fnt_plan(self.config, "250432", "001.swc")
        self.assertEqual(plan["project"], str(manual))
        self.assertEqual(before, {p.name for p in root.iterdir()})
        with patch("vispa.fnt.urllib.request.urlopen", side_effect=AssertionError("no HTTP")):
            prepared = prepare_manual_project(self.config, plan)
        bound = Path(prepared["project"])
        self.assertEqual(bound.name, manual.name)
        self.assertNotEqual(bound, manual)
        self.assertEqual(manual.read_bytes(), self.body)
        self.assertEqual(bound.read_bytes().splitlines()[1], b"http://10.10.48.110/monkeydata/250432/catalog")
        self.assertEqual(bound.read_bytes().splitlines()[2:], self.body.splitlines()[2:])
        self.assertEqual(prepared["command"], [str(exe), str(bound)])
        self.assertTrue(bound.with_suffix(".json").is_file())
        self.assertEqual(prepare_manual_project(self.config, plan)["project"], str(bound))

    def test_correct_manual_catalog_stays_direct_and_invalid_source_blocks(self):
        root = Path(self.temp.name) / "projects"
        root.mkdir()
        exe = root / "fnt-tracer.exe"
        exe.write_bytes(b"fixture")
        manual = root / "250432_001.fnt"
        correct = self.body.replace(b"NONE", b"http://10.10.48.110/monkeydata/250432/catalog", 1)
        manual.write_bytes(correct)
        self.config["visual_toolkit"]["fnt_tracer"].update(executable=str(exe), project_root=str(root))
        plan = fnt_plan(self.config, "250432", "001.swc")
        self.assertEqual(prepare_manual_project(self.config, plan), plan)
        self.assertEqual({p.name for p in root.iterdir()}, {exe.name, manual.name})
        manual.write_bytes(b"malformed")
        with self.assertRaisesRegex(ValueError, "FNT header is invalid"):
            prepare_manual_project(self.config, plan)
        self.assertEqual(manual.read_bytes(), b"malformed")

    def test_wrong_sample_manual_catalog_fails_without_copy(self):
        root = Path(self.temp.name) / "projects"
        root.mkdir()
        exe = root / "fnt-tracer.exe"
        exe.write_bytes(b"fixture")
        manual = root / "250432_001.fnt"
        wrong = self.body.replace(b"NONE", b"http://10.10.48.110/monkeydata/251637/catalog", 1)
        manual.write_bytes(wrong)
        self.config["visual_toolkit"]["fnt_tracer"].update(executable=str(exe), project_root=str(root))
        plan = fnt_plan(self.config, "250432", "001.swc")
        with self.assertRaisesRegex(ValueError, "different SampleID"):
            prepare_manual_project(self.config, plan)
        self.assertEqual(manual.read_bytes(), wrong)
        self.assertFalse((Path(resolve_fnt_plan(self.config, "250432", "001")["bound_path"]).parent / "manual").exists())

    def test_exact_route_and_dry_run_have_no_side_effects(self):
        plan = resolve_fnt_plan(self.config, "250432", "001.swc")
        self.assertEqual(Path(plan["bound_path"]).name, "250432-001-merge.fnt")
        self.assertEqual(Path(plan["bound_path"]).parent.name, "viewer")
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

    def _borrowed_config(self):
        root = Path(self.temp.name)
        bin_dir = root / "bin"
        bin_dir.mkdir(exist_ok=True)
        converter = bin_dir / "fnt-from-swc.exe"
        tracer = bin_dir / "fnt-tracer.exe"
        converter.write_bytes(b"converter")
        tracer.write_bytes(b"tracer")
        self.config["sources"] = {"http_host": "http://test.example",
                                  "raw_swc_base": "http://test.example/raw",
                                  "legacy_raw_swc_root": str(root / "scientific-raw")}
        self.config["visual_toolkit"]["fnt_tracer"].update(
            executable=str(tracer), converter_executable=str(converter))
        original = root / "scientific-raw" / "251637" / "004.swc"
        original.parent.mkdir(parents=True)
        original.write_text("1 1 999 999 999 1 -1\n", encoding="ascii")
        return original, converter, tracer

    def test_borrowed_dry_run_has_no_files_or_network(self):
        original, _converter, _tracer = self._borrowed_config()
        before = original.read_bytes()
        with patch("vispa.data_input_adaptor.PortalSWCProvider.getRawNeuronTreeByID") as fetch:
            result = swc_fnt_tracer(self.config, "251637", "004.swc", dry_run=True)
        fetch.assert_not_called()
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["raw_path"], None)
        self.assertIn("{project_id}", result["raw_url_template"])
        self.assertEqual(original.read_bytes(), before)
        self.assertFalse((Path(self.temp.name) / "native").exists())

    def test_borrowed_fresh_portal_raw_converter_catalog_and_process(self):
        original, converter, tracer = self._borrowed_config()
        before = original.read_bytes()
        from vispa.data_input_adaptor import read_swc

        def fresh_fetch(provider, _sample, _neuron):
            raw = provider.cache_root / "251637" / "004.swc"
            raw.parent.mkdir(parents=True)
            raw.write_text("1 1 10 20 30 1 -1\n", encoding="ascii")
            return read_swc(raw)

        converter_calls = []
        def convert(command, **_kwargs):
            converter_calls.append(command)
            Path(command[2]).write_bytes(self.body)
            return type("Finished", (), {"returncode": 0, "stderr": ""})()

        with patch("vispa.data_input_adaptor.PortalSWCProvider.getRawNeuronTreeByID", fresh_fetch):
            with patch("vispa.fnt.subprocess.run", side_effect=convert):
                with patch("vispa.fnt.subprocess.Popen") as launch:
                    launch.return_value.pid = 777
                    launch.return_value.poll.return_value = None
                    result = swc_fnt_tracer(self.config, "251637", "004")
        self.assertEqual(result["status"], "process_started")
        self.assertEqual(result["pixels_loaded"], "unverified")
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual(converter_calls[0][0], str(converter.resolve()))
        self.assertEqual(converter_calls[0][1], result["raw_path"])
        self.assertEqual(converter_calls[0][2], result["project_path"])
        self.assertTrue(result["project_path"].endswith("004.swc.fnt"))
        self.assertEqual(Path(result["project_path"]).read_text(encoding="utf-8").splitlines()[2:],
                         self.body.decode().splitlines()[2:])
        self.assertEqual(Path(result["project_path"]).read_text(encoding="utf-8").splitlines()[1],
                         "http://10.10.48.110/monkeydata/251637/catalog")
        self.assertEqual(launch.call_args.args[0], [str(tracer.resolve()), result["project_path"]])
        self.assertTrue(Path(result["receipt_path"]).is_file())

    def test_borrowed_converter_failure_never_starts_tracer(self):
        self._borrowed_config()
        from vispa.data_input_adaptor import read_swc
        def fresh_fetch(provider, _sample, _neuron):
            raw = provider.cache_root / "251637" / "004.swc"
            raw.parent.mkdir(parents=True)
            raw.write_text("1 1 10 20 30 1 -1\n", encoding="ascii")
            return read_swc(raw)
        failed = type("Finished", (), {"returncode": 3, "stderr": "invalid SWC"})()
        with patch("vispa.data_input_adaptor.PortalSWCProvider.getRawNeuronTreeByID", fresh_fetch):
            with patch("vispa.fnt.subprocess.run", return_value=failed):
                with patch("vispa.fnt.subprocess.Popen") as launch:
                    with self.assertRaisesRegex(RuntimeError, "invalid SWC"):
                        swc_fnt_tracer(self.config, "251637", "004")
                    launch.assert_not_called()

    def test_native_raw_conversion_identity_and_launch_validation(self):
        root = Path(self.temp.name)
        raw_dir = root / "raw" / "251637"
        raw_dir.mkdir(parents=True)
        raw = raw_dir / "004.swc"
        raw.write_text("1 1 10 20 30 1 -1\n", encoding="ascii")
        binary = root / "bin" / "fnt-from-swc.exe"
        binary.parent.mkdir()
        binary.write_bytes(b"converter fixture")
        self.config["sources"] = {"legacy_raw_swc_root": str(root / "raw")}
        self.config["visual_toolkit"]["fnt_tracer"]["converter_executable"] = str(binary)
        self.config["visual_toolkit"]["fnt_tracer"]["max_response_bytes"] = 4096
        plan = resolve_native_fnt_plan(self.config, "251637", "004.swc")
        self.assertEqual(plan["raw_path"], str(raw))
        self.assertFalse(Path(plan["project_path"]).exists())
        self.assertEqual(prepare_native_fnt(self.config, "251637", "004", dry_run=True)["status"], "planned")
        self.assertFalse(Path(plan["project_path"]).exists())

        def convert(command, **_kwargs):
            Path(command[2]).write_bytes(self.body)
            return type("Finished", (), {"returncode": 0, "stderr": ""})()

        with patch("vispa.fnt.subprocess.run", side_effect=convert) as runner:
            first = prepare_native_fnt(self.config, "251637", "004")
            second = prepare_native_fnt(self.config, "251637", "004")
        runner.assert_called_once()
        self.assertEqual((first["status"], second["status"]), ("converted", "cached"))
        self.assertEqual(Path(plan["project_path"]).read_bytes().splitlines()[1],
                         b"http://10.10.48.110/monkeydata/251637/catalog")
        receipt = validate_native_fnt(plan)
        self.assertEqual(receipt["tracing_header_count"], 1)
        self.assertEqual(receipt["raw_tree_node_count"], 1)
        self.assertIn("not total SWC node count", receipt["tracing_header_count_semantics"])
        raw.write_text("1 1 99 20 30 1 -1\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            validate_native_fnt(plan)

    def _native_fixture(self):
        root = Path(self.temp.name)
        raw_dir = root / "raw" / "251637"
        raw_dir.mkdir(parents=True)
        raw = raw_dir / "004.swc"
        raw.write_text("1 1 10 20 30 1 -1\n", encoding="ascii")
        binary = root / "bin" / "fnt-from-swc.exe"
        binary.parent.mkdir()
        binary.write_bytes(b"converter fixture")
        settings = self.config["visual_toolkit"]["fnt_tracer"]
        settings["converter_executable"] = str(binary)
        self.config["sources"] = {"legacy_raw_swc_root": str(root / "raw")}
        self.config["samples"] = {"251637": {"swc_cache": str(root / "processed")}}
        processed = root / "processed"
        processed.mkdir()
        (processed / "004.swc").write_text("1 1 999 999 999 1 -1\n", encoding="ascii")
        return raw, binary

    def _convert_fixture(self, command, **_kwargs):
        Path(command[2]).write_bytes(self.body)
        return type("Finished", (), {"returncode": 0, "stderr": ""})()

    def test_native_prefers_declared_raw_root_over_processed_cache_and_manual(self):
        raw, _binary = self._native_fixture()
        manual = Path(self.temp.name) / "projects"
        manual.mkdir()
        (manual / "251637_004.fnt").write_bytes(self.body)
        self.config["visual_toolkit"]["fnt_tracer"]["project_root"] = str(manual)
        plan = resolve_native_fnt_plan(self.config, "251637", "004")
        self.assertEqual(Path(plan["project_path"]).name, "004.swc.fnt")
        self.assertEqual(plan["raw_path"], str(raw))
        self.assertNotIn("projects", plan["project_path"])
        self.assertEqual(plan["source_declaration"], "sources.legacy_raw_swc_root")
        self.config["sources"].pop("legacy_raw_swc_root")
        with self.assertRaisesRegex(ValueError, "explicit raw_path"):
            resolve_native_fnt_plan(self.config, "251637", "004")
        explicit = resolve_native_fnt_plan(self.config, "251637", "004", raw)
        self.assertEqual(explicit["source_declaration"], "explicit raw_path")

    def test_cli_native_plan_does_not_select_manual_or_portal_cache(self):
        raw, _binary = self._native_fixture()
        manual = Path(self.temp.name) / "projects"
        manual.mkdir()
        wrong = manual / "251637_004.fnt"
        wrong.write_bytes(self.body)
        settings = self.config["visual_toolkit"]["fnt_tracer"]
        settings["project_root"] = str(manual)
        exe = Path(self.temp.name) / "bin" / "fnt-tracer.exe"
        exe.write_bytes(b"tracer")
        settings["executable"] = str(exe)
        portal = Path(resolve_fnt_plan(self.config, "251637", "004")["source_path"])
        portal.parent.mkdir(parents=True)
        portal.write_bytes(self.body)
        plan = native_cli_fnt_plan(self.config, "251637", "004")
        self.assertEqual(plan["native_plan"]["raw_path"], str(raw))
        self.assertNotIn(str(wrong), str(plan.get("project")))
        self.assertNotIn(str(portal), str(plan.get("project")))

    def test_native_converter_failure_and_timeout_leave_no_cache(self):
        self._native_fixture()
        plan = resolve_native_fnt_plan(self.config, "251637", "004")
        failed = type("Finished", (), {"returncode": 7, "stderr": "bad input"})()
        with patch("vispa.fnt.subprocess.run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "bad input"):
                prepare_native_fnt(self.config, "251637", "004")
        self.assertFalse(Path(plan["project_path"]).exists())
        self.assertFalse(Path(plan["receipt_path"]).exists())
        import subprocess
        with patch("vispa.fnt.subprocess.run", side_effect=subprocess.TimeoutExpired("converter", 3)):
            with self.assertRaisesRegex(TimeoutError, "exceeded timeout"):
                prepare_native_fnt(self.config, "251637", "004")
        self.assertFalse(Path(plan["project_path"]).exists())

    def test_native_cache_tampering_rejected_before_launch(self):
        raw, binary = self._native_fixture()
        with patch("vispa.fnt.subprocess.run", side_effect=self._convert_fixture):
            plan = prepare_native_fnt(self.config, "251637", "004")
        exe = Path(self.temp.name) / "bin" / "fnt-tracer.exe"
        exe.write_bytes(b"tracer")
        cases = [(Path(plan["project_path"]), b"changed"),
                 (Path(plan["receipt_path"]), b"{}"),
                 (binary, b"modified converter"),
                 (raw, b"1 1 99 20 30 1 -1\n")]
        for target, replacement in cases:
            original = target.read_bytes()
            try:
                target.write_bytes(replacement)
                with patch("vispa.fnt.subprocess.Popen") as popen:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        launch_native_fnt(plan, exe)
                    popen.assert_not_called()
            finally:
                target.write_bytes(original)
        changed = dict(plan, catalog_url="http://10.10.48.110/monkeydata/other/catalog")
        with patch("vispa.fnt.subprocess.Popen") as popen:
            with self.assertRaisesRegex(ValueError, "receipt catalog_url differs"):
                launch_native_fnt(changed, exe)
            popen.assert_not_called()

    def test_native_launch_reports_process_start_or_immediate_exit(self):
        self._native_fixture()
        with patch("vispa.fnt.subprocess.run", side_effect=self._convert_fixture):
            plan = prepare_native_fnt(self.config, "251637", "004")
        exe = Path(self.temp.name) / "bin" / "fnt-tracer.exe"
        exe.write_bytes(b"tracer")
        with patch("vispa.fnt.subprocess.Popen") as popen:
            popen.return_value.pid = 123
            popen.return_value.poll.return_value = None
            result = launch_native_fnt(plan, exe)
        self.assertEqual(result["status"], "process_started")
        self.assertEqual(result["pixels_loaded"], "unverified")
        self.assertEqual(popen.call_args.kwargs["cwd"], str(exe.parent))
        with patch("vispa.fnt.subprocess.Popen") as popen:
            popen.return_value.poll.return_value = 5
            with self.assertRaisesRegex(RuntimeError, "exited immediately \\(5\\)"):
                launch_native_fnt(plan, exe)


if __name__ == "__main__":
    unittest.main()
