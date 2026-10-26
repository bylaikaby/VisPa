"""Contract tests for the lazy original-engine OpenGL worker.

Version: 1.11.0.dev14 (local/unreleased)
Last updated: 2026-10-26
Change history: ../CHANGELOG.md
Status: candidate
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
if os.environ.get("VISPA_TEST_INSTALLED") != "1":
    sys.path.insert(0, str(ROOT / "src"))

from vispa import opengl


class LegacyOpenGLPlanningTests(unittest.TestCase):
    def setUp(self):
        environment = mock.patch.dict(
            os.environ,
            {"VISPA_PYTHON": sys.executable, "VISUAL_TOOLKIT_PYTHON": ""},
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.mesh = self.root / "brain.obj"
        self.mesh.write_text("v -2 -3 -4\nv 2 3 4\nf 1 2 1\n", encoding="ascii")
        self.swc_root = self.root / "swc"
        self.swc = self.swc_root / "251637" / "001.swc"
        self.swc.parent.mkdir(parents=True)
        self.swc.write_text("1 1 0 0 0 200 -1\n2 3 0 1 0 1 1\n", encoding="ascii")
        self.config = self.root / "datasets.json"
        self._write_config(frame="legacy-neuronvis-template-as-stored", units="stored")

    def tearDown(self):
        self.temp.cleanup()

    def _write_config(self, *, frame=None, units=None, settings=None, scoped_settings=None):
        brain_view = {"mesh_path": str(self.mesh), "processed_swc_root": str(self.swc_root)}
        if frame is not None:
            brain_view["coordinate_frame"] = frame
        if units is not None:
            brain_view["coordinate_units"] = units
        if settings is not None:
            brain_view["settings"] = settings
        payload = {"version": 1, "base_dir": str(self.root),
                   "visual_toolkit": {"worker_python": sys.executable, "output_root": str(self.root / "out"),
                                      "settings": scoped_settings or {}},
                   "sources": {"brain_view": brain_view}}
        self.config.write_text(json.dumps(payload), encoding="utf-8")

    def test_plan_is_lazy_hash_bound_and_uses_centered_scene_camera(self):
        before_modules = set(sys.modules)
        plan = opengl.plan_configured_view("251637", "001.swc", "insula", self.config)
        self.assertEqual(plan["schema"], "visual-toolkit.legacy-gl.v1")
        self.assertEqual(plan["coordinate_units"], "stored")
        self.assertEqual(plan["coordinate_handling"], "stored coordinates; no inferred transform, scale, or mirror")
        self.assertEqual(plan["mesh"]["bounds_source_xyz"]["center"], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(plan["camera"]["distance"], 0.40 * (3 ** 0.5) * (116 ** 0.5))
        self.assertEqual(plan["camera"]["center_centered_xyz"], [0, 0, 0])
        self.assertGreater(plan["camera"]["clipping"]["far"], plan["camera"]["clipping"]["near"])
        self.assertEqual(plan["processed_swc"]["sha256"], opengl._sha256(self.swc))
        self.assertFalse(Path(plan["session_receipt"]).exists())
        self.assertFalse({"vispa.legacy_gl", "vispa.legacy_gl.RenderGL"}
                         & (set(sys.modules) - before_modules))

    def test_shared_brain_view_schema_has_complete_constraints_without_gl_import(self):
        from vispa.settings import settings_schema
        before = set(sys.modules)
        schema = settings_schema("brain-view")
        self.assertEqual(set(schema["settings"]), set(opengl.DEFAULT_SETTINGS))
        for key, spec in schema["settings"].items():
            self.assertIn("default", spec)
            self.assertIn("current", spec)
            self.assertIn("unit", spec)
            self.assertIn("effect", spec)
            self.assertIn("range", spec)
        self.assertIn("not parallel", schema["settings"]["eye_direction"]["range"])
        self.assertFalse({"glfw", "OpenGL", "vispy", "trimesh"} & (set(sys.modules) - before))

    def test_scoped_yaml_values_override_legacy_brain_view_settings(self):
        self._write_config(frame="legacy-neuronvis-template-as-stored", units="stored",
                           settings={"line_width": 2.5},
                           scoped_settings={"brain-view": {"camera_distance_scale": 0.45}})
        plan = opengl.plan_configured_view("251637", "001.swc", config_path=self.config)
        self.assertEqual(plan["settings"]["camera_distance_scale"], 0.45)
        self.assertEqual(plan["settings"]["line_width"], 2.5)
        self.assertEqual(plan["settings_config_path"], str(self.config.resolve()))

    def test_missing_frame_or_units_fails_before_backend_import(self):
        before_modules = set(sys.modules)
        self._write_config(units="stored")
        with self.assertRaisesRegex(ValueError, "coordinate_frame must be explicitly declared"):
            opengl.plan_configured_view("251637", "001.swc", config_path=self.config)
        self._write_config(frame="declared", units=None)
        with self.assertRaisesRegex(ValueError, "coordinate_units must be explicitly declared"):
            opengl.plan_configured_view("251637", "001.swc", config_path=self.config)
        self.assertFalse({"vispa.legacy_gl", "vispa.legacy_gl.RenderGL"}
                         & (set(sys.modules) - before_modules))

    def test_path_and_settings_validation(self):
        with self.assertRaisesRegex(ValueError, "sample_id"):
            opengl.plan_configured_view("../251637", "001.swc", config_path=self.config)
        for neuron_id in ("../001.swc", "..\\001.swc", "sub/001.swc", "sub\\001.swc"):
            with self.subTest(neuron_id=neuron_id), self.assertRaisesRegex(ValueError, "filename"):
                opengl.plan_configured_view("251637", neuron_id, config_path=self.config)
        with self.assertRaisesRegex(ValueError, "must not be the zero vector"):
            opengl.plan_configured_view("251637", "001.swc", config_path=self.config,
                                        overrides={"eye_direction": [0, 0, 0]})
        with self.assertRaisesRegex(ValueError, "must be a positive finite number"):
            opengl.plan_configured_view("251637", "001.swc", config_path=self.config,
                                        overrides={"soma_radius": 0})
        for key, value in (("up", [None, 0, 1]), ("eye_direction", {"x": 1}),
                           ("soma_radius", []), ("line_width", None),
                           ("window_size", [800, None])):
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                opengl.resolve_settings(overrides={key: value})
        from vispa.settings import apply_settings, resolve_settings
        for operation in (lambda: resolve_settings("all"),
                          lambda: apply_settings("all", {})):
            with self.assertRaisesRegex(ValueError, "review, brain-view, montage"):
                operation()

    def test_cli_dry_run_prints_plan_without_writes_or_gl_import(self):
        self._write_config(frame="legacy-neuronvis-template-as-stored", units="stored",
                           settings={"line_width": 2.5},
                           scoped_settings={"brain-view": {"camera_distance_scale": 0.45}})
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = opengl.main(["--sample", "251637", "--neuron", "001.swc",
                                  "--config", str(self.config), "--dry-run",
                                  "--set", 'camera_distance_scale=0.5',
                                  "--set", 'line_width=3.25',
                                  "--camera-distance-scale", "0.6",
                                  "--line-width", "3.5"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["settings"]["line_width"], 3.5)
        self.assertEqual(payload["settings"]["camera_distance_scale"], 0.6)
        self.assertEqual(payload["settings"]["line_width"], 3.5)
        self.assertEqual(payload["settings_config_path"], str(self.config.resolve()))
        self.assertFalse(Path(payload["session_receipt"]).exists())
        self.assertNotIn("vispa.legacy_gl.RenderGL", sys.modules)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            opengl.main(["--sample", "251637", "--neuron", "001.swc",
                         "--config", str(self.config), "--dry-run", "--set", "broken"])
        self.assertIn("--set expects PATH=VALUE", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_top_level_help_lists_brain_view_lazily(self):
        before_modules = set(sys.modules)
        from vispa.cli import _parser
        help_text = _parser().format_help()
        self.assertIn("brain-view", help_text)
        self.assertIn("gui", help_text)
        self.assertFalse({"vispa.legacy_gl", "vispa.legacy_gl.RenderGL"}
                         & (set(sys.modules) - before_modules))

    def test_launcher_uses_isolated_absolute_worker_and_no_mesh_cwd(self):
        with mock.patch.object(opengl.subprocess, "Popen", return_value="process") as popen:
            result = opengl.launch_configured_view("251637", "001.swc", "insula", self.config)
        self.assertEqual(result, "process")
        command, kwargs = popen.call_args.args[0], popen.call_args.kwargs
        self.assertEqual(command[1:4], ["-I", "-m", "vispa"])
        self.assertEqual(command[4], "brain-view")
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertEqual(kwargs["cwd"], tempfile.gettempdir())
        self.assertFalse(kwargs["shell"])
        self.assertNotIn("PYTHONPATH", kwargs["env"])
        self.assertNotIn("MATPLOTLIBRC", kwargs["env"])
        self.assertNotIn("GLFW_LIBRARY", kwargs["env"])

    def test_stale_environment_worker_falls_back_to_configured_python(self):
        stale = self.root / "retired-runtime" / "python.exe"
        with mock.patch.dict(os.environ, {
                "VISPA_PYTHON": str(stale), "VISUAL_TOOLKIT_PYTHON": ""}):
            plan = opengl.plan_configured_view(
                "251637", "001.swc", config_path=self.config)
        self.assertEqual(Path(plan["worker_python"]), Path(sys.executable).resolve())

    def test_snapshot_worker_returns_hash_verified_receipt(self):
        snapshot = self.root / "swc3d.png"
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            output = Path(command[command.index("--snapshot") + 1])
            output.write_bytes(b"synthetic-png")
            output.with_suffix(".json").write_text(json.dumps({
                "status": "rendered_candidate",
                "output_png_sha256": opengl._sha256(output),
            }), encoding="utf-8")
            return opengl.subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(opengl.subprocess, "run", side_effect=fake_run):
            receipt = opengl.render_configured_snapshot(
                "251637", "001.swc", snapshot, portal_region="-x",
                config_path=self.config, mesh_path=self.mesh, mesh_label="-h")
        self.assertEqual(receipt["status"], "rendered_candidate")
        self.assertTrue(snapshot.is_file())
        self.assertIn("--portal-region=-x", commands[0])
        self.assertIn(f"--mesh-path={self.mesh.resolve()}", commands[0])
        self.assertIn("--mesh-label=-h", commands[0])

    def test_snapshot_collision_rejected_without_overwrite(self):
        target = self.root / "review.png"
        target.write_bytes(b"keep")
        with self.assertRaisesRegex(FileExistsError, "already exists"):
            opengl.plan_configured_view("251637", "001.swc", config_path=self.config,
                                        snapshot=target)
        self.assertEqual(target.read_bytes(), b"keep")

    def test_interactive_receipt_records_initial_request_without_touching_sources(self):
        plan = opengl.plan_configured_view("251637", "001.swc", config_path=self.config)
        class Viewer:
            gl_version = "4.6 test"
        opengl._write_session_receipt(Viewer(), plan)
        receipt_path = Path(plan["session_receipt"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "interactive_started")
        self.assertEqual(receipt["coordinate_frame"], "legacy-neuronvis-template-as-stored")
        self.assertEqual(receipt["runtime"]["opengl_version"], "4.6 test")
        self.assertIn("later user camera gestures are not captured", receipt["interaction_note"])
        self.assertEqual(receipt["input_check"]["mesh"]["sha256"], opengl._sha256(self.mesh))


if __name__ == "__main__":
    unittest.main()
