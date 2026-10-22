"""CLI contract tests for bounded standalone use.

Version: 1.11.0.dev2 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEST_INSTALLED = os.environ.get("VISUAL_TOOLKIT_TEST_INSTALLED") == "1"
if not TEST_INSTALLED:
    sys.path.insert(0, str(ROOT / "src"))
ENV = {key: value for key, value in os.environ.items()
       if key not in {"PYTHONPATH", "VISPA_CONFIG", "VISUAL_TOOLKIT_CONFIG", "PROJECTOME_DATASETS"}}
ENV.update({"MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1"})
if TEST_INSTALLED:
    ENV["VISUAL_TOOLKIT_TEST_INSTALLED"] = "1"
else:
    ENV["PYTHONPATH"] = str(ROOT / "src")


def run_cli(*args, cwd=None, env=None):
    command = [sys.executable]
    if TEST_INSTALLED:
        command.append("-I")
    command.extend(("-m", "vispa", *map(str, args)))
    return subprocess.run(command,
                          cwd=cwd or Path.cwd(), env=ENV if env is None else env, text=True,
                          capture_output=True, check=False)


def assert_backend_is_installed(testcase, plan):
    if not TEST_INSTALLED:
        return
    purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
    backend = Path(plan["runtime"]["backend_module"]).resolve()
    testcase.assertTrue(backend.is_relative_to(purelib), f"backend came from {backend}, not {purelib}")
    testcase.assertEqual(Path(plan["python_executable"]).resolve(), Path(sys.executable).resolve())
    testcase.assertEqual(Path(plan["runtime"]["python_prefix"]).resolve(), Path(sys.prefix).resolve())


def render_args(input_path, output_dir, *extra):
    return ("render", "--input", input_path, "--sample", "DS01",
            "--neuron", "001.swc", "--soma", "2", "2", "1",
            "--origin", "0", "0", "0", "--resolution", "1", "1", "1",
            "--coordinate-frame", "synthetic-XYZ", "--output-dir", output_dir,
            *extra)


def same_planned_path(actual, expected, existing_parent):
    actual, expected = Path(actual), Path(expected)
    return (actual.name == expected.name and actual.parent.name == expected.parent.name
            and os.path.samefile(actual.parent.parent, existing_parent))


class CliContractTests(unittest.TestCase):
    def setUp(self):
        isolated = mock.patch.dict(os.environ, {"VISPA_CONFIG": ""})
        isolated.start()
        self.addCleanup(isolated.stop)

    def test_install_path_entry_is_idempotent_and_removable(self):
        from vispa.cli import merge_user_path, remove_user_path
        root = Path(tempfile.gettempdir()) / "VisPa path test"
        tools = str(root / "Tools")
        tools_in_current = tools + os.sep * 2
        duplicate = str(root / "tools") if os.name == "nt" else tools
        current = f"{root / 'Windows'};{tools_in_current}"
        unchanged, changed = merge_user_path(current, duplicate)
        self.assertFalse(changed)
        self.assertEqual(unchanged, current)
        entry = str(root / "vispa" / ".venv" / "Scripts")
        added, changed = merge_user_path(current, entry)
        self.assertTrue(changed)
        self.assertTrue(added.endswith(entry))
        removed, changed = remove_user_path(added, entry + os.sep * 2)
        self.assertTrue(changed)
        self.assertNotIn(entry, removed)
        case_variant = str(root / "VISPA" / ".venv" / "Scripts")
        _, changed = merge_user_path(added, case_variant)
        self.assertEqual(changed, os.name != "nt")

    def test_help_and_version_do_not_import_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            script = "import sys; import vispa; assert 'vispa.toolkit' not in sys.modules"
            command = [sys.executable]
            if TEST_INSTALLED:
                command.append("-I")
            command.extend(("-c", script))
            result = subprocess.run(command, cwd=tmp_path, env=ENV,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(run_cli("--help", cwd=tmp_path).returncode, 0)
            version = run_cli("--version", cwd=tmp_path)
            self.assertEqual(version.returncode, 0)
            self.assertIn("1.11.0.dev2", version.stdout)

    def test_settings_command_prints_discoverable_json_without_optional_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            isolated_env = ENV.copy()
            isolated_env["APPDATA"] = str(tmp_path / "empty-appdata")
            result = run_cli("settings", cwd=tmp_path, env=isolated_env)
            self.assertEqual(result.returncode, 0, result.stderr)
            schema = json.loads(result.stdout)
            self.assertEqual(schema["schema"], "visual-toolkit.review-settings.v1")
            self.assertEqual(schema["settings"]["marker.color"]["default"], "#00e5ee")
            self.assertIn("effect", schema["settings"]["figure.panel_dpi"])
            grouped = run_cli("settings", "--scope", "all", cwd=tmp_path, env=isolated_env)
            self.assertEqual(grouped.returncode, 0, grouped.stderr)
            groups = json.loads(grouped.stdout)
            self.assertEqual(set(groups["scopes"]), {"review", "brain-view", "montage"})
            self.assertIn("unit", groups["scopes"]["review"]["settings"]["context.width_um"])
            self.assertIn("vector_relation", groups["scopes"]["brain-view"]["settings"]["eye_direction"])
            self.assertIn("figure_size_inches", groups["scopes"]["montage"]["settings"])
            script = """import builtins, sys
