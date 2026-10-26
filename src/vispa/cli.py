"""Bounded command line for one local VisPa review render or montage.

Version: 1.11.0.dev18 (local/unreleased)
Last updated: 2026-10-26
Change history: CHANGELOG.md
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

from ._version import __version__ as VERSION


def _triple(values, name):
    import math
    result = tuple(float(value) for value in values)
    if len(result) != 3 or not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain three finite numbers")
    return result


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stat(path):
    stat = Path(path).stat()
    return {"size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _atomic_json(path, payload):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, default=str)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_volume(path):
    if Path(path).suffix.lower() != ".npy":
        raise ValueError("--input must be a local .npy array in ZYX (or YX) order")
    if Path(path).stat().st_size > 256 * 1024 * 1024:
        raise ValueError("input exceeds the 256 MiB bounded-render limit")
    import numpy as np
    volume = np.load(path, allow_pickle=False)
    if volume.ndim == 2:
        volume = volume[np.newaxis, ...]
    if (volume.ndim != 3 or not volume.size or volume.size > 16_000_000
            or not np.issubdtype(volume.dtype, np.number)
            or not np.isfinite(volume).all()):
        raise ValueError("input must be a finite numeric YX or ZYX array of at most 16M voxels")
    return volume


def _apply_render_settings(tk, tool, resolved):
    """Refresh cached toolkit constants so the receipt describes the actual render."""
    tk.REVIEW_SETTINGS = resolved
    tk.TARGET_MARKER_COLOR = resolved["marker"]["color"]
    tk.WIDEFIELD_DEFAULT_PARAMETERS = (resolved["widefield"]["gain"],
                                       resolved["widefield"]["threshold"])
    tk.SCALE_BAR_CANDIDATES_UM = resolved["scale_bar_candidates_um"]
    tool.PANEL_FIGSIZE = resolved["figure"]["panel_figsize"]
    tool.PANEL_DPI = resolved["figure"]["panel_dpi"]
    tool.TRIO_FIGSIZE = resolved["figure"]["review_figsize"]
    tool.TRIO_DPI = resolved["figure"]["review_dpi"]


def _reserve(path):
    """Create an exclusive placeholder so a concurrent render cannot overwrite."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)


