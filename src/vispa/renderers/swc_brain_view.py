"""Explicit local-input launcher for the isolated legacy OpenGL viewer.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../../CHANGELOG.md
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

from .._version import __version__

SCHEMA = "visual-toolkit.legacy-gl.v1"
TRACE_LABEL = "Processed neuron SWC"
_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
DEFAULT_WORKER_CANDIDATES = (
    _LOCALAPPDATA / "VisPa" / "conda-env" / "python.exe",
    _LOCALAPPDATA / "VisPa" / "conda-env" / "bin" / "python",
)
from ..config import BRAIN_VIEW_DEFAULT_SETTINGS as DEFAULT_SETTINGS
_IDENT = re.compile(r"^[A-Za-z0-9_-]+$")
_REGION_NAME = re.compile(r"^(?P<display>.+?)\s*\((?P<acronym>[^()]+)\)$")
_PORTAL_SUFFIX = re.compile(r"^(?P<acronym>[A-Za-z][A-Za-z0-9-]*?)_[0-9]+$")
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


def _swc_root_coordinate(path: Path) -> list[float]:
    """Read the declared SWC root coordinate without changing its stored frame."""
    roots = []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.split()
            if not fields or fields[0].startswith("#"):
                continue
            if len(fields) < 7:
                raise ValueError(f"invalid SWC row {line_number}: expected at least 7 fields")
            try:
                xyz = [float(fields[index]) for index in (2, 3, 4)]
                parent = int(fields[6])
            except ValueError as exc:
                raise ValueError(f"invalid SWC row {line_number}: non-numeric coordinate or parent") from exc
            if not all(math.isfinite(value) for value in xyz):
                raise ValueError(f"invalid SWC row {line_number}: non-finite root candidate")
            if parent == -1:
                roots.append(xyz)
    if len(roots) != 1:
        raise ValueError(f"processed SWC must declare exactly one parent=-1 root; found {len(roots)}")
    return roots[0]


from ..config import _vec, _parse_color, resolve_brain_view_settings as resolve_settings

def _settings(config_settings: dict | None, overrides: dict | None = None) -> dict:
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


def region_mesh_inventory(root: str | os.PathLike) -> list[dict]:
    """Describe direct-child legacy region OBJs without reading mesh pixels/vertices."""
    folder = Path(root).expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"configured region mesh folder does not exist: {folder}")
    files = sorted((path for path in folder.iterdir()
                    if path.is_file() and path.suffix.lower() == ".obj"),
                   key=lambda path: (path.name.casefold(), path.name))
    if len(files) > 2048:
        raise ValueError("region mesh folder exceeds the 2048-file inventory limit")
    result = []
    for path in files:
        match = _REGION_NAME.fullmatch(path.stem)
        display = match.group("display") if match else path.stem
        acronym = match.group("acronym") if match else None
        result.append({
            "path": str(path), "filename": path.name,
            "display_name": display, "display_label": display.replace("_", " "),
            "acronym": acronym,
        })
    return result


def _region_matches(inventory: list[dict], query: str) -> list[dict]:
    key = query.strip().casefold()
    return [entry for entry in inventory if key in {
        entry["filename"].casefold(), Path(entry["filename"]).stem.casefold(),
        entry["display_name"].casefold(), entry["display_label"].casefold(),
        (entry["acronym"] or "").casefold(),
    }]


def resolve_region_mesh(root: str | os.PathLike, query: str) -> tuple[dict, str]:
    """Resolve one exact filename/display/acronym; never choose among duplicates."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("region selection must be a non-empty filename, display name or acronym")
    matches = _region_matches(region_mesh_inventory(root), query)
    if not matches:
        raise ValueError(f"no region OBJ exactly matches {query!r}")
    if len(matches) != 1:
        names = ", ".join(entry["filename"] for entry in matches[:5])
        raise ValueError(f"region selection {query!r} is ambiguous: {names}")
    entry = matches[0]
    key = query.strip().casefold()
    kind = ("filename" if key == entry["filename"].casefold() else
            "acronym" if key == (entry["acronym"] or "").casefold() else
            "display_name")
    return entry, kind