if sys.argv[1]:
    sys.path.insert(0, sys.argv[1])
original = builtins.__import__
blocked = {"tifffile", "nibabel", "paramiko", "yaml", "scipy", "glfw", "OpenGL", "vispy", "trimesh"}
def guarded(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked:
        raise AssertionError("optional import attempted: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
if not sys.argv[1]:
    import sysconfig
    from pathlib import Path
    import vispa.settings as settings_module
    package_root = Path(sysconfig.get_paths()["purelib"]).resolve()
    assert Path(settings_module.__file__).resolve().is_relative_to(package_root)
from vispa.cli import main
assert main(["settings", "--scope", "all"]) == 0
"""
            command = [sys.executable]
            if TEST_INSTALLED:
                command.append("-I")
            command.extend(("-c", script, "" if TEST_INSTALLED else str(ROOT / "src")))
            guarded = subprocess.run(command, cwd=tmp_path, env=isolated_env,
                                     text=True, capture_output=True)
            self.assertEqual(guarded.returncode, 0, guarded.stderr)
            self.assertEqual(set(json.loads(guarded.stdout)["scopes"]), {"review", "brain-view", "montage"})

    def test_settings_command_reports_invalid_config_as_cli_error(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "invalid.json"
            config.write_text(json.dumps({"version": 1, "visual_toolkit": {"settings": {
                "review": {"marker.color": "invalid"}}}}), encoding="utf-8")
            result = run_cli("settings", "--scope", "review", "--config", config, cwd=directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_config_init_is_bounded_to_explicit_yaml_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rejected = run_cli("config-init", "--output", root / "config.json",
                               "--dry-run", cwd=root)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("error:", rejected.stderr)
            self.assertNotIn("Traceback", rejected.stderr)
            self.assertFalse((root / "config.json").exists())
            dry = run_cli("config-init", "--output", root / "config.yaml",
                          "--dry-run", cwd=root)
            self.assertEqual(dry.returncode, 0, dry.stderr)
            plan = json.loads(dry.stdout)
            self.assertEqual((plan["action"], plan["source_kind"]),
                             ("would_create", "package_defaults"))
            self.assertFalse((root / "config.yaml").exists())
            created = run_cli("config-init", "--output", root / "config.yaml", cwd=root)
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertTrue((root / "config.yaml").is_file())
            second = run_cli("config-init", "--output", root / "config.yaml", cwd=root)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(second.stdout)["action"], "already_exists")
            settings = run_cli("settings", "--scope", "all",
                               "--config", root / "config.yaml", cwd=root)
            self.assertEqual(settings.returncode, 0, settings.stderr)
            self.assertEqual(set(json.loads(settings.stdout)["scopes"]),
                             {"review", "brain-view", "montage"})

    def test_dry_run_resolves_exact_names_settings_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "tiny.npy"
            np.save(source, np.ones((3, 5, 5), dtype=np.uint8))
            output = tmp_path / "out"
            result = run_cli(*render_args(source, output, "--set", "marker.color=#123456", "--dry-run"),
                             cwd=tmp_path)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            assert_backend_is_installed(self, plan)
            self.assertEqual(plan["schema"], "visual-toolkit.render.v1")
            self.assertEqual(plan["package_version"], "1.11.0.dev2")
            self.assertTrue(Path(plan["python_executable"]).is_file())
            self.assertTrue(Path(plan["runtime"]["python_executable"]).is_file())
            self.assertTrue(Path(plan["runtime"]["backend_module"]).is_file())
            self.assertTrue(same_planned_path(plan["output_png"], output / "DS01_001.swc_soma.png", tmp_path))
            self.assertTrue(same_planned_path(plan["receipt"], output / "DS01_001.swc_soma.json", tmp_path))
            self.assertEqual(plan["review_settings"]["marker"]["color"], "#123456")
            self.assertFalse(output.exists())

    def test_review_yaml_then_cli_precedence_matches_shared_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tiny.npy"
            np.save(source, np.ones((3, 5, 5), dtype=np.uint8))
            config = root / "settings.json"
            config.write_text(json.dumps({"version": 1, "visual_toolkit": {"settings": {
                "review": {"marker.color": "#123456", "figure.review_dpi": 50}}}}), encoding="utf-8")
            result = run_cli(*render_args(source, root / "out", "--config", config,
                                          "--set", "marker.color=#abcdef", "--dry-run"), cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan["review_settings"]["marker"]["color"], "#abcdef")
            self.assertEqual(plan["review_settings"]["figure"]["review_dpi"], 50)
            self.assertEqual(Path(plan["settings_config_path"]), config.resolve())
            self.assertFalse((root / "out").exists())
            schema = run_cli("settings", "--scope", "review", "--config", config, cwd=root)
            self.assertEqual(schema.returncode, 0, schema.stderr)
            current = json.loads(schema.stdout)
            self.assertEqual(current["settings"]["marker.color"]["current"], "#123456")

    def test_invalid_overrides_fail_even_in_dry_run(self):
        for override in ("broken", "marker.color=red", "marker.nope=1", "figure.review_dpi=0"):
            with self.subTest(override=override), tempfile.TemporaryDirectory() as directory:
                tmp_path = Path(directory)
                source = tmp_path / "tiny.npy"
                np.save(source, np.ones((3, 5, 5), dtype=np.uint8))
                result = run_cli(*render_args(source, tmp_path / "out", "--set", override, "--dry-run"),
                                 cwd=tmp_path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("error:", result.stderr)
                self.assertFalse((tmp_path / "out").exists())

    def test_missing_input_and_collision_fail_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            output = tmp_path / "out"
            missing = run_cli(*render_args(tmp_path / "missing.npy", output, "--dry-run"), cwd=tmp_path)
            self.assertNotEqual(missing.returncode, 0)
            source = tmp_path / "tiny.npy"
            np.save(source, np.ones((3, 5, 5), dtype=np.uint8))
            output.mkdir()
            expected = output / "DS01_001.swc_soma.png"
            expected.write_bytes(b"preserve")
            collision = run_cli(*render_args(source, output, "--dry-run"), cwd=tmp_path)
            self.assertNotEqual(collision.returncode, 0)
            self.assertEqual(expected.read_bytes(), b"preserve")

    def test_bounded_render_writes_one_png_and_receipt_with_matching_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "tiny.npy"
            volume = np.zeros((3, 5, 5), dtype=np.uint8)
            volume[:, 2, 2] = 255
            np.save(source, volume)
            output = tmp_path / "out"
            result = run_cli(*render_args(source, output, "--set", "figure.review_figsize=5,3",
                                          "--set", "figure.review_dpi=50",
                                          "--set", "marker.color=#ff00ff",
                                          "--set", "marker.crosshair_px=2",
                                          "--set", "marker.label_offset_px=0"), cwd=tmp_path)
            self.assertEqual(result.returncode, 0, result.stderr)
            png = output / "DS01_001.swc_soma.png"
            receipt_path = output / "DS01_001.swc_soma.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertTrue(png.is_file() and png.stat().st_size > 100)
            self.assertEqual({path.name for path in output.iterdir()}, {png.name, receipt_path.name})
            self.assertTrue(os.path.samefile(receipt["output_png"], png))
            self.assertEqual(receipt["schema"], "visual-toolkit.render.v1")
            self.assertEqual(receipt["package_version"], "1.11.0.dev2")
            runtime = receipt["runtime"]
            self.assertTrue(Path(runtime["python_prefix"]).exists())
            self.assertEqual(runtime["backend_sha256"],
                             hashlib.sha256(Path(runtime["backend_module"]).read_bytes()).hexdigest())
            self.assertEqual(receipt["review_settings"]["figure"]["review_dpi"], 50)
            self.assertEqual(receipt["review_settings"]["marker"]["color"], "#ff00ff")
            from PIL import Image
            with Image.open(png) as rendered_image:
                rendered_image = rendered_image.convert("RGB")
                self.assertGreater(rendered_image.width, 100)
                self.assertGreater(rendered_image.height, 50)
                self.assertLess(rendered_image.width, 400)
                self.assertLess(rendered_image.height, 250)
                pixels = np.asarray(rendered_image)
                magenta_pixels = int(((pixels[:, :, 0] > 220) &
                                      (pixels[:, :, 1] < 40) &
                                      (pixels[:, :, 2] > 220)).sum())
                self.assertGreater(magenta_pixels, 0)
            self.assertEqual(receipt["input_stat_before"], receipt["input_stat_after"])
            self.assertEqual(receipt["input_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(receipt["output_sha256"], hashlib.sha256(png.read_bytes()).hexdigest())
            self.assertEqual(receipt["input_shape_zyx"], [3, 5, 5])
            self.assertEqual(receipt["render_labels"]["legend_header_role"], "Soma")
            self.assertIn("pixel index", receipt["render_labels"]["x_axis"])
            self.assertIn("pixel index", receipt["render_labels"]["y_axis"])

    def test_configured_render_restores_global_and_cached_review_defaults_on_success_and_failure(self):
        from vispa import toolkit
        from vispa.cli import main

        original_settings = toolkit.review_settings_snapshot()
        original_settings_ref = toolkit.REVIEW_SETTINGS
        def state():
            return (toolkit.review_settings_snapshot(), toolkit.TARGET_MARKER_COLOR,
                    toolkit.WIDEFIELD_DEFAULT_PARAMETERS, toolkit.SCALE_BAR_CANDIDATES_UM,
                    toolkit.VisPa.PANEL_FIGSIZE, toolkit.VisPa.PANEL_DPI,
                    toolkit.VisPa.TRIO_FIGSIZE, toolkit.VisPa.TRIO_DPI)
        original_state = state()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tiny.npy"
            np.save(source, np.ones((3, 5, 5), dtype=np.uint8))
            config = root / "settings.json"
            config.write_text(json.dumps({"version": 1, "visual_toolkit": {"settings": {
                "review": {"marker.color": "#123456", "figure.panel_dpi": 40,
                           "figure.review_dpi": 45}}}}), encoding="utf-8")
            try:
                for index in range(2):
                    result = main(list(map(str, render_args(source, root / f"success-{index}",
                                                            "--config", config))))
                    self.assertEqual(result, 0)
                    self.assertIs(toolkit.REVIEW_SETTINGS, original_settings_ref)
                    self.assertEqual(state(), original_state)

                with mock.patch.object(toolkit, "VisPa", side_effect=RuntimeError("render failed")):
                    with self.assertRaises(SystemExit):
                        main(list(map(str, render_args(source, root / "failure", "--config", config))))
                self.assertEqual(state(), original_state)
                self.assertIs(toolkit.REVIEW_SETTINGS, original_settings_ref)
            finally:
                original_settings_ref.clear()
                original_settings_ref.update(original_settings)
                toolkit.REVIEW_SETTINGS = original_settings_ref
                toolkit._sync_review_setting_constants()




class FNTResourcePreflightTests(unittest.TestCase):
    def test_requires_matching_project_and_never_starts_binary(self):
        from vispa.cli import fnt_plan
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / 'fnt-tracer.exe'
            exe.write_bytes(b'not executable')
            config = {'visual_toolkit': {'fnt_tracer': {'executable': exe, 'project_root': root}}}
            with mock.patch('subprocess.Popen', side_effect=AssertionError('must not launch')):
                missing = fnt_plan(config, 's01', '003.swc')
                self.assertFalse(missing['ready'])
                self.assertIsNone(missing['command'])
                project = root / 's01_003.decimate.fnt'
                project.write_bytes(b'fixture project')
                ready = fnt_plan(config, 's01', '003.swc')
                self.assertEqual(ready['command'], [str(exe), str(project)])
                self.assertTrue(ready['ready'])
                exe.unlink()
                self.assertFalse(fnt_plan(config, 's01', '003.swc')['ready'])
                with self.assertRaises(ValueError):
                    fnt_plan(config, '../s01', '003.swc')


if __name__ == "__main__":
    unittest.main()