def _render(args):
    if not args.dry_run:
        import matplotlib
        matplotlib.use("Agg")
    if args.config:
        os.environ["VISPA_CONFIG"] = str(Path(args.config).expanduser().resolve())
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"input does not exist: {input_path}")
    sample, neuron = str(args.sample), str(args.neuron)
    if not sample or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in sample):
        raise ValueError("--sample must be a simple identifier")
    if not neuron or Path(neuron).name != neuron or neuron in {".", ".."}:
        raise ValueError("--neuron must be a name, not a path")
    soma, origin, resolution = (_triple(args.soma, "--soma"),
                                _triple(args.origin, "--origin"),
                                _triple(args.resolution, "--resolution"))
    if any(value <= 0 for value in resolution):
        raise ValueError("--resolution values must be positive")
    from . import toolkit as tk
    from .settings import apply_settings, config_source
    from .dataset_config import default_output_root, load
    config = load(args.config)
    base_settings = copy.deepcopy(tk.REVIEW_SETTINGS)
    resolved_settings = copy.deepcopy(base_settings)
    changed = apply_settings("review", args.set, settings=resolved_settings, config=config)
    settings_config_path = (config_source(config) if
                           config.get("visual_toolkit", {}).get("settings", {}).get("review") else None)
    output_dir = (Path(args.output_dir).expanduser().resolve() if args.output_dir
                  else default_output_root(config) / sample)
    output_path = output_dir / f"{sample}_{neuron}_{args.role}.png"
    receipt_path = output_path.with_suffix(".json")
    before_stat = _stat(input_path)
    plan = {
        "schema": "visual-toolkit.render.v1", "version": VERSION,
        "package_version": VERSION, "python_executable": sys.executable,
        "runtime": {
            "python_executable": sys.executable,
            "python_prefix": sys.prefix,
            "backend_module": str(Path(tk.__file__).resolve()),
        },
        "command": "render", "sample_id": sample,
        "config_path": str(config["path"]),
        "neuron_id": neuron, "role": args.role, "input": str(input_path),
        "input_order": "ZYX; a 2D YX array is treated as one Z plane",
        "output_png": str(output_path), "receipt": str(receipt_path),
        "soma_xyz_um": list(soma), "origin_xyz_um": list(origin),
        "resolution_xyz_um": list(resolution), "coordinate_frame": args.coordinate_frame,
        "coordinate_units": "micrometre", "settings_overrides": changed,
        "review_settings": resolved_settings, "settings_config_path": settings_config_path,
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        if output_path.exists() or receipt_path.exists():
            raise FileExistsError("planned output PNG or receipt already exists; choose another output directory")
        print(json.dumps(plan, indent=2, sort_keys=True, default=str))
        return 0
    before_hash = _sha256(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_path.exists() or receipt_path.exists():
        raise FileExistsError("output PNG or receipt already exists; choose another output directory")
    reserved_paths = []
    original_review_settings_ref = tk.REVIEW_SETTINGS
    original_review_settings = copy.deepcopy(original_review_settings_ref)
    original_globals = (tk.TARGET_MARKER_COLOR, tk.WIDEFIELD_DEFAULT_PARAMETERS, tk.SCALE_BAR_CANDIDATES_UM,
                        tk.VisPa.PANEL_FIGSIZE, tk.VisPa.PANEL_DPI,
                        tk.VisPa.TRIO_FIGSIZE, tk.VisPa.TRIO_DPI)
    try:
        _reserve(output_path)
        reserved_paths.append(output_path)
        _reserve(receipt_path)
        reserved_paths.append(receipt_path)
    except FileExistsError:
        for reserved in reserved_paths:
            reserved.unlink(missing_ok=True)
        raise FileExistsError("output PNG or receipt already exists; choose another output directory")

    try:
        volume = _load_volume(input_path)
        coords = tuple((soma[i] - origin[i]) / resolution[i] for i in range(3))
        if any(value < 0 or value >= volume.shape[2 - i] for i, value in enumerate(coords)):
            raise ValueError("--soma falls outside the input array bounds for the supplied origin/resolution")
        tk.configure_data_sources(args.config, config)
        with tempfile.TemporaryDirectory(prefix="visual_toolkit_render_", dir=output_dir) as temp_dir:
            tool = tk.VisPa(sample, cache_dir=temp_dir)
            _apply_render_settings(tk, tool, resolved_settings)
            if args.role == "soma":
                panel = tool.plot_soma_block(volume, origin, resolution, soma, neuron,
                                             output_dir=temp_dir)
                source_label = "local NPY input · grayscale ZYX MIP"
            else:
                panel = tool.plot_widefield_context(volume, origin, resolution, soma, neuron,
                                                    output_dir=temp_dir)
                source_label = "local NPY input · threshold composite of ZYX MIP"
            marker_label = "target soma marker (box + cross, not to scale)"
            panel["role"] = args.role.title()
            panel["title"] = (f"{sample} | {neuron} | {args.role.title()} local array | "
                              f"{input_path.name} | frame: {args.coordinate_frame}")
            panel["legend"] = ([] if args.role == "soma" else [
                ("patch", "green", source_label),
                ("marker", tk.TARGET_MARKER_COLOR, marker_label),
            ])
            panel["notes"] = [f"Input shape ZYX: {tuple(volume.shape)}; "
                              f"spacing XYZ µm: {tuple(resolution)}."]
            panel["axis_labels"] = (
                None if args.role == "soma"
                else ("X pixel index (column)", "Y pixel index (row)"))
            rendered = Path(tool.plot_tri_plot([panel], neuron, output_dir=temp_dir,
                                               suffix=args.role, legend=False))
            tool.close()
            if not rendered.is_file():
                raise RuntimeError("renderer did not produce the expected PNG")
            os.replace(rendered, output_path)
        after_stat = _stat(input_path)
        after_hash = _sha256(input_path)
        if before_stat != after_stat or before_hash != after_hash:
            raise RuntimeError("input changed while rendering; output was discarded")
        receipt = {
            **plan, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_sha256": before_hash, "input_stat_before": before_stat,
            "input_stat_after": after_stat, "input_shape_zyx": list(volume.shape),
            "input_dtype": str(volume.dtype), "output_sha256": _sha256(output_path),
            "runtime": {
                **plan["runtime"],
                "backend_sha256": _sha256(Path(tk.__file__).resolve()),
            },
            "render_labels": {
                "panel_title": panel["title"],
                "legend_header_role": panel["role"],
                "x_axis": (panel["axis_labels"][0]
                           if panel["axis_labels"] is not None else None),
                "y_axis": (panel["axis_labels"][1]
                           if panel["axis_labels"] is not None else None),
                "legend": panel["legend"],
            },
            "status": "rendered_candidate",
        }
        _atomic_json(receipt_path, receipt)
    except Exception:
        for reserved in reserved_paths:
            try:
                reserved.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        original_review_settings_ref.clear()
        original_review_settings_ref.update(original_review_settings)
        tk.REVIEW_SETTINGS = original_review_settings_ref
        (tk.TARGET_MARKER_COLOR,
         tk.WIDEFIELD_DEFAULT_PARAMETERS, tk.SCALE_BAR_CANDIDATES_UM,
         tk.VisPa.PANEL_FIGSIZE, tk.VisPa.PANEL_DPI,
         tk.VisPa.TRIO_FIGSIZE, tk.VisPa.TRIO_DPI) = original_globals
    print(json.dumps({"output_png": str(output_path), "receipt": str(receipt_path)}, indent=2))
    return 0


def _montage_settings(values, config=None):
    from .settings import resolve_settings

    return resolve_settings("montage", values, config=config)


def _montage(args):
    from .dataset_config import load
    from .settings import config_source
    from .volume_montage import (
        VIEW_KEYS,
        VIEW_TITLES,
        anatomical_axes,
        render_volume,
        save_single_volume_montage,
        view_axis_labels,
    )

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    receipt_path = output_path.with_suffix(".json")
    if not input_path.is_file():
        raise FileNotFoundError(f"input does not exist: {input_path}")
    if input_path == output_path or input_path == receipt_path:
        raise ValueError("output paths must not overwrite the input NIfTI")
    if output_path.suffix.lower() != ".png":
        raise ValueError("--output must name a .png file")
    if input_path.suffix.lower() not in {".nii", ".gz"} or (input_path.suffix.lower() == ".gz" and not input_path.name.lower().endswith(".nii.gz")):
        raise ValueError("--input must be a local .nii or .nii.gz file")
    config = load(args.config)
    settings = _montage_settings(args.set, config=config)
    settings_config_path = (config_source(config) if
                           config.get("visual_toolkit", {}).get("settings", {}).get("montage") else None)
    if isinstance(args.max_voxels, bool) or args.max_voxels < 1:
        raise ValueError("--max-voxels must be a positive integer")
    before_stat = _stat(input_path)
    before_hash = _sha256(input_path)
    try:
        import nibabel as nib
    except ImportError as exc:
        raise RuntimeError("montage requires the 'montage' optional dependencies: nibabel and scipy") from exc
    image = nib.load(str(input_path))
    shape = tuple(int(value) for value in image.shape)
    if len(shape) != 3 or any(value < 1 for value in shape):
        raise ValueError(f"montage input must be a nonempty 3D NIfTI image, got shape {shape}")
    voxel_count = 1
    for size in shape:
        voxel_count *= size
    if voxel_count > args.max_voxels:
        raise ValueError(f"input has {voxel_count:,} voxels; limit is {args.max_voxels:,} (--max-voxels)")
    affine = image.affine.copy()
    anatomical_axes(affine)
    voxel_axis_codes = list(nib.aff2axcodes(affine))
    sform_code = int(image.header["sform_code"])
    qform_code = int(image.header["qform_code"])
    spatial_units, temporal_units = image.header.get_xyzt_units()
    spatial_units = spatial_units or "unknown"
    if spatial_units not in {"mm", "unknown"}:
        raise ValueError(
            f"NIfTI header units are {spatial_units!r}; montage affine is interpreted in millimetres. "
            "Convert the source explicitly to millimetres before rendering."
        )
    if args.units != "mm":
        raise ValueError("--units must be mm; this renderer preserves the source affine without unit conversion")
    del image
    if args.dry_run:
        if output_path.exists() or receipt_path.exists():
            raise FileExistsError("planned PNG or receipt already exists; choose another output path")
        plan = {
            "schema": "visual-toolkit.montage.v1",
            "status": "planned_candidate",
            "version": VERSION,
            "command": "montage",
            "config_path": str(config["path"]),
            "input": str(input_path),
            "input_sha256": before_hash,
            "input_stat": before_stat,
            "shape_ijk": list(shape),
            "affine_ijk_to_world": affine.tolist(),
            "voxel_axis_codes": voxel_axis_codes,
            "world_axis_convention": "RAS+",
            "sform_code": sform_code,
            "qform_code": qform_code,
            "reference_identity": "unknown; not inferred by this command",
            "spatial_units": spatial_units,
            "temporal_units": temporal_units,
            "coordinate_frame": "NIfTI voxel order LPS; world coordinates RAS+; no additional transform",
            "declared_coordinate_units": args.units,
            "output_png": str(output_path),
            "receipt": str(receipt_path),
            "settings": settings,
            "settings_config_path": settings_config_path,
            "max_voxels": args.max_voxels,
            "dry_run": True,
            "runtime": {"python_executable": sys.executable, "python_prefix": sys.prefix},
        }
        if before_stat != _stat(input_path) or before_hash != _sha256(input_path):
            raise RuntimeError("input changed while preparing montage plan")
        print(json.dumps(plan, indent=2, sort_keys=True, default=str))
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    reserved = []
    try:
        _reserve(output_path)
        reserved.append(output_path)
        _reserve(receipt_path)
        reserved.append(receipt_path)
    except FileExistsError as exc:
        for path in reserved:
            path.unlink(missing_ok=True)
        raise FileExistsError("output PNG or receipt already exists; choose another output path") from exc

    try:
        result = render_volume(input_path, settings=settings)
        with tempfile.TemporaryDirectory(prefix="visual_toolkit_montage_", dir=output_path.parent) as folder:
            temp_png = Path(folder) / output_path.name
            save_single_volume_montage(
                result["frames"], result["extents_mm"], temp_png,
                f"{input_path.name} | DS00 five-view candidate | voxel order LPS; world RAS+",
                affine=affine,
                settings=settings,
            )
            if not temp_png.is_file():
                raise RuntimeError("montage renderer did not produce a PNG")
            after_stat = _stat(input_path)
            after_hash = _sha256(input_path)
            if before_stat != after_stat or before_hash != after_hash:
                raise RuntimeError("input changed while rendering; output was discarded")
            os.replace(temp_png, output_path)
        receipt = {
            "schema": "visual-toolkit.montage.v1",
            "status": "rendered_candidate",
            "version": VERSION,
            "command": "montage",
            "config_path": str(config["path"]),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input": str(input_path),
            "input_sha256": before_hash,
            "input_stat_before": before_stat,
            "input_stat_after": after_stat,
            "shape_ijk": list(shape),
            "affine_ijk_to_world": affine.tolist(),
            "voxel_axis_codes": voxel_axis_codes,
            "world_axis_convention": "RAS+",
            "sform_code": sform_code,
            "qform_code": qform_code,
            "reference_identity": "unknown; not inferred by this command",
            "spatial_units": result["spatial_units"],
            "temporal_units": result["temporal_units"],
            "coordinate_frame": "NIfTI voxel order LPS; world coordinates RAS+; no additional transform",
            "declared_coordinate_units": args.units,
            "threshold": result["threshold"],
            "high_intensity": result["high"],
            "downsampled_shape_ijk": result["downsampled_shape"],
            "settings": result["settings"],
            "settings_config_path": settings_config_path,
            "max_voxels": args.max_voxels,
            "views": [
                {"key": key, "title": title, "projected_extent_ras_world_mm": extent,
                 "axis_labels": list(view_axis_labels(affine, key))}
                for key, title, extent in zip(VIEW_KEYS, VIEW_TITLES, result["extents_mm"])
            ],
            "output_png": str(output_path),
            "output_sha256": _sha256(output_path),
            "runtime": {
                "python_executable": sys.executable,
                "python_prefix": sys.prefix,
                "volume_montage_module": str(Path(sys.modules["vispa.volume_montage"].__file__).resolve()),
                "volume_montage_sha256": _sha256(Path(sys.modules["vispa.volume_montage"].__file__).resolve()),
            },
        }
        _atomic_json(receipt_path, receipt)
    except Exception:
        for path in reserved:
            path.unlink(missing_ok=True)
        raise
    print(json.dumps({"output_png": str(output_path), "receipt": str(receipt_path)}, indent=2))
    return 0


def fnt_plan(config, sample, neuron):
    """Resolve an exact FNT project without starting an external application."""
    if not sample or not neuron or any(Path(str(v)).name != str(v) or str(v) in {".", ".."}
                                       for v in (sample, neuron)):
        raise ValueError("sample and neuron must be simple identifiers")
    settings = config.get("visual_toolkit", {}).get("fnt_tracer", {})
    executable = settings.get("executable")
    root = settings.get("project_root")
    stem = f"{sample}_{str(neuron).removesuffix('.swc')}"
    candidates = [Path(root) / f"{stem}{suffix}" for suffix in (".fnt", ".decimate.fnt")] if root else []
    project = next((path for path in candidates if path.is_file()), None)
    from .fnt import resolve_fnt_plan
    try:
        native = resolve_fnt_plan(config, sample, neuron)
    except ValueError:
        if project is None:
            raise
        native = None
    if project is None:
        cached = Path(native["source_path"])
        bound = Path(native["bound_path"])
        project = next((p for p in (bound, cached) if p.is_file()), None)
    executable_ready = bool(executable and Path(executable).is_file())
    errors = []
    if not executable_ready:
        errors.append("Configure an existing visual_toolkit.fnt_tracer.executable to launch")
    if project is None:
        errors.append(f"Matching project missing; use fnt-fetch for {sample} {neuron}")
    command = [str(executable), str(project)] if executable_ready and project else None
    return {"sample": sample, "neuron": neuron, "executable": str(executable) if executable else None,
            "project": str(project) if project else None, "searched": [str(p) for p in candidates],
            "native_plan": native, "command": command, "errors": errors,
            "project_ready": project is not None, "executable_ready": executable_ready,
            "ready": bool(project and executable_ready),
            "version": None, "version_note": "Binary is not executed during preflight"}


def _fnt_fetch(args):
    from .dataset_config import load
    from .fnt import ensure_fnt
    config = load(args.config)
    result = ensure_fnt(config, args.sample, args.neuron, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"planned", "downloaded", "cached"} else 1


def _resource_check(args):
    from .dataset_config import load
    config = load(args.config)
    if not args.sample or not args.neuron:
        raise ValueError("--sample and --neuron are required together for single-case inventory")
    plan = fnt_plan(config, args.sample, args.neuron)
    records = []
    def record(role, value, space=None):
        path = Path(value) if value else None
        item = {"role": role, "path": str(path) if path else None, "source_date": None,
                "space": space, "exists": None, "sha256": None}
        try:
            item['exists'] = bool(path and path.exists())
            if path and path.is_file():
                item.update(size_bytes=path.stat().st_size, sha256=_sha256(path))
        except OSError as exc:
            item['status'] = 'unverified_access_denied'
            item['error'] = str(exc)
        records.append(item)
    record("config", config["path"])
    record("fnt_executable", plan["executable"])
    record("fnt_project", plan["project"])
    sources = config.get("sources", {})
    brain = sources.get("brain_view", {})
    frame = brain.get("coordinate_frame")
    record("brain_mesh", brain.get("mesh_path"), frame)
    root = brain.get("processed_swc_root")
    record("processed_swc", Path(root) / args.sample / (str(args.neuron).removesuffix('.swc') + '.swc') if root else None, frame)
    raw_root = sources.get("legacy_raw_swc_root")
    record("raw_swc", Path(raw_root) / args.sample / (str(args.neuron).removesuffix('.swc') + '.swc') if raw_root else None, "source native; axes unaccepted")
    sample = config.get("samples", {}).get(args.sample, {})
    for key in ("ds00_processed", "resample_5um", "swc_cache"):
        record(key, sample.get(key), "native source; see configured geometry")
    defaults = config.get('defaults', {})
    cache = defaults.get('cache_root')
    record('high_res_cache', Path(cache) / args.sample / 'high_res_http' if cache else None, 'source native')
    from .toolkit import BLOCK_SIZE_PIXELS, RESOLUTION_HIGH
    host = sources.get('http_base_url') or sources.get('http_host')
    prefix = str(sources.get('http_path') or '').strip('/')
    route = f"{str(host).rstrip('/')}/{prefix + '/' if prefix else ''}{args.sample}/cube/{{z}}/{{x}}_{{y}}_{{z}}.tif" if host else None
    result = {"cube_source": {"host": host, "http_path": prefix, "route": route},
              "cube_geometry": {"size_xyz_pixels": BLOCK_SIZE_PIXELS, "spacing_xyz_um": RESOLUTION_HIGH, "acceptance": "configured math only; source axes unaccepted"},
              "schema": "visual-toolkit.resources.v1", "dry_run": True,
              "config": str(config["path"]), "sample": args.sample, "neuron": args.neuron,
              "resources": records, "fnt": plan,
              "limits": "Read-only inventory; directories are references, not recursively hashed. No offline/full-panel acceptance."}
    print(json.dumps(result, indent=2))
    return 0 if not args.fnt or plan["ready"] else 1


def _catalog_check(args):
    from .dataset_config import load
    from .sources import catalog_request_url, list_neurons

    if not args.sample:
        raise ValueError("config-check --catalog requires --sample with one exact sample ID")
    config = load(args.config)
    catalog = (config.get("sources") or {}).get("neuron_catalog")
    if not isinstance(catalog, dict):
        raise ValueError("no sources.neuron_catalog configuration is configured")
    selected = args.catalog_source or catalog.get("mode", "csv")
    if selected not in {"csv", "live-iondata"}:
        raise ValueError("catalog source must be 'csv' or 'live-iondata'")
    if selected == "live-iondata":
        request_url = catalog_request_url(args.sample, catalog)
        snapshot_path = catalog.get("snapshot_path")
    else:
        configured_path = (catalog.get("snapshot_path") if catalog.get("mode") == "live-iondata"
                           else catalog.get("path"))
        request_url = None
        snapshot_path = str(configured_path) if configured_path else None
    plan = {"schema": "vispa.neuron-catalog-check.v1", "dry_run": bool(args.dry_run),
            "sample_id": args.sample, "source_kind": selected,
            "request_url": request_url,
            "timeout_seconds": catalog.get("timeout_seconds", 10) if selected == "live-iondata" else None,
            "max_response_bytes": catalog.get("max_response_bytes", 8 * 1024 * 1024) if selected == "live-iondata" else None,
            "snapshot_path": str(snapshot_path) if snapshot_path else None,
            "limits": "one exact sample; no retries, cache writes, or directory creation"}
    if args.dry_run:
        plan["plan"] = "Resolve live URL and limits without a network request" if selected == "live-iondata" else "Resolve dated CSV snapshot without reading its rows"
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    result = list_neurons(args.sample, config=config, source=selected)
    plan.update(result=result)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def _data_check(args):
    from .readiness import data_check

    report = data_check(
        config=args.config,
        sample_id=args.sample,
        neuron_id=args.neuron,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(f"VisPa data check - {report['sample_id']}/{report['neuron_id']}")
        print("\n".join(report["checklist"]))
        print()
        print(report["summary"])
    return 0 if report["ready"] else 1


def _parser():
    parser = argparse.ArgumentParser(prog="vispa", description=f"VisPa {VERSION} command line")
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="open the VisPa review GUI")
    example = commands.add_parser(
        "example", help="download and preview one public neuron morphology",
        description=f"VisPa {VERSION}: render one public macaque SWC morphology only; no atlas or image context")
    example.add_argument("--dry-run", action="store_true",
                         help="show the bounded single-neuron plan without network or file access")
    example.add_argument("--output-dir", help="new PNG and provenance receipt directory")
    example.add_argument("--cache-dir", help="per-user cache directory for the immutable source SWC")
    example.add_argument("--config", help="VisPa profile containing the public example source and SHA-256")
    example.add_argument("--dpi", type=int, default=160,
                         help="figure resolution, integer 100-240 (default: 160)")
    render = commands.add_parser("render", help="render one local array as a review panel")
    render.add_argument("--input", required=True, help="local .npy array in ZYX (or YX) order")
    render.add_argument("--sample", required=True)
    render.add_argument("--neuron", required=True)
    render.add_argument("--soma", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    render.add_argument("--origin", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    render.add_argument("--resolution", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    render.add_argument("--role", choices=("soma", "context"), default="soma")
    render.add_argument("--coordinate-frame", required=True,
                        help="name of the XYZ physical frame represented by origin/resolution")
    render.add_argument("--output-dir")
    render.add_argument("--config")
    render.add_argument("--set", action="append", default=[], metavar="PATH=VALUE")
    render.add_argument("--dry-run", action="store_true")
    montage = commands.add_parser("montage", help="render one local LPS NIfTI volume as a five-view montage")
    montage.add_argument("--input", required=True, help="one local 3D NIfTI image (.nii or .nii.gz), validated as LPS voxel axis codes")
    montage.add_argument("--output", required=True, help="new PNG path; adjacent JSON receipt uses the same stem")
    montage.add_argument("--config", help="optional VisPa JSON/YAML settings config")
    montage.add_argument("--units", choices=("mm",), required=True,
                         help="explicitly declare affine values in millimetres; non-mm header units are rejected")
    montage.add_argument("--max-voxels", type=int, default=64_000_000,
                         help="maximum input voxels for this bounded one-volume operation (default: 64000000)")
    montage.add_argument("--set", action="append", default=[], metavar="KEY=JSON_VALUE",
                         help="override a display setting, repeatable; values use JSON syntax")
    montage.add_argument("--dry-run", action="store_true",
                         help="resolve input header, settings and outputs without reading image pixels or writing files")
    commands.add_parser("brain-view", help="open one configured local processed neuron on the local brain mesh")
    settings = commands.add_parser("settings", help="list validated setting defaults, current values, ranges and effects as JSON")
    settings.add_argument("--scope", choices=("review", "brain-view", "montage", "all"),
                          default="review", help="setting group to print (default: review)")
    settings.add_argument("--config", help="optional VisPa JSON/YAML settings config")
    config_check = commands.add_parser("config-check", help="validate configuration or check configured source paths")
    config_check.add_argument("--config")
    config_check.add_argument("--validate-only", action="store_true",
                              help="validate config syntax and declarations without probing source paths")
    config_check.add_argument("--sample", help="exact sample for read-only hashed resource inventory")
    config_check.add_argument("--neuron", help="exact neuron for read-only hashed resource inventory")
    config_check.add_argument("--catalog", action="store_true",
                              help="read or plan one neuron-catalog listing; use --sample")
    config_check.add_argument("--catalog-source", choices=("live-iondata", "csv"),
                              help="select live portal or dated CSV snapshot when both are configured")
    config_check.add_argument("--dry-run", action="store_true", help="read-only preflight (config-check never writes)")
    config_check.add_argument("--fnt", action="store_true", help="require executable AND matching neuron project; never launch")
    data_check = commands.add_parser(
        "check", aliases=["data-check"],
        help="check configured dataset, cache, dependency, brain-view and FNT readiness")
    data_check.add_argument("--config", help="VisPa JSON/YAML settings config")
    data_check.add_argument("--sample", help="exact sample ID; defaults to the configured startup sample")
    data_check.add_argument("--neuron", help="exact neuron ID; defaults to the configured startup neuron")
    data_check.add_argument("--json", action="store_true", help="emit the complete machine-readable report")
    fnt_fetch = commands.add_parser("fnt-fetch", help="fetch one exact native FNT into the verified per-user cache")
    fnt_fetch.add_argument("--config", help="VisPa JSON/YAML settings config")
    fnt_fetch.add_argument("--sample", required=True, help="one exact SampleID")
    fnt_fetch.add_argument("--neuron", required=True, help="one three-digit neuron ID, optionally .swc")
    fnt_fetch.add_argument("--dry-run", action="store_true", help="show URL and cache paths without network or writes")
    config_init = commands.add_parser("config-init", help="create the per-user YAML config without overwriting")
    config_init.add_argument("--output", help="explicit YAML destination; defaults to the per-user config path")
    config_init.add_argument("--from-config", help="explicitly copy an existing JSON/YAML config into the selected VisPa target")
    config_init.add_argument("--dry-run", action="store_true", help="show source/destination hashes and action without writing")
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "gui":
        from .gui import main as gui_main
        return gui_main(argv[1:])
    if argv and argv[0] == "brain-view":
        from .opengl import main as brain_view_main
        return brain_view_main(argv[1:])
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "render":
        try:
            return _render(args)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    if args.command == "example":
        try:
            from .public_example import run as run_public_example
            print(json.dumps(run_public_example(output_dir=args.output_dir,
                                                cache_dir=args.cache_dir,
                                                dpi=args.dpi,
                                                dry_run=args.dry_run, config=args.config),
                             indent=2, sort_keys=True))
            return 0
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    if args.command == "montage":
        try:
            return _montage(args)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    if args.command == "settings":
        try:
            from .settings import settings_schema
            print(json.dumps(settings_schema(args.scope, config=args.config), indent=2, sort_keys=True))
            return 0
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    if args.command == "config-check":
        if args.validate_only:
            if args.catalog or args.catalog_source or args.sample or args.neuron or args.fnt:
                parser.error("--validate-only cannot be combined with catalog or resource checks")
            try:
                from .dataset_config import load
                if args.config and not Path(args.config).expanduser().is_file():
                    raise ValueError(f"config file does not exist: {args.config}")
                config = load(args.config)
                print(json.dumps({"config": str(config["path"]), "valid": True,
                                  "samples": len(config["samples"])}, indent=2))
                return 0
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                parser.error(str(exc))
        if args.catalog:
            try:
                return _catalog_check(args)
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                parser.error(str(exc))
        if args.sample or args.neuron or args.fnt:
            try:
                return _resource_check(args)
            except (OSError, ValueError, KeyError) as exc:
                parser.error(str(exc))
        from .dataset_config import main as config_main
        check_argv = ["--check"]
        if args.config:
            check_argv.extend(("--config", args.config))
        return config_main(check_argv)
    if args.command in {"check", "data-check"}:
        try:
            return _data_check(args)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            parser.error(str(exc))
    if args.command == "fnt-fetch":
        try:
            return _fnt_fetch(args)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    if args.command == "config-init":
        try:
            from .dataset_config import initialize_default_config
            plan = initialize_default_config(
                output=args.output, from_path=args.from_config, dry_run=args.dry_run)
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    parser.print_help()
    return 0
