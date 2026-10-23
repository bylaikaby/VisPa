"""Explicit local-input launcher for the isolated legacy OpenGL viewer.

Version: 1.11.0.dev4 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../CHANGELOG.md
Status: candidate

This module stays standard-library-only until a render is requested. It never
looks up cohort data, fetches sources, transforms coordinates, or mirrors SWCs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

from ._version import __version__

SCHEMA = "visual-toolkit.legacy-gl.v1"
DEFAULT_SETTINGS = {
    "eye_direction": [-1.3, 1.6, 1.5],
    "up": [0.0, 0.0, 1.0],
    "camera_distance_scale": 0.40,
    "line_width": 2.0,
    "soma_radius": 200.0,
    "background": [0.0, 0.0, 0.0],
    "mesh_color": [0.8, 0.8, 0.8],
    "neuron_color": [1.0, 0.5, 0.0],
    "window_size": [1100, 800],
}
_IDENT = re.compile(r"^[A-Za-z0-9_-]+$")
_SETTINGS_KEYS = frozenset(DEFAULT_SETTINGS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stat(path: Path) -> dict:
    stat = path.stat()
    return {"size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _vec(value, name: str, *, nonzero: bool = False) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three finite numbers")
    result = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError(f"{name} must contain three finite numbers")
        try:
            number = float(item)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must contain three finite numbers") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name} must contain three finite numbers")
        result.append(number)
    if nonzero and math.sqrt(sum(x * x for x in result)) <= 0:
        raise ValueError(f"{name} must not be the zero vector")
    return result


def _parse_color(value, name: str) -> list[float]:
    result = _vec(value, name)
    if any(component < 0 or component > 1 for component in result):
        raise ValueError(f"{name} components must be between 0 and 1")
    return result


def resolve_settings(config_settings: dict | None = None, overrides: dict | None = None) -> dict:
    """Resolve and validate brain-view values while preserving the private alias."""
    if config_settings is not None and not isinstance(config_settings, dict):
        raise ValueError("sources.brain_view.settings must be a mapping")
    resolved = {**DEFAULT_SETTINGS, **(config_settings or {}), **(overrides or {})}
    unknown = set(resolved) - _SETTINGS_KEYS
    if unknown:
        raise ValueError(f"unknown brain-view setting(s): {', '.join(sorted(unknown))}")
    resolved["eye_direction"] = _vec(resolved["eye_direction"], "eye_direction", nonzero=True)
    resolved["up"] = _vec(resolved["up"], "up", nonzero=True)
    # Eye and up must not be parallel; the renderer's look-at matrix is undefined otherwise.
    eye, up = resolved["eye_direction"], resolved["up"]
    cross = (eye[1] * up[2] - eye[2] * up[1],
             eye[2] * up[0] - eye[0] * up[2],
             eye[0] * up[1] - eye[1] * up[0])
    if math.sqrt(sum(x * x for x in cross)) < 1e-8:
        raise ValueError("eye_direction and up must not be parallel")
    for key in ("camera_distance_scale", "line_width", "soma_radius"):
        value = resolved[key]
        if isinstance(value, bool):
            raise ValueError(f"{key} must be a positive finite number")
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{key} must be a positive finite number") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be a positive finite number")
        resolved[key] = value
    for key in ("background", "mesh_color", "neuron_color"):
        resolved[key] = _parse_color(resolved[key], key)
    size = resolved["window_size"]
    if not isinstance(size, (list, tuple)) or len(size) != 2 or any(
            isinstance(x, bool) or not isinstance(x, int) or x < 100 for x in size):
        raise ValueError("window_size must contain two integers of at least 100 pixels")
    resolved["window_size"] = [int(size[0]), int(size[1])]
    return resolved


def _settings(config_settings: dict | None, overrides: dict | None = None) -> dict:
    """Compatibility alias retained for existing internal callers."""
    return resolve_settings(config_settings, overrides)


def _obj_bounds(path: Path) -> tuple[list[float], list[float], list[float], float]:
    if path.suffix.lower() != ".obj":
        raise ValueError("bounded camera planning currently requires an OBJ root mesh")
    lo = [math.inf, math.inf, math.inf]
    hi = [-math.inf, -math.inf, -math.inf]
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            fields = line.split()
            if len(fields) < 4 or fields[0] != "v":
                continue
            try:
                xyz = [float(item) for item in fields[1:4]]
            except ValueError:
                continue
            if not all(math.isfinite(item) for item in xyz):
                continue
            for axis, item in enumerate(xyz):
                lo[axis] = min(lo[axis], item)
                hi[axis] = max(hi[axis], item)
    if not all(math.isfinite(x) for x in (*lo, *hi)):
        raise ValueError(f"OBJ contains no finite vertex coordinates: {path}")
    center = [(lo[i] + hi[i]) / 2 for i in range(3)]
    diagonal = math.sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3)))
    if not math.isfinite(diagonal) or diagonal <= 0:
        raise ValueError(f"mesh bounds are degenerate: {path}")
    return center, lo, hi, diagonal


def plan_configured_view(sample_id: str, neuron_id: str, portal_region: str = "",
                         config_path: str | os.PathLike | None = None,
                         *, overrides: dict | None = None, snapshot: str | os.PathLike | None = None) -> dict:
    """Resolve one configured local mesh/SWC pair without importing GL libraries."""
    if not isinstance(sample_id, str) or not _IDENT.fullmatch(sample_id):
        raise ValueError("sample_id must contain only letters, digits, underscore or hyphen")
    if not isinstance(neuron_id, str) or not neuron_id.lower().endswith(".swc"):
        raise ValueError("neuron_id must be an SWC filename, including its .swc suffix")
    if ("/" in neuron_id or "\\" in neuron_id
            or Path(neuron_id).name != neuron_id or neuron_id in {".", ".."}):
        raise ValueError("neuron_id must be a filename, not a path")
    from .dataset_config import load

    config = load(config_path)
    source = config.get("sources", {}).get("brain_view")
    if not isinstance(source, dict):
        raise ValueError("sources.brain_view is not configured")
    frame = source.get("coordinate_frame")
    units = source.get("coordinate_units")
    if not isinstance(frame, str) or not frame.strip():
        raise ValueError("sources.brain_view.coordinate_frame must be explicitly declared")
    if not isinstance(units, str) or not units.strip():
        raise ValueError("sources.brain_view.coordinate_units must be explicitly declared")
    mesh = Path(source["mesh_path"]).expanduser().resolve()
    swc_root = Path(source["processed_swc_root"]).expanduser().resolve()
    swc = (swc_root / sample_id / neuron_id).resolve()
    if not mesh.is_file():
        raise FileNotFoundError(f"configured local brain mesh does not exist: {mesh}")
    if not swc.is_file():
        raise FileNotFoundError(f"configured processed SWC does not exist: {swc}")
    mesh_stat, swc_stat = _stat(mesh), _stat(swc)
    size = mesh_stat["size_bytes"]
    if size > 256 * 1024 * 1024:
        raise ValueError("mesh exceeds 256 MiB local-view limit")
    if swc_stat["size_bytes"] > 64 * 1024 * 1024:
        raise ValueError("SWC exceeds 64 MiB local-view limit")
    mesh_before = (mesh_stat, _sha256(mesh))
    swc_before = (swc_stat, _sha256(swc))
    from .settings import resolve_settings, config_source
    settings = resolve_settings("brain-view", overrides, config=config)
    settings_config_path = (config_source(config) if source.get("settings") or
                            config.get("visual_toolkit", {}).get("settings", {}).get("brain-view") else None)
    center, bounds_min, bounds_max, diagonal = _obj_bounds(mesh)
    if mesh_before != (_stat(mesh), _sha256(mesh)) or swc_before != (_stat(swc), _sha256(swc)):
        raise RuntimeError("mesh or SWC changed while preflight was reading inputs")
    snapshot_path = Path(snapshot).expanduser().resolve() if snapshot else None
    receipt_path = snapshot_path.with_suffix(".json") if snapshot_path else None
    if snapshot_path and (snapshot_path.exists() or receipt_path.exists()):
        raise FileExistsError("snapshot PNG or receipt already exists; choose a new path")
    worker = (os.environ.get("VISPA_PYTHON") or os.environ.get("VISUAL_TOOLKIT_PYTHON")) or config.get("visual_toolkit", {}).get("worker_python") or sys.executable
    worker = str(Path(worker).expanduser().resolve())
    if not Path(worker).is_file():
        raise FileNotFoundError(f"configured VisPa worker Python does not exist: {worker}")
    direction = settings["eye_direction"]
    norm = math.sqrt(sum(value * value for value in direction))
    direction = [value / norm for value in direction]
    distance = settings["camera_distance_scale"] * math.sqrt(3.0) * diagonal
    clipping = {"near": max(distance / 1000.0, 0.01),
                "far": max(distance * 3.0, diagonal * 2.0), "field_of_view_degrees": 45.0}
    from .dataset_config import default_output_root
    session_dir = default_output_root(config) / "brain_view"
    session_receipt = session_dir / f"{sample_id}_{Path(neuron_id).stem}_{uuid.uuid4().hex[:12]}.json"
    return {
        "schema": SCHEMA, "command": "brain-view", "package_version": __version__,
        "sample_id": sample_id, "neuron_id": neuron_id,
        "portal_region": str(portal_region or ""),
        "mesh": {"path": str(mesh), "sha256": mesh_before[1], "stat": mesh_before[0],
                 "bounds_source_xyz": {"center": center, "min": bounds_min, "max": bounds_max,
                                       "diagonal": diagonal}},
        "processed_swc": {"path": str(swc), "sha256": swc_before[1], "stat": swc_before[0]},
        "coordinate_frame": frame.strip(), "coordinate_units": units.strip(),
        "coordinate_handling": "stored coordinates; no inferred transform, scale, or mirror",
        "camera": {"eye_direction_centered_xyz": direction, "center_centered_xyz": [0, 0, 0],
                   "up_centered_xyz": settings["up"], "distance": distance,
                   "distance_basis": "camera_distance_scale × sqrt(3) × root mesh source-bounds diagonal",
                   "clipping": clipping},
        "settings": settings, "worker_python": worker,
        "config_path": str(config["path"]),
        "settings_config_path": settings_config_path,
        "session_receipt": str(session_receipt),
        "display_space": "legacy renderer recenters mesh and neuron together at the origin",
        "snapshot_png": str(snapshot_path) if snapshot_path else None,
        "receipt": str(receipt_path) if receipt_path else None,
        "dry_run": True,
    }


def launch_configured_view(sample_id: str, neuron_id: str, portal_region: str = "",
                           config_path: str | os.PathLike | None = None) -> subprocess.Popen:
    """Start the isolated legacy viewer for one configured local sample/neuron."""
    plan = plan_configured_view(sample_id, neuron_id, portal_region, config_path)
    command = [plan["worker_python"], "-I", "-m", "vispa", "brain-view",
               "--sample", sample_id, "--neuron", neuron_id]
    if portal_region:
        command.extend(("--portal-region", str(portal_region)))
    command.extend(("--config", plan["config_path"]))
    command.extend(_settings_argv(plan["settings"]))
    env = {key: value for key, value in os.environ.items()
           if not (key.startswith("PYTHON") or key.startswith("CONDA")
                   or key.startswith("TCL_") or key.startswith("TK_")
                   or key.startswith("MPL") or key.startswith("MATPLOTLIB")
                   or key in {"PYOPENGL_PLATFORM", "QT_PLUGIN_PATH", "GLFW_LIBRARY"})}
    env["PYTHONNOUSERSITE"] = "1"
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
              "stderr": subprocess.STDOUT, "text": True, "shell": False,
              "env": env, "cwd": tempfile.gettempdir()}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(command, **kwargs)


def _settings_argv(settings: dict) -> list[str]:
    result = []
    for key, flag in (("eye_direction", "--eye-direction"), ("up", "--up"),
                      ("background", "--background"), ("mesh_color", "--mesh-color"),
                      ("neuron_color", "--neuron-color"), ("window_size", "--window-size")):
        result.extend((flag, *(str(value) for value in settings[key])))
    for key, flag in (("camera_distance_scale", "--camera-distance-scale"),
                      ("line_width", "--line-width"), ("soma_radius", "--soma-radius")):
        result.extend((flag, str(settings[key])))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vispa brain-view",
                                     description="View one explicitly configured local processed SWC on a local brain mesh.")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--neuron", required=True)
    parser.add_argument("--portal-region", default="")
    parser.add_argument("--config")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--snapshot", help="write one PNG and adjacent JSON receipt, then exit")
    parser.add_argument("--eye-direction", nargs=3, type=float)
    parser.add_argument("--up", nargs=3, type=float)
    parser.add_argument("--camera-distance-scale", type=float)
    parser.add_argument("--line-width", type=float)
    parser.add_argument("--soma-radius", type=float)
    parser.add_argument("--background", nargs=3, type=float)
    parser.add_argument("--mesh-color", nargs=3, type=float)
    parser.add_argument("--neuron-color", nargs=3, type=float)
    parser.add_argument("--window-size", nargs=2, type=int)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override a brain-view setting; explicit matching flags take precedence")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        from .settings import parse_overrides
        overrides = parse_overrides(args.set)
        # Explicit legacy flags remain the final layer for backwards-compatible CLI precedence.
        for key in _SETTINGS_KEYS:
            value = getattr(args, key, None)
            if value is not None:
                overrides[key] = value
        plan = plan_configured_view(args.sample, args.neuron, args.portal_region,
                                    args.config, overrides=overrides, snapshot=args.snapshot)
        if args.dry_run:
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        return _run_view(plan)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        _parser().error(str(exc))


def _run_view(plan: dict) -> int:
    """Import the optional backend only after preflight succeeds."""
    try:
        from .legacy_gl.GeometryAdapter import GeometryAdapter
        from .legacy_gl.RenderGL import RenderGL
    except ImportError as exc:
        raise RuntimeError("legacy OpenGL dependencies are missing; install vispa[legacy-gl] in the configured worker") from exc

    mesh = Path(plan["mesh"]["path"])
    swc = Path(plan["processed_swc"]["path"])
    before = {"mesh": (_stat(mesh), _sha256(mesh)), "swc": (_stat(swc), _sha256(swc))}
    for label, actual in before.items():
        planned = plan["mesh" if label == "mesh" else "processed_swc"]
        if actual[0] != planned["stat"] or actual[1] != planned["sha256"]:
            raise RuntimeError(f"{label} changed after preflight; re-run the view request")
    settings = plan["settings"]
    viewer = RenderGL(size=tuple(settings["window_size"]), renderModel=0,
                      near=plan["camera"]["clipping"]["near"],
                      far=plan["camera"]["clipping"]["far"],
                      species="monkey", root_mesh_path=mesh)
    viewer.setLineWidth(settings["line_width"])
    viewer.setBackgroundColor(settings["background"])
    viewer.rootMesh.Geometry.uniformColor = settings["mesh_color"]
    direction = plan["camera"]["eye_direction_centered_xyz"]
    distance = plan["camera"]["distance"]
    eye = tuple(value * distance for value in direction)
    viewer.setLookAt(eye, (0.0, 0.0, 0.0),
                     tuple(settings["up"]))
    adapter = GeometryAdapter(species="monkey")
    adapter.width = settings["line_width"]
    adapter.readFile(str(swc), somaRadius=settings["soma_radius"])
    viewer.addGeometry(adapter.geometry, color=settings["neuron_color"])
    if plan["snapshot_png"]:
        return _snapshot(viewer, plan, before)
    try:
        viewer.__createWindow__(viewer.size)
        _install_legend_overlay(viewer, plan)
        _set_interactive_caption(viewer, plan)
        _write_session_receipt(viewer, plan)
        viewer.run()
    finally:
        viewer.closeWindow()
    return 0


def _snapshot(viewer, plan: dict, before: dict) -> int:
    # Snapshot implementation is kept in the isolated worker; GUI dependencies
    # and any legacy GL modules remain lazy until this branch is reached.
    from PIL import Image
    from importlib import import_module
    render_module = import_module(".legacy_gl.RenderGL", __package__)

    output = Path(plan["snapshot_png"])
    receipt_path = Path(plan["receipt"])
    output.parent.mkdir(parents=True, exist_ok=True)
    reserved = []
    try:
        for path in (output, receipt_path):
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            reserved.append(path)
        viewer.__createWindow__(viewer.size)
        _install_legend_overlay(viewer, plan)
        viewer.render_once(str(output))
        with Image.open(output) as image:
            image.verify()
        after = {"mesh": (_stat(Path(plan["mesh"]["path"])), _sha256(Path(plan["mesh"]["path"]))),
                 "swc": (_stat(Path(plan["processed_swc"]["path"])), _sha256(Path(plan["processed_swc"]["path"]))) }
        if before != after:
            raise RuntimeError("mesh or SWC changed during snapshot; output discarded")
        receipt = {**plan, "dry_run": False,
                   "created_at_utc": datetime.now(timezone.utc).isoformat(),
                   "input_check_before": {key: {"stat": val[0], "sha256": val[1]} for key, val in before.items()},
                   "input_check_after": {key: {"stat": val[0], "sha256": val[1]} for key, val in after.items()},
                   "output_png_sha256": _sha256(output),
                   "runtime": {"python_executable": sys.executable, "python_prefix": sys.prefix,
                               "renderer_module": str(Path(render_module.__file__).resolve()),
                               "renderer_sha256": _sha256(Path(render_module.__file__).resolve()),
                               "opengl_version": getattr(viewer, "gl_version", None)},
                   "status": "rendered_candidate"}
        temp = receipt_path.with_name(f".{receipt_path.name}.{os.getpid()}.part")
        temp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, receipt_path)
        print(json.dumps({"snapshot_png": str(output), "receipt": str(receipt_path)}, indent=2))
        return 0
    except Exception:
        for path in reserved:
            path.unlink(missing_ok=True)
        raise
    finally:
        viewer.closeWindow()


def _legend_texture(plan: dict):
    """Build a compact role legend as RGBA pixels for the fixed-screen overlay."""
    from PIL import Image, ImageDraw
    image = Image.new("RGBA", (1080, 72), (20, 20, 20, 228))
    draw = ImageDraw.Draw(image)
    mesh = tuple(round(value * 255) for value in plan["settings"]["mesh_color"])
    neuron = tuple(round(value * 255) for value in plan["settings"]["neuron_color"])
    draw.rectangle((14, 27, 31, 45), fill=mesh + (255,))
    draw.text((40, 28), "Brain mesh", fill=(250, 250, 250, 255))
    draw.line((150, 36, 176, 36), fill=neuron + (255,), width=5)
    draw.text((185, 28), "Processed neuron", fill=(250, 250, 250, 255))
    caption = (f'{plan["sample_id"]} | {plan["neuron_id"]} | '
               f'{plan["coordinate_frame"]} ({plan["coordinate_units"]}; as stored)')
    draw.text((375, 28), caption, fill=(250, 250, 250, 255))
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def _install_legend_overlay(viewer, plan: dict) -> None:
    """Draw a small fixed-screen role legend after each unchanged legacy frame."""
    import ctypes
    import numpy as np
    from OpenGL.GL import (GL_ARRAY_BUFFER, GL_BLEND, GL_CLAMP_TO_EDGE,
                           GL_DEPTH_TEST, GL_FLOAT, GL_FRAGMENT_SHADER,
                           GL_LINEAR, GL_RGBA, GL_STATIC_DRAW, GL_TEXTURE0,
                           GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
                           GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S,
                           GL_TEXTURE_WRAP_T, GL_TRIANGLES, GL_UNSIGNED_BYTE,
                           GL_VERTEX_SHADER, GL_ONE_MINUS_SRC_ALPHA,
                           GL_SRC_ALPHA, glActiveTexture, glAttachShader,
                           glBindBuffer, glBindTexture, glBindVertexArray, glBlendFunc,
                           glBufferData, glCompileShader, glCreateProgram,
                           glCreateShader, glDrawArrays, glEnable, glDisable,
                           glEnableVertexAttribArray, glGenBuffers,
                           glGenTextures, glGenVertexArrays, glGetProgramInfoLog,
                           glGetProgramiv, glGetShaderInfoLog, glGetShaderiv,
                           glGetUniformLocation, glLinkProgram, glShaderSource,
                           glTexImage2D, glTexParameteri, glUniform1i,
                           glUseProgram, glVertexAttribPointer)
    if getattr(viewer, "_visual_toolkit_legend", None):
        return
    vertex_source = """#version 430 core