def _region_manifest(source: dict) -> tuple[dict | None, dict | None]:
    manifest_value = source.get("region_manifest")
    if manifest_value is None:
        return None, None
    path = Path(manifest_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"configured region mesh manifest does not exist: {path}")
    stat = _stat(path)
    if stat["size_bytes"] > 4 * 1024 * 1024:
        raise ValueError("region mesh manifest exceeds 4 MiB")
    digest = _sha256(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"invalid region mesh manifest: {exc}") from exc
    if payload.get("schema") != "vispa-region-mesh-dependency-manifest-v1":
        raise ValueError("unsupported region mesh manifest schema")
    files = payload.get("files")
    if not isinstance(files, list) or payload.get("obj_count") != len(files):
        raise ValueError("region mesh manifest files/count mismatch")
    by_name = {}
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("region mesh manifest file entry must be a mapping")
        name, size, sha = entry.get("file"), entry.get("bytes"), entry.get("sha256")
        if (not isinstance(name, str) or Path(name).name != name or
                not name.lower().endswith(".obj") or not isinstance(size, int) or size < 0 or
                not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha)):
            raise ValueError("invalid region mesh manifest file entry")
        key = name.casefold()
        if key in by_name:
            raise ValueError(f"duplicate region mesh manifest filename: {name}")
        by_name[key] = {**entry, "sha256": sha.lower()}
    return by_name, {"path": str(path), "sha256": digest, "stat": stat,
                     "schema": payload["schema"], "obj_count": payload["obj_count"],
                     "total_bytes": payload.get("total_bytes")}


def _plan_region(source: dict, requested: str | None, portal_region: str) -> tuple[dict | None, dict, dict | None]:
    """Resolve explicit selection strictly; portal metadata may only select uniquely."""
    root = source.get("region_mesh_root")
    explicit = requested is not None
    raw_query = requested if explicit else str(portal_region or "").strip()
    resolution = {"source": "explicit" if explicit else "portal_region",
                  "requested": raw_query, "status": "not_selected", "reason": ""}
    manifest_files, manifest_info = _region_manifest(source)
    if not raw_query:
        resolution["reason"] = "no region was requested or reported by the portal"
        return None, resolution, manifest_info
    if root is None:
        if explicit:
            raise ValueError("--region requires sources.brain_view.region_mesh_root")
        resolution["reason"] = "sources.brain_view.region_mesh_root is not configured"
        return None, resolution, manifest_info
    query = raw_query
    normalized = False
    if not explicit:
        direct = _region_matches(region_mesh_inventory(root), query)
        if len(direct) == 1:
            entry, match_kind = direct[0], "portal_exact"
        elif len(direct) > 1:
            resolution.update(status="ambiguous", reason="portal region matches multiple OBJ files")
            return None, resolution, manifest_info
        else:
            suffix = _PORTAL_SUFFIX.fullmatch(query)
            if suffix is None:
                resolution.update(status="unmatched", reason="portal region has no exact OBJ match")
                return None, resolution, manifest_info
            query = suffix.group("acronym")
            normalized = True
            try:
                entry, match_kind = resolve_region_mesh(root, query)
            except ValueError as exc:
                resolution.update(status="unmatched", reason=str(exc), normalized_query=query)
                return None, resolution, manifest_info
            if match_kind != "acronym":
                resolution.update(status="unmatched",
                                  reason="normalized portal region did not match an exact acronym",
                                  normalized_query=query)
                return None, resolution, manifest_info
    else:
        entry, match_kind = resolve_region_mesh(root, query)
    path = Path(entry["path"])
    stat = _stat(path)
    if stat["size_bytes"] > 256 * 1024 * 1024:
        raise ValueError("region mesh exceeds 256 MiB local-view limit")
    digest = _sha256(path)
    if (stat, digest) != (_stat(path), _sha256(path)):
        raise RuntimeError("region mesh changed while preflight was reading it")
    manifest_entry = None
    if manifest_files is not None:
        manifest_entry = manifest_files.get(path.name.casefold())
        if manifest_entry is None:
            raise ValueError(f"selected region OBJ is absent from the dependency manifest: {path.name}")
        if manifest_entry["bytes"] != stat["size_bytes"] or manifest_entry["sha256"] != digest:
            raise RuntimeError(f"selected region OBJ does not match the dependency manifest: {path.name}")
    short_label = entry["acronym"] or entry["display_label"]
    legend_label = (f"Region · {short_label}" if explicit else
                    f"Bilateral soma region · {short_label}")
    compact_label = (f"Region · {short_label}" if explicit else f"Soma · {short_label}")
    resolution.update(status="selected", reason="unique exact region OBJ match",
                      match_kind=match_kind, normalized_query=query if normalized else None)
    return {**entry, "sha256": digest, "stat": stat, "manifest_entry": manifest_entry,
            "legend_label": legend_label, "compact_label": compact_label,
            "color": list(source["region_color"]),
            "coordinate_handling": "stored coordinates; no inferred transform, scale, or mirror"}, resolution, manifest_info


