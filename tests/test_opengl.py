"""Contract tests for the lazy original-engine OpenGL worker.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
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
import types
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

    def _configure_regions(self, names, *, color=(0.3, 0.7, 1.0), manifest=False):
        folder = self.root / "regions"
        folder.mkdir(exist_ok=True)
        for index, name in enumerate(names):
            (folder / name).write_text(
                f"v {index} 0 0\nv {index + 1} 1 1\nf 1 2 1\n", encoding="ascii")
        payload = json.loads(self.config.read_text(encoding="utf-8"))
        source = payload["sources"]["brain_view"]
        source["region_mesh_root"] = str(folder)
        source["region_color"] = list(color)
        if manifest:
            entries = []
            for path in sorted(folder.glob("*.obj")):
                entries.append({"file": path.name, "bytes": path.stat().st_size,
                                "sha256": opengl._sha256(path),
                                "source_relative": path.name,
                                "destination_relative": path.name})
            manifest_path = folder / "region_mesh_manifest.json"
            manifest_path.write_text(json.dumps({
                "schema": "vispa-region-mesh-dependency-manifest-v1",
                "obj_count": len(entries),
                "total_bytes": sum(entry["bytes"] for entry in entries),
                "files": entries,
            }), encoding="utf-8")
            source["region_manifest"] = str(manifest_path)
        self.config.write_text(json.dumps(payload), encoding="utf-8")
        return folder

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
        self.assertEqual(plan["processed_swc"]["soma_root_stored_xyz"], [0.0, 0.0, 0.0])
        self.assertEqual(plan["visual_roles"]["soma"], {
            "source": "processed SWC parent=-1 root", "stored_xyz": [0.0, 0.0, 0.0],
            "radius": 500.0, "color": [0.0, 1.0, 1.0], "transform": "none"})
        self.assertFalse(Path(plan["session_receipt"]).exists())
        self.assertFalse({"vispa.legacy_gl", "vispa.legacy_gl.RenderGL"}
                         & (set(sys.modules) - before_modules))

    def test_legend_texture_casts_fractional_text_width_to_pixels(self):
        self._write_config(frame="legacy-neuronvis-template-as-stored", units="stored",
                           settings={"window_size": [800, 600]})
        plan = opengl.plan_configured_view("251637", "001.swc", config_path=self.config)
        image = opengl._legend_texture(plan)
        self.assertEqual(image.mode, "RGBA")
        self.assertIsInstance(image.width, int)
        self.assertGreater(image.width, 0)

    def test_configured_mesh_label_names_the_declared_obj(self):
        self._write_config(frame="legacy-neuronvis-template-as-stored", units="stored")
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["sources"]["brain_view"]["mesh_label"] = "NMT mesh"
        self.config.write_text(json.dumps(config), encoding="utf-8")
        plan = opengl.plan_configured_view("251637", "001.swc", config_path=self.config)
        self.assertEqual(plan["mesh_label"], "NMT mesh")

    def test_region_inventory_and_explicit_selection_are_exact_and_manifest_bound(self):
        folder = self._configure_regions([
            "precentral_opercular_cortex (PrCO).obj", "amygdala (Amy).obj"],
            manifest=True)
        plan = opengl.plan_configured_view(
            "251637", "001.swc", config_path=self.config, region="PrCO")
        self.assertEqual(plan["region_mesh"]["filename"],
                         "precentral_opercular_cortex (PrCO).obj")
        self.assertEqual(plan["region_mesh"]["color"], [0.3, 0.7, 1.0])
        self.assertEqual(plan["region_mesh"]["manifest_entry"]["bytes"],
                         (folder / plan["region_mesh"]["filename"]).stat().st_size)
        self.assertEqual(plan["region_resolution"]["match_kind"], "acronym")
        self.assertEqual(plan["region_manifest"]["schema"],
                         "vispa-region-mesh-dependency-manifest-v1")

    def test_portal_suffix_selects_only_one_exact_acronym_or_stays_root_only(self):
        self._configure_regions(["precentral_opercular_cortex (PrCO).obj"])
        selected = opengl.plan_configured_view(
            "251637", "001.swc", "PrCO_49", self.config)
        self.assertEqual(selected["region_mesh"]["acronym"], "PrCO")
        self.assertEqual(selected["region_resolution"]["normalized_query"], "PrCO")
        unmatched = opengl.plan_configured_view(
            "251637", "001.swc", "Unknown_49", self.config)
        self.assertIsNone(unmatched["region_mesh"])
        self.assertEqual(unmatched["region_resolution"]["status"], "unmatched")

    def test_ambiguous_region_acronym_is_never_guessed(self):
        self._configure_regions(["first_region (X).obj", "second_region (X).obj"])
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            opengl.plan_configured_view(
                "251637", "001.swc", config_path=self.config, region="X")
        portal = opengl.plan_configured_view(
            "251637", "001.swc", "X", self.config)
        self.assertIsNone(portal["region_mesh"])
        self.assertEqual(portal["region_resolution"]["status"], "ambiguous")

    def test_region_manifest_rejects_changed_selected_obj(self):
        folder = self._configure_regions(["amygdala (Amy).obj"], manifest=True)
        with (folder / "amygdala (Amy).obj").open("a", encoding="ascii") as stream:
            stream.write("# changed\n")
        with self.assertRaisesRegex(RuntimeError, "does not match the dependency manifest"):
            opengl.plan_configured_view(
                "251637", "001.swc", config_path=self.config, region="Amy")

    def test_worker_adds_one_region_overlay_without_changing_root_camera_basis(self):
        self._configure_regions(["amygdala (Amy).obj"], manifest=True)
        plan = opengl.plan_configured_view(
            "251637", "001.swc", "Amy_16", self.config)
        events = []

        class FakeViewer:
            def __init__(self, **kwargs):
                self.rootMesh = types.SimpleNamespace(
                    Geometry=types.SimpleNamespace(uniformColor=None))
                self.size = kwargs["size"]
                events.append(("viewer", kwargs))
            def setLineWidth(self, value): events.append(("line", value))
            def setBackgroundColor(self, value): events.append(("background", value))
            def setLookAt(self, *value): events.append(("camera", value))
            def loadGeometry(self, path):
                events.append(("load_region", path))
                return types.SimpleNamespace(name=None)
            def addGeometry(self, geometry, color): events.append(("add", geometry.name, color))
            def __createWindow__(self, _size): pass
            def run(self): events.append(("run",))
            def closeWindow(self): events.append(("close",))

        class FakeAdapter:
            def __init__(self, **_kwargs):
                self.geometry = types.SimpleNamespace(name="SWC")
                self.somaColor = None
                self.axonColor = None
                self.dendriteColor = None
            def readFile(self, path, somaRadius):
                events.append(("swc", path, somaRadius, self.somaColor,
                               self.axonColor, self.dendriteColor))

        with mock.patch("vispa.legacy_gl.RenderGL.RenderGL", FakeViewer), \
             mock.patch("vispa.legacy_gl.GeometryAdapter.GeometryAdapter", FakeAdapter), \
             mock.patch.object(opengl, "_install_legend_overlay"), \
             mock.patch.object(opengl, "_set_interactive_caption"), \
             mock.patch.object(opengl, "_write_session_receipt"):
            self.assertEqual(opengl._run_view(plan), 0)
        self.assertIn(("load_region", plan["region_mesh"]["path"]), events)
        self.assertIn(("add", plan["region_mesh"]["display_name"], [0.3, 0.7, 1.0]), events)
        self.assertIn(("swc", plan["processed_swc"]["path"], 500.0,
                       [0.0, 1.0, 1.0], [1.0, 0.5, 0.0], [1.0, 0.5, 0.0]), events)
        viewer_kwargs = next(item[1] for item in events if item[0] == "viewer")
        self.assertEqual(viewer_kwargs["far"], plan["camera"]["clipping"]["far"])

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
        self.assertEqual(command[1], "-I")
        self.assertEqual(Path(command[2]), Path(opengl.__file__).resolve().parents[3] / "run_vispa.py")
        self.assertEqual(command[3], "brain-view")
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertEqual(kwargs["cwd"], tempfile.gettempdir())
        self.assertFalse(kwargs["shell"])
        self.assertNotIn("PYTHONPATH", kwargs["env"])
        self.assertNotIn("MATPLOTLIBRC", kwargs["env"])
        self.assertNotIn("GLFW_LIBRARY", kwargs["env"])

    def test_portal_region_stays_automatic_in_worker_command_and_explicit_cli_is_forwarded(self):
        self._configure_regions(["precentral_operular_area (PrCO).obj"])
        process = mock.Mock()
        with mock.patch.object(opengl.subprocess, "Popen", return_value=process) as popen:
            result = opengl.launch_configured_view(
                "251637", "001.swc", "PrCO_49", self.config)
        portal_command = popen.call_args.args[0]
        self.assertFalse(any(argument.startswith("--region=") for argument in portal_command))
        self.assertEqual(result.vispa_plan["region_mesh"]["legend_label"],
                         "Bilateral soma region · PrCO")

        with mock.patch.object(opengl.subprocess, "Popen", return_value=mock.Mock()) as popen:
            opengl.launch_configured_view(
                "251637", "001.swc", config_path=self.config, region="PrCO")
        explicit_command = popen.call_args.args[0]
        self.assertIn("--region=precentral_operular_area (PrCO).obj", explicit_command)

    def test_installed_worker_requires_matching_candidate_source(self):
        installed = self.root / "installed" / "vispa" / "renderers" / "swc_brain_view.py"
        with mock.patch.object(opengl, "__file__", str(installed)):
            mismatched = opengl.subprocess.CompletedProcess([], 0,
                json.dumps(["1.11.0.dev21", "D:/old/vispa/renderers/swc_brain_view.py"]), "")
            with mock.patch.object(opengl.subprocess, "run", return_value=mismatched):
                with self.assertRaisesRegex(RuntimeError, "does not resolve this VisPa candidate"):
                    opengl._worker_entry(sys.executable)
            matching = opengl.subprocess.CompletedProcess([], 0,
                json.dumps([opengl.__version__, str(installed.resolve())]), "")
            with mock.patch.object(opengl.subprocess, "run", return_value=matching):
                command = opengl._worker_entry(sys.executable)
                probe_code = opengl.subprocess.run.call_args.args[0][-1]
            self.assertEqual(command, [sys.executable, "-I", "-m", "vispa"])
        checkout_src = Path(opengl.__file__).resolve().parents[2]
        actual = opengl.subprocess.run(
            [sys.executable, "-c", probe_code], capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(checkout_src)}, timeout=15)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(json.loads(actual.stdout), [opengl.__version__, str(Path(opengl.__file__).resolve())])

    def test_selected_older_worker_binary_still_runs_candidate_entry(self):
        older = self.root / "older-dev11" / "python.exe"
        older.parent.mkdir()
        older.write_bytes(b"synthetic worker binary")
        with mock.patch.dict(os.environ, {"VISPA_PYTHON": str(older)}):
            with mock.patch.object(opengl.subprocess, "Popen", return_value="process") as popen:
                opengl.launch_configured_view("251637", "001.swc", config_path=self.config)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], str(older.resolve()))
        self.assertEqual(Path(command[2]), Path(opengl.__file__).resolve().parents[3] / "run_vispa.py")

    def test_installed_plan_skips_stale_ambient_worker_for_configured_runtime(self):
        stale = self.root / "stale-dev11" / "python.exe"
        stale.parent.mkdir()
        stale.write_bytes(b"synthetic stale binary")
        installed = self.root / "installed" / "vispa" / "renderers" / "swc_brain_view.py"

        def probe(command, **_kwargs):
            if Path(command[0]) == stale.resolve():
                return opengl.subprocess.CompletedProcess(command, 1, "", "ModuleNotFoundError: vispa.renderers")
            return opengl.subprocess.CompletedProcess(
                command, 0, json.dumps([opengl.__version__, str(installed.resolve())]), "")

        with mock.patch.dict(os.environ, {"VISPA_PYTHON": str(stale), "VISUAL_TOOLKIT_PYTHON": ""}):
            with mock.patch.object(opengl, "__file__", str(installed)):
                with mock.patch.object(opengl.subprocess, "run", side_effect=probe) as run:
                    plan = opengl.plan_configured_view("251637", "001.swc", config_path=self.config)
        self.assertEqual(Path(plan["worker_python"]), Path(sys.executable).resolve())
        self.assertEqual(plan["worker_entry"], [str(Path(sys.executable).resolve()), "-I", "-m", "vispa"])
        self.assertEqual(run.call_count, 2)

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

    def test_snapshot_worker_failure_uses_preview_label(self):
        snapshot = self.root / "failed-snapshot.png"
        with mock.patch.object(opengl.subprocess, "run", return_value=
                               opengl.subprocess.CompletedProcess([], 2, "", "worker failed")):
            with self.assertRaisesRegex(RuntimeError, "SWC Brain View worker exited"):
                opengl.render_configured_snapshot(
                    "251637", "001.swc", snapshot, config_path=self.config)

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