layout(location=0) in vec2 position; layout(location=1) in vec2 uv;
out vec2 texcoord; void main(){ texcoord=uv; gl_Position=vec4(position,0.0,1.0); }
"""
    fragment_source = """#version 430 core
in vec2 texcoord; uniform sampler2D legend; out vec4 frag;
void main(){ frag=texture(legend,texcoord); }
"""
    def compile_shader(kind, source):
        handle = glCreateShader(kind)
        glShaderSource(handle, source)
        glCompileShader(handle)
        if not glGetShaderiv(handle, 0x8B81):
            error = glGetShaderInfoLog(handle).decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenGL legend shader failed: {error}")
        return handle
    program = glCreateProgram()
    glAttachShader(program, compile_shader(GL_VERTEX_SHADER, vertex_source))
    glAttachShader(program, compile_shader(GL_FRAGMENT_SHADER, fragment_source))
    glLinkProgram(program)
    if not glGetProgramiv(program, 0x8B82):
        error = glGetProgramInfoLog(program).decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenGL legend program failed: {error}")
    vao, vbo, texture = glGenVertexArrays(1), glGenBuffers(1), glGenTextures(1)
    glBindVertexArray(vao)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    vertices = np.asarray([
        -0.985, 0.985, 0, 1,  -0.985, 0.805, 0, 0,   0.985, 0.805, 1, 0,
        -0.985, 0.985, 0, 1,   0.985, 0.805, 1, 0,   0.985, 0.985, 1, 1,
    ], dtype=np.float32)
    glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 2, GL_FLOAT, False, 16, ctypes.c_void_p(0))
    glEnableVertexAttribArray(1)
    glVertexAttribPointer(1, 2, GL_FLOAT, False, 16, ctypes.c_void_p(8))
    glBindVertexArray(0)
    glBindTexture(GL_TEXTURE_2D, texture)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    pixels = np.asarray(_legend_texture(plan), dtype=np.uint8)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, pixels.shape[1], pixels.shape[0], 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, pixels)
    uniform_location = glGetUniformLocation(program, "legend")
    original_render = viewer.render
    def render_with_legend(*args, **kwargs):
        original_render(*args, **kwargs)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glUseProgram(program)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, texture)
        glUniform1i(uniform_location, 0)
        glBindVertexArray(vao)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glBindVertexArray(0)
        glEnable(GL_DEPTH_TEST)
    viewer.render = render_with_legend
    viewer._visual_toolkit_legend = (program, vao, vbo, texture)


def _set_interactive_caption(viewer, plan: dict) -> None:
    """Set role labels in the GLFW title bar as a readable companion caption."""
    try:
        import glfw
        if getattr(viewer, "window", None) is not None:
            color_label = lambda values: "#" + "".join(f"{round(value * 255):02x}" for value in values)
            glfw.set_window_title(viewer.window,
                                  f'Brain mesh ({color_label(plan["settings"]["mesh_color"])}) | '
                                  f'Processed neuron ({color_label(plan["settings"]["neuron_color"])}) | '
                                  f'{plan["sample_id"]} {plan["neuron_id"]} | '
                                  f'{plan["coordinate_frame"]} ({plan["coordinate_units"]}; as stored)')
    except Exception:
        pass


def _write_session_receipt(viewer, plan: dict) -> None:
    """Persist the initial interactive request; later camera gestures are not logged."""
    from importlib import import_module
    render_module = import_module(".legacy_gl.RenderGL", __package__)
    mesh, swc = Path(plan["mesh"]["path"]), Path(plan["processed_swc"]["path"])
    current = {"mesh": (_stat(mesh), _sha256(mesh)), "swc": (_stat(swc), _sha256(swc))}
    for label, value in current.items():
        entry = plan["mesh" if label == "mesh" else "processed_swc"]
        if value[0] != entry["stat"] or value[1] != entry["sha256"]:
            raise RuntimeError(f"{label} changed after preflight; re-run the view request")
    target = Path(plan["session_receipt"])
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = {**plan, "dry_run": False,
               "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "input_check": {key: {"stat": value[0], "sha256": value[1]}
                               for key, value in current.items()},
               "runtime": {"python_executable": sys.executable, "python_prefix": sys.prefix,
                           "renderer_module": str(Path(render_module.__file__).resolve()),
                           "renderer_sha256": _sha256(Path(render_module.__file__).resolve()),
                           "opengl_version": getattr(viewer, "gl_version", None)},
               "interaction_note": "Receipt records the initial fitted pose; later user camera gestures are not captured.",
               "status": "interactive_started"}
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.link(temporary, target)
    except FileExistsError as exc:
        raise FileExistsError(f"session receipt already exists: {target}") from exc
    finally:
        Path(temporary).unlink(missing_ok=True)