def plan_configured_view(sample_id: str, neuron_id: str, portal_region: str = "",
                         config_path: str | os.PathLike | None = None,
                         *, overrides: dict | None = None, snapshot: str | os.PathLike | None = None,
                         mesh_path: str | os.PathLike | None = None,
                         mesh_label: str | None = None,
                         region: str | None = None) -> dict:
    """Resolve one configured local mesh/SWC pair without importing GL libraries."""
    if not isinstance(sample_id, str) or not _IDENT.fullmatch(sample_id):
        raise ValueError("sample_id must contain only letters, digits, underscore or hyphen")
    if not isinstance(neuron_id, str) or not neuron_id.lower().endswith(".swc"):
        raise ValueError("neuron_id must be an SWC filename, including its .swc suffix")
    if ("/" in neuron_id or "\\" in neuron_id
            or Path(neuron_id).name != neuron_id or neuron_id in {".", ".."}):
        raise ValueError("neuron_id must be a filename, not a path")
    from ..config import load

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
    requested_mesh_label = mesh_label
    mesh_label = mesh_label if mesh_label is not None else source.get("mesh_label", "Brain mesh")
    if (not isinstance(mesh_label, str) or not mesh_label.strip() or
            len(mesh_label.strip()) > 18 or
            any(not 32 <= ord(character) <= 126 for character in mesh_label.strip())):
        raise ValueError("mesh_label must be 1-18 printable ASCII characters")
    if requested_mesh_label is not None and mesh_path is None:
        raise ValueError("mesh_label requires an explicit mesh_path")
    mesh = Path(mesh_path if mesh_path is not None else source["mesh_path"]).expanduser().resolve()
    if mesh.suffix.lower() != ".obj":
        raise ValueError("brain-view mesh must be an OBJ file")
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
    soma_root = _swc_root_coordinate(swc)
    region_mesh, region_resolution, region_manifest = _plan_region(source, region, portal_region)
    from ..config import resolve_settings, config_source
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
    candidates = (
        os.environ.get("VISPA_PYTHON"),
        os.environ.get("VISUAL_TOOLKIT_PYTHON"),
        config.get("visual_toolkit", {}).get("worker_python"),
        sys.executable,
        *DEFAULT_WORKER_CANDIDATES,
    )
    worker = None
    worker_entry = None
    worker_errors = []
    for candidate in candidates:
        if not candidate:
            continue
        resolved = Path(candidate).expanduser().resolve()
        if not resolved.is_file():
            continue
        try:
            entry = _worker_entry(str(resolved))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            worker_errors.append(f"{resolved}: {exc}")
            continue
        worker = str(resolved)
        worker_entry = entry
        break
    if worker is None:
        raise FileNotFoundError(
            "no usable VisPa worker Python was found; run the Conda environment "
            "or set VISPA_PYTHON to its python executable; " + "; ".join(worker_errors[-3:])
        )
    direction = settings["eye_direction"]
    norm = math.sqrt(sum(value * value for value in direction))
    direction = [value / norm for value in direction]
    distance = settings["camera_distance_scale"] * math.sqrt(3.0) * diagonal
    clipping = {"near": max(distance / 1000.0, 0.01),
                "far": max(distance * 3.0, diagonal * 2.0), "field_of_view_degrees": 45.0}
    from ..config import default_output_root
    session_dir = default_output_root(config) / "brain_view"
    session_receipt = session_dir / f"{sample_id}_{Path(neuron_id).stem}_{uuid.uuid4().hex[:12]}.json"
    return {
        "schema": SCHEMA, "command": "brain-view", "package_version": __version__,
        "sample_id": sample_id, "neuron_id": neuron_id,
        "portal_region": str(portal_region or ""),
        "mesh_label": mesh_label.strip(),
        "mesh": {"path": str(mesh), "sha256": mesh_before[1], "stat": mesh_before[0],
                 "bounds_source_xyz": {"center": center, "min": bounds_min, "max": bounds_max,
                                       "diagonal": diagonal}},
        "processed_swc": {"path": str(swc), "sha256": swc_before[1], "stat": swc_before[0],
                          "soma_root_stored_xyz": soma_root},
        "region_mesh": region_mesh, "region_resolution": region_resolution,
        "region_manifest": region_manifest,
        "coordinate_frame": frame.strip(), "coordinate_units": units.strip(),
        "coordinate_handling": "stored coordinates; no inferred transform, scale, or mirror",
        "visual_roles": {
            "soma": {"source": "processed SWC parent=-1 root",
                     "stored_xyz": soma_root, "radius": settings["soma_radius"],
                     "color": settings["soma_color"], "transform": "none"},
            "trace": {"color": settings["neuron_color"], "transform": "none"},
        },
        "camera": {"eye_direction_centered_xyz": direction, "center_centered_xyz": [0, 0, 0],
                   "up_centered_xyz": settings["up"], "distance": distance,
                   "distance_basis": "camera_distance_scale × sqrt(3) × root mesh source-bounds diagonal",
                   "clipping": clipping},
        "settings": settings, "worker_python": worker, "worker_entry": worker_entry,
        "config_path": str(config["path"]),
        "settings_config_path": settings_config_path,
        "session_receipt": str(session_receipt),
        "display_space": "legacy renderer recenters mesh and neuron together at the origin",
        "snapshot_png": str(snapshot_path) if snapshot_path else None,
        "receipt": str(receipt_path) if receipt_path else None,
        "dry_run": True,
    }


