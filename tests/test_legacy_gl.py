"""Focused checks for the optional isolated legacy OpenGL renderer.

Version: 1.11.0.dev3 (local/unreleased)
Last updated: 2026-10-22
Change history: ../CHANGELOG.md
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TEST_INSTALLED = os.environ.get("VISUAL_TOOLKIT_TEST_INSTALLED") == "1"
if not TEST_INSTALLED:
    sys.path.insert(0, str(SRC))


def run_isolated_child(source: str) -> None:
    # A clean process prevents stubbed optional modules and partially imported
    # legacy_gl submodules from contaminating later graphics tests.
    bootstrap = ""
    if not TEST_INSTALLED:
        bootstrap = f"import sys; sys.path.insert(0, {str(SRC)!r})\n"
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", bootstrap + textwrap.dedent(source)],
        check=True,
        capture_output=True,
        text=True,
    )


class LegacyGLIsolationTests(unittest.TestCase):
    def test_optional_package_import_is_lazy(self):
        package = importlib.import_module("vispa.legacy_gl")
        self.assertTrue(package.__doc__)
        self.assertNotIn("vispa.legacy_gl.RenderGL", sys.modules)
        self.assertNotIn("OpenGL", sys.modules)

    def test_extracted_modules_have_no_project_or_network_provider(self):
        package_dir = SRC / "vispa" / "legacy_gl"
        for name in ("RenderGL.py", "GeometryAdapter.py", "SwcLoader.py", "Node.py", "glutils.py", "Arcball.py"):
            with self.subTest(name=name):
                text = (package_dir / name).read_text(encoding="utf-8")
                self.assertNotIn("IONData", text)
                self.assertNotIn("getFileFromServer", text)
                self.assertNotIn("sys.path", text)
                self.assertNotIn("projectome_analysis", text)
        adapter_source = (package_dir / "GeometryAdapter.py").read_text(encoding="utf-8")
        self.assertIn("readFile(processed_swc_path)", adapter_source)
        self.assertIn("somaRadius=200", adapter_source)

    def test_readfile_preserves_stored_xyz_and_exposes_soma_radius(self):
        run_isolated_child(r"""
            import sys, types, tempfile
            from pathlib import Path
            import numpy as np
            glm = types.ModuleType("glm")
            vispy = types.ModuleType("vispy")
            vispy.__path__ = []
            geometry = types.ModuleType("vispy.geometry")
            calls = []
            class Sphere:
                def get_vertices(self): return np.zeros((1, 3), dtype=np.float32)
                def get_faces(self): return np.zeros((0, 3), dtype=np.uint32)
                def get_vertex_normals(self): return np.zeros((1, 3), dtype=np.float32)
            def create_sphere(radius):
                calls.append(radius)
                return Sphere()
            geometry.create_sphere = create_sphere
            vispy.geometry = geometry
            sys.modules.update({"glm": glm, "vispy": vispy, "vispy.geometry": geometry})
            from vispa.legacy_gl.GeometryAdapter import GeometryAdapter
            adapter = GeometryAdapter()
            with tempfile.TemporaryDirectory() as temp_dir:
                swc = Path(temp_dir) / "003.processed.swc"
                swc.write_text("1 1 10 20 30 2 -1\n2 3 13 24 35 0.5 1\n", encoding="utf-8")
                adapter.readFile(swc, somaRadius=321)
            assert calls == [321]
            np.testing.assert_array_equal(
                np.asarray(adapter.geometry.children[1].vertex),
                np.asarray([[10, 20, 30], [13, 24, 35]], dtype=np.float32))
            try:
                adapter.readByID("sample", "003.swc")
            except RuntimeError as exc:
                assert "readFile(processed_swc_path)" in str(exc)
            else:
                raise AssertionError("readByID must fail without an explicit local SWC")
        """)

    def test_renderer_module_import_does_not_need_provider_modules(self):
        # Stub only optional graphics bindings; the import guard proves no project
        # acquisition or HTTP modules are consulted while loading the renderer.
        run_isolated_child(r"""
            import builtins, sys, tempfile, types
            from pathlib import Path
            glm = types.ModuleType("glm")
            vispy = types.ModuleType("vispy")
            vispy.__path__ = []
            geometry = types.ModuleType("vispy.geometry")
            geometry.create_sphere = lambda *args, **kwargs: None
            vispy.geometry = geometry
            opengl = types.ModuleType("OpenGL")
            opengl.__path__ = []
            gl = types.ModuleType("OpenGL.GL")
            gl.__path__ = []
            gl.__all__ = []
            shaders = types.ModuleType("OpenGL.GL.shaders")
            shaders.__all__ = []
            sys.modules.update({"glm": glm, "vispy": vispy, "vispy.geometry": geometry,
                "OpenGL": opengl, "OpenGL.GL": gl, "OpenGL.GL.shaders": shaders})
            original_import = builtins.__import__
            def guarded(name, *args, **kwargs):
                if name.split(".", 1)[0] in {"IONData", "projectome_analysis", "requests"}:
                    raise AssertionError("unexpected project/network import: " + name)
                return original_import(name, *args, **kwargs)
            builtins.__import__ = guarded
            from vispa.legacy_gl.RenderGL import RenderGL
            assert hasattr(RenderGL, "render_once") and hasattr(RenderGL, "run") and hasattr(RenderGL, "savepng")
            try:
                RenderGL()
            except ValueError as exc:
                assert "root_mesh_path is required" in str(exc)
            else:
                raise AssertionError("explicit mesh is required")
            viewer = RenderGL.__new__(RenderGL)
            try:
                viewer.animation()
            except ValueError as exc:
                assert "output_dir is required" in str(exc)
            else:
                raise AssertionError("explicit animation output directory is required")
            with tempfile.TemporaryDirectory() as temp_dir:
                try:
                    RenderGL(root_mesh_path=Path(temp_dir) / "missing-root.obj")
                except FileNotFoundError as exc:
                    assert "local root mesh" in str(exc)
                else:
                    raise AssertionError("missing mesh must fail")
                try:
                    viewer.animation(path="../escape", output_dir=temp_dir)
                except ValueError as exc:
                    assert "path must stay within" in str(exc)
                else:
                    raise AssertionError("animation output traversal must fail")
        """)


if __name__ == "__main__":
    unittest.main()
