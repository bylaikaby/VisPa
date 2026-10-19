"""Bounded command line for one local VisualToolkit review render or montage.

Version: 1.11.0.dev0 (local/unreleased)
Last updated: 2026-10-19
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
        os.environ["VISUAL_TOOLKIT_CONFIG"] = str(Path(args.config).expanduser().resolve())
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
                        tk.Visual_toolkit.PANEL_FIGSIZE, tk.Visual_toolkit.PANEL_DPI,
                        tk.Visual_toolkit.TRIO_FIGSIZE, tk.Visual_toolkit.TRIO_DPI)
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
            tool = tk.Visual_toolkit(sample, cache_dir=temp_dir)
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
            panel["legend"] = [
                ("patch", "gray" if args.role == "soma" else "green", source_label),
                ("marker", tk.TARGET_MARKER_COLOR, marker_label),
            ]
            panel["notes"] = [f"Input shape ZYX: {tuple(volume.shape)}; "
                              f"spacing XYZ µm: {tuple(resolution)}."]
            panel["axis_labels"] = ("X pixel index (column)", "Y pixel index (row)")
            rendered = Path(tool.plot_tri_plot([panel], neuron, output_dir=temp_dir,
                                               suffix=args.role, legend=True))
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
                "x_axis": panel["axis_labels"][0],
                "y_axis": panel["axis_labels"][1],
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
         tk.Visual_toolkit.PANEL_FIGSIZE, tk.Visual_toolkit.PANEL_DPI,
         tk.Visual_toolkit.TRIO_FIGSIZE, tk.Visual_toolkit.TRIO_DPI) = original_globals
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
                "volume_montage_module": str(Path(sys.modules["Visual_toolkit.volume_montage"].__file__).resolve()),
                "volume_montage_sha256": _sha256(Path(sys.modules["Visual_toolkit.volume_montage"].__file__).resolve()),
            },
        }
        _atomic_json(receipt_path, receipt)
    except Exception:
        for path in reserved:
            path.unlink(missing_ok=True)
        raise
    print(json.dumps({"output_png": str(output_path), "receipt": str(receipt_path)}, indent=2))
    return 0


def _path_parts(value):
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _same_path(left, right):
    def normalized(value):
        return os.path.normcase(
            os.path.normpath(os.path.expandvars(str(value).strip())))
    return normalized(left) == normalized(right)


def merge_user_path(current, entry):
    """Return (new_path, changed) with one idempotent user-PATH entry."""
    parts = _path_parts(current)
    if any(_same_path(part, entry) for part in parts):
        return current, False
    return ";".join(parts + [str(entry)]), True


def remove_user_path(current, entry):
    """Return (new_path, changed) after removing one user-PATH entry."""
    parts = _path_parts(current)
    kept = [part for part in parts if not _same_path(part, entry)]
    return ";".join(kept), len(kept) != len(parts)


def _read_user_path():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_READ) as key:
            value, kind = winreg.QueryValueEx(key, "Path")
        return str(value), kind
    except FileNotFoundError:
        return "", winreg.REG_EXPAND_SZ


def _write_user_path(value, kind):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, kind or winreg.REG_EXPAND_SZ, value)


def _set_user_env(name, value):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _broadcast_environment_change():
    import ctypes
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(
        0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result))


def _install_path(args):
    """Add or remove this venv's Scripts folder from the current user's PATH."""
    if os.name != "nt":
        raise RuntimeError("install-path is Windows-only")
    scripts = Path(sys.executable).resolve().parent
    if not (scripts / "visual-toolkit.exe").is_file():
        raise RuntimeError(
            f"{scripts} does not contain visual-toolkit.exe; "
            "run this command from the installed venv")
    current, kind = _read_user_path()
    if args.remove:
        updated, changed = remove_user_path(current, scripts)
    else:
        updated, changed = merge_user_path(current, scripts)
    config_value = None
    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        if not config_path.is_file():
            raise ValueError(f"Config file not found: {config_path}")
        config_value = str(config_path)
    plan = {
        "scope": "user",
        "path_entry": str(scripts),
        "action": "remove" if args.remove else "add",
        "changed": changed,
        "previous_path": current,
        "updated_path": updated,
        "config_env": config_value,
        "dry_run": bool(args.dry_run),
    }
    if not args.dry_run:
        if changed:
            _write_user_path(updated, kind)
        if config_value:
            _set_user_env("VISUAL_TOOLKIT_CONFIG", config_value)
        if changed or config_value:
            _broadcast_environment_change()
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def _parser():
    parser = argparse.ArgumentParser(prog="visual-toolkit")
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="open the VisualToolkit review GUI")
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
    montage.add_argument("--config", help="optional VisualToolkit JSON/YAML settings config")
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
    settings.add_argument("--config", help="optional VisualToolkit JSON/YAML settings config")
    config_check = commands.add_parser("config-check", help="check configured source paths")
    config_check.add_argument("--config")
    config_init = commands.add_parser("config-init", help="create the per-user YAML config without overwriting")
    config_init.add_argument("--output", help="explicit YAML destination; defaults to the per-user config path")
    config_init.add_argument("--from-config", help="copy an existing JSON/YAML config; default target auto-migrates legacy per-user JSON")
    config_init.add_argument("--dry-run", action="store_true", help="show source/destination hashes and action without writing")
    install_path = commands.add_parser(
        "install-path",
        help="add this venv's Scripts folder to the current user's PATH")
    install_path.add_argument("--remove", action="store_true",
                              help="remove the entry instead of adding it")
    install_path.add_argument("--config",
                              help="also set VISUAL_TOOLKIT_CONFIG for the current user")
    install_path.add_argument("--dry-run", action="store_true",
                              help="print the plan without changing the environment")
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
        from .dataset_config import main as config_main
        check_argv = ["--check"]
        if args.config:
            check_argv.extend(("--config", args.config))
        return config_main(check_argv)
    if args.command == "config-init":
        try:
            from .dataset_config import initialize_default_config
            plan = initialize_default_config(
                output=args.output, from_path=args.from_config, dry_run=args.dry_run)
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    if args.command == "install-path":
        try:
            return _install_path(args)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            parser.error(str(exc))
    parser.print_help()
    return 0