def _worker_entry(worker_python: str) -> list[str]:
    """Bind an isolated worker to this checkout, or verify its installed source."""
    checkout_entry = Path(__file__).resolve().parents[3] / "run_vispa.py"
    if checkout_entry.is_file():
        return [worker_python, "-I", str(checkout_entry)]
    probe_code = ("import json, vispa.renderers.swc_brain_view as m; "
                  "print(json.dumps([m.__version__, m.__file__]))")
    probe = subprocess.run([worker_python, "-I", "-c", probe_code],
                           capture_output=True, text=True, timeout=15,
                           stdin=subprocess.DEVNULL, shell=False)
    expected = [__version__, str(Path(__file__).resolve())]
    try:
        observed = json.loads((probe.stdout or "").strip())
    except ValueError:
        observed = None
    if probe.returncode != 0 or observed != expected:
        diagnostic = (probe.stderr or probe.stdout or "unknown worker package").strip()
        raise RuntimeError("configured worker Python does not resolve this VisPa candidate "
                           f"({diagnostic[-500:]}); choose a compatible worker")
    return [worker_python, "-I", "-m", "vispa"]


def launch_configured_view(sample_id: str, neuron_id: str, portal_region: str = "",
                           config_path: str | os.PathLike | None = None,
                           *, mesh_path: str | os.PathLike | None = None,
                           mesh_label: str | None = None,
                           region: str | None = None) -> subprocess.Popen:
    """Start the isolated legacy viewer for one configured local sample/neuron."""
    plan = plan_configured_view(sample_id, neuron_id, portal_region, config_path,
                                mesh_path=mesh_path, mesh_label=mesh_label, region=region)
    command = plan["worker_entry"] + ["brain-view",
               "--sample", sample_id, "--neuron", neuron_id]
    if portal_region:
        command.append(f"--portal-region={portal_region}")
    if (plan["region_mesh"] is not None and
            plan["region_resolution"]["source"] == "explicit"):
        command.append(f"--region={plan['region_mesh']['filename']}")
    command.extend(("--config", plan["config_path"]))
    if mesh_path is not None:
        command.extend((f"--mesh-path={plan['mesh']['path']}",
                        f"--mesh-label={plan['mesh_label']}"))
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
    process = subprocess.Popen(command, **kwargs)
    if hasattr(process, "__dict__"):
        process.vispa_plan = plan
    return process


def render_configured_snapshot(sample_id: str, neuron_id: str,
                               snapshot: str | os.PathLike,
                               portal_region: str = "",
                               config_path: str | os.PathLike | None = None,
                               *, mesh_path: str | os.PathLike | None = None,
                               mesh_label: str | None = None,
                               region: str | None = None,
                               overrides: dict | None = None) -> dict:
    """Render one static SWC Brain View through the isolated worker."""
    plan = plan_configured_view(
        sample_id, neuron_id, portal_region, config_path, snapshot=snapshot,
        mesh_path=mesh_path, mesh_label=mesh_label, region=region, overrides=overrides)
    command = plan["worker_entry"] + ["brain-view",
               "--sample", sample_id, "--neuron", neuron_id,
               "--snapshot", plan["snapshot_png"]]
    if portal_region:
        command.append(f"--portal-region={portal_region}")
    if (plan["region_mesh"] is not None and
            plan["region_resolution"]["source"] == "explicit"):
        command.append(f"--region={plan['region_mesh']['filename']}")
    command.extend(("--config", plan["config_path"]))
    if mesh_path is not None:
        command.extend((f"--mesh-path={plan['mesh']['path']}",
                        f"--mesh-label={plan['mesh_label']}"))
    command.extend(_settings_argv(plan["settings"]))
    env = {key: value for key, value in os.environ.items()
           if not (key.startswith("PYTHON") or key.startswith("CONDA")
                   or key.startswith("TCL_") or key.startswith("TK_")
                   or key.startswith("MPL") or key.startswith("MATPLOTLIB")
                   or key in {"PYOPENGL_PLATFORM", "QT_PLUGIN_PATH", "GLFW_LIBRARY",
                              "VISPA_PYTHON", "VISUAL_TOOLKIT_PYTHON"})}
    env["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=180, shell=False, env=env, cwd=tempfile.gettempdir(),
    )
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout or "no diagnostic").strip()
        raise RuntimeError(
            f"SWC Brain View worker exited with status {completed.returncode}: {diagnostic[-4000:]}")
    receipt = Path(plan["receipt"])
    image = Path(plan["snapshot_png"])
    if not image.is_file() or not receipt.is_file():
        raise RuntimeError("SWC Brain View worker did not create both the PNG and receipt")
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    if payload.get("status") != "rendered_candidate":
        raise RuntimeError(f"Unexpected SWC Brain View receipt status: {payload.get('status')!r}")
    if payload.get("output_png_sha256") != _sha256(image):
        raise RuntimeError("SWC Brain View snapshot hash does not match its receipt")
    return payload


def _settings_argv(settings: dict) -> list[str]:
    result = []
    for key, flag in (("eye_direction", "--eye-direction"), ("up", "--up"),
                      ("background", "--background"), ("mesh_color", "--mesh-color"),
                      ("neuron_color", "--neuron-color"), ("soma_color", "--soma-color"),
                      ("window_size", "--window-size")):
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
    parser.add_argument("--mesh-path", help="explicit local OBJ region/root mesh for this view")
    parser.add_argument("--mesh-label", help="legend role label for --mesh-path")
    parser.add_argument("--region", help="exact region OBJ filename, display name or acronym")
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
    parser.add_argument("--soma-color", nargs=3, type=float)
    parser.add_argument("--window-size", nargs=2, type=int)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override a brain-view setting; explicit matching flags take precedence")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        from ..config import parse_overrides
        overrides = parse_overrides(args.set)
        # Explicit legacy flags remain the final layer for backwards-compatible CLI precedence.
        for key in _SETTINGS_KEYS:
            value = getattr(args, key, None)
            if value is not None:
                overrides[key] = value
        plan = plan_configured_view(args.sample, args.neuron, args.portal_region,
                                    args.config, overrides=overrides, snapshot=args.snapshot,
                                    mesh_path=args.mesh_path, mesh_label=args.mesh_label,
                                    region=args.region)
        if args.dry_run:
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        return _run_view(plan)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        _parser().error(str(exc))


def _run_view(plan: dict) -> int:
    """Import the optional backend only after preflight succeeds."""
    try:
        from ..legacy_gl.GeometryAdapter import GeometryAdapter
        from ..legacy_gl.RenderGL import RenderGL
    except ImportError as exc:
        raise RuntimeError("legacy OpenGL dependencies are missing; install vispa[legacy-gl] in the configured worker") from exc

    mesh = Path(plan["mesh"]["path"])
    swc = Path(plan["processed_swc"]["path"])
    before = {"mesh": (_stat(mesh), _sha256(mesh)), "swc": (_stat(swc), _sha256(swc))}
    if plan["region_mesh"] is not None:
        region_path = Path(plan["region_mesh"]["path"])
        before["region"] = (_stat(region_path), _sha256(region_path))
    for label, actual in before.items():
        planned = plan[{"mesh": "mesh", "swc": "processed_swc", "region": "region_mesh"}[label]]
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
    if plan["region_mesh"] is not None:
        region_geometry = viewer.loadGeometry(plan["region_mesh"]["path"])
        region_geometry.name = plan["region_mesh"]["display_name"]
        viewer.addGeometry(region_geometry, color=plan["region_mesh"]["color"])
    adapter = GeometryAdapter(species="monkey")
    adapter.width = settings["line_width"]
    # GeometryAdapter owns both the SWC-root sphere and its child traces. Set
    # every role before parsing so the soma remains distinct without changing
    # axon/dendrite colors or coordinates.
    adapter.somaColor = settings["soma_color"]
    adapter.axonColor = settings["neuron_color"]
    adapter.dendriteColor = settings["neuron_color"]
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
    render_module = import_module("..legacy_gl.RenderGL", __package__)

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
        if plan["region_mesh"] is not None:
            region_path = Path(plan["region_mesh"]["path"])
            after["region"] = (_stat(region_path), _sha256(region_path))
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
    caption = f'{plan["sample_id"]} · {plan["neuron_id"]}'
    mesh_label = plan.get("mesh_label", "Brain mesh")
    region = plan.get("region_mesh")
    region_resolution = plan.get("region_resolution", {})
    unavailable = (not region and region_resolution.get("source") == "portal_region" and
                   bool(region_resolution.get("requested")))
    unavailable_label = "Soma region unavailable"
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    role_width = (42 + probe.textlength(mesh_label) + 28 + probe.textlength(TRACE_LABEL)
                  + 28 + probe.textlength("Soma") + 8)
    if region:
        role_width += 28 + probe.textlength(region["legend_label"])
    elif unavailable:
        role_width += 18 + probe.textlength(unavailable_label)
    width = int(min(int(plan["settings"]["window_size"][0]) - 24,
                    max(320, role_width + probe.textlength(caption) + 45)))
    light = sum(plan["settings"]["background"]) / 3 > .5
    surface = (235, 235, 235, 228) if light else (20, 20, 20, 228)
    ink = (20, 20, 20, 255) if light else (250, 250, 250, 255)
    compact = width < role_width
    height = 98 if (region or unavailable) and compact else (76 if compact else 52)
    image = Image.new("RGBA", (width, height), surface)
    draw = ImageDraw.Draw(image)
    mesh = tuple(round(value * 255) for value in plan["settings"]["mesh_color"])
    neuron = tuple(round(value * 255) for value in plan["settings"]["neuron_color"])
    soma = tuple(round(value * 255) for value in plan["settings"]["soma_color"])
    if compact:
        draw.rectangle((9, 8, 22, 21), fill=mesh + (255,), outline=ink)
        draw.text((29, 9), "Mesh", fill=ink)
        row = 30
        if region:
            region_color = tuple(round(value * 255) for value in region["color"])
            draw.rectangle((9, row, 22, row + 13), fill=region_color + (255,), outline=ink)
            draw.text((29, row + 1), region["compact_label"], fill=ink)
            row += 22
        elif unavailable:
            draw.text((9, row + 1), unavailable_label, fill=ink)
            row += 22
        draw.line((9, row + 7, 22, row + 7), fill=neuron + (255,), width=4)
        draw.text((29, row), "SWC", fill=ink)
        row += 22
        draw.ellipse((9, row, 22, row + 13), fill=soma + (255,), outline=ink)
        draw.text((29, row + 1), "Soma", fill=ink)
        return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    draw.rectangle((10, 17, 25, 33), fill=mesh + (255,), outline=ink)
    draw.text((32, 18), mesh_label, fill=ink)
    cursor = 42 + probe.textlength(mesh_label)
    if region:
        region_color = tuple(round(value * 255) for value in region["color"])
        draw.rectangle((cursor, 17, cursor + 15, 33), fill=region_color + (255,), outline=ink)
        draw.text((cursor + 22, 18), region["legend_label"], fill=ink)
        cursor += 32 + probe.textlength(region["legend_label"])
    elif unavailable:
        draw.text((cursor, 18), unavailable_label, fill=ink)
        cursor += 10 + probe.textlength(unavailable_label)
    draw.ellipse((cursor, 17, cursor + 15, 33), fill=soma + (255,), outline=ink)
    draw.text((cursor + 22, 18), "Soma", fill=ink)
    cursor += 32 + probe.textlength("Soma")
    draw.line((cursor, 25, cursor + 22, 25), fill=neuron + (255,), width=4)
    draw.text((cursor + 28, 18), TRACE_LABEL, fill=ink)
    cursor += 38 + probe.textlength(TRACE_LABEL)
    if cursor + probe.textlength(caption) + 8 < width:
        draw.text((cursor, 18), caption, fill=ink)
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
    legend_image = _legend_texture(plan)
    window_width, window_height = plan["settings"]["window_size"]
    left, right = -1 + 12 / window_width * 2, -1 + (12 + legend_image.width) / window_width * 2
    top, bottom = 1 - 12 / window_height * 2, 1 - (12 + legend_image.height) / window_height * 2
    vertices = np.asarray([
        left, top, 0, 1, left, bottom, 0, 0, right, bottom, 1, 0,
        left, top, 0, 1, right, bottom, 1, 0, right, top, 1, 1,
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
    pixels = np.asarray(legend_image, dtype=np.uint8)
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
            region_caption = ""
            if plan.get("region_mesh"):
                region_caption = (f'{plan["region_mesh"]["legend_label"]} '
                                  f'({color_label(plan["region_mesh"]["color"])}) | ')
            elif plan.get("region_resolution", {}).get("requested"):
                region_caption = "Soma region unavailable | "
            glfw.set_window_title(viewer.window,
                                  f'{plan.get("mesh_label", "Brain mesh")} ({color_label(plan["settings"]["mesh_color"])}) | '
                                  f'{region_caption}'
                                  f'{TRACE_LABEL} ({color_label(plan["settings"]["neuron_color"])}) | '
                                  f'{plan["sample_id"]} {plan["neuron_id"]} | '
                                  f'{plan["coordinate_frame"]} ({plan["coordinate_units"]}; as stored)')
    except Exception:
        pass


def _write_session_receipt(viewer, plan: dict) -> None:
    """Persist the initial interactive request; later camera gestures are not logged."""
    from importlib import import_module
    render_module = import_module("..legacy_gl.RenderGL", __package__)
    mesh, swc = Path(plan["mesh"]["path"]), Path(plan["processed_swc"]["path"])
    current = {"mesh": (_stat(mesh), _sha256(mesh)), "swc": (_stat(swc), _sha256(swc))}
    if plan["region_mesh"] is not None:
        region_path = Path(plan["region_mesh"]["path"])
        current["region"] = (_stat(region_path), _sha256(region_path))
    for label, value in current.items():
        entry = plan[{"mesh": "mesh", "swc": "processed_swc", "region": "region_mesh"}[label]]
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
