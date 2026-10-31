"""Load explicit, portable VisPa dataset configuration.

Version: 1.12.0.dev3 (local/unreleased)
Last updated: 2026-10-31
Change history: ../../CHANGELOG.md
2026-10-30: Set the review-marker crosshair default to 320 display pixels;
retain the legacy setting as accepted compatibility metadata.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
import time
from collections.abc import Mapping, MutableMapping
from pathlib import Path, PureWindowsPath
from typing import Any

ENV_VAR = "VISPA_CONFIG"
COMPAT_ENV_VAR = "VISUAL_TOOLKIT_CONFIG"
LEGACY_ENV_VAR = "PROJECTOME_DATASETS"
SCHEMA_VERSION = 1
DATASET_KINDS = ("ds00_processed", "resample_5um", "swc_cache")
CONFIG_SUFFIXES = (".json", ".yaml", ".yml")
YAML_SUFFIXES = (".yaml", ".yml")


def config_path() -> Path:
    """Return an explicit config path or the per-user YAML target, without creating it."""
    configured = os.environ.get(ENV_VAR)
    return Path(configured).expanduser() if configured else default_config_path()


def default_config_path() -> Path:
    """Return the per-user YAML config target without creating it."""
    app_data = os.environ.get("APPDATA")
    base = Path(app_data) if app_data else Path.home() / ".config"
    return base / "VisPa" / "vispa_config.yaml"


def legacy_default_config_path() -> Path:
    """Return the prior per-user JSON location for one-time YAML migration."""
    app_data = os.environ.get("APPDATA")
    base = Path(app_data) if app_data else Path.home() / ".config"
    return base / "VisualToolkit" / "visual_toolkit_config.json"


def legacy_yaml_config_path() -> Path:
    """Return the former per-user YAML location without modifying it."""
    app_data = os.environ.get("APPDATA")
    base = Path(app_data) if app_data else Path.home() / ".config"
    return base / "VisualToolkit" / "visual_toolkit_config.yaml"


def packaged_config_path():
    """Primary packaged profile, with one legacy location for older installs."""
    from importlib.resources import files

    package = files("vispa")
    primary = package.joinpath("configs", "config_deb.yaml")
    return primary if primary.is_file() else package.joinpath("config_deb.yaml")


def _template_bytes() -> bytes:
    return packaged_config_path().read_bytes()


def _parse_config_bytes(content: bytes, source: Path) -> dict:
    text = content.decode("utf-8")
    suffix = source.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix not in YAML_SUFFIXES:
        raise ValueError(f"{source}: config filename must end with .json, .yaml or .yml")
    import yaml
    return yaml.safe_load(text) or {}


def _empty_config(source: Path, base_dir: Path | None = None, *, origin: str) -> dict:
    user_data = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")) / "VisPa"
    base = base_dir or source.parent
    defaults = {"cache_root": user_data / "cache", "output_root": user_data / "output"}
    return {"path": source, "base_dir": base, "defaults": defaults, "samples": {},
            "visual_toolkit": {"output_root": defaults["output_root"], "settings": {},
                               "startup_mode": "configured"},
            "sources": {}, "config_origin": origin}


def _resolve(value, base: Path):
    if value is None or not str(value).strip():
        return None
    candidate = Path(os.path.expandvars(str(value))).expanduser()
    if candidate.is_absolute():
        return candidate
    joined = base / candidate
    # Path.resolve can probe a UNC server. Config loading must remain usable off
    # the lab network; child paths are normalized without opening the share.
    return Path(os.path.normpath(str(joined))) if str(base).startswith("\\\\") else joined.resolve()


def _relative_under(value, root, key):
    """Resolve a declared child of one editable source root."""
    if value is None:
        return None
    if not root:
        raise ValueError(f"{key} requires defaults.ds00_root")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonempty relative path")
    candidate = Path(value)
    windows = PureWindowsPath(value)
    if (candidate.is_absolute() or windows.is_absolute() or windows.drive
            or ".." in candidate.parts or ".." in windows.parts):
        raise ValueError(f"{key} must stay under defaults.ds00_root")
    return _resolve(candidate, root)


def _positive_int_vector(value, key, length=3):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{key} must contain {length} integers")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{key} values must be positive integers")
    return tuple(int(item) for item in value)


def _finite_vector(value, key, length=3, *, nonzero=False, positive=False):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{key} must contain {length} finite numbers")
    if any(isinstance(item, bool) for item in value):
        raise ValueError(f"{key} values must be finite numbers, not booleans")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{key} values must be finite numbers") from exc
    if any(not math.isfinite(item) or (positive and item <= 0) or (nonzero and item == 0)
           for item in result):
        qualifier = "positive finite" if positive else "finite and nonzero" if nonzero else "finite"
        raise ValueError(f"{key} values must be {qualifier} numbers")
    return result


def _geometry_descriptor(value, sample_id):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"samples.{sample_id}.ds00_expected_geometry must be a mapping")
    required = {"shape_ijk", "spacing_mm_ijk", "affine_diag"}
    missing = required - set(value)
    extra = set(value) - required
    if missing or extra:
        raise ValueError(
            f"samples.{sample_id}.ds00_expected_geometry requires exactly {sorted(required)}; "
            f"missing={sorted(missing)}, unknown={sorted(extra)}")
    spacing = _finite_vector(value["spacing_mm_ijk"], f"samples.{sample_id}.ds00_expected_geometry.spacing_mm_ijk", positive=True)
    affine_diag = _finite_vector(value["affine_diag"], f"samples.{sample_id}.ds00_expected_geometry.affine_diag", nonzero=True)
    if any(not math.isclose(abs(diag), step, rel_tol=0.0, abs_tol=1e-6)
           for diag, step in zip(affine_diag, spacing)):
        raise ValueError(f"samples.{sample_id}.ds00_expected_geometry affine diagonal magnitudes must match spacing")
    return {
        "shape_ijk": _positive_int_vector(value["shape_ijk"], f"samples.{sample_id}.ds00_expected_geometry.shape_ijk"),
        "spacing_mm_ijk": spacing,
        "affine_diag": affine_diag,
    }


def _resample_policy(value, sample_id, resample_path):
    if value is None:
        return None
    prefix = f"samples.{sample_id}.resample_5um_policy"
    if not isinstance(value, dict):
        raise ValueError(f"{prefix} must be a mapping")
    if value.get("corrected") is not True:
        raise ValueError(f"{prefix}.corrected must be true when a correction policy is declared")
    required = {"corrected", "completion_record", "sample_id_field", "required_values",
                "collection_counts", "empty_fields", "cache_namespace", "provenance"}
    missing = required - set(value)
    extra = set(value) - required
    if missing or extra:
        raise ValueError(f"{prefix} is incomplete; missing={sorted(missing)}, unknown={sorted(extra)}")
    record = value["completion_record"]
    if (not isinstance(record, str) or not record or record != record.strip() or Path(record).is_absolute()
            or PureWindowsPath(record).is_absolute() or ":" in record):
        raise ValueError(f"{prefix}.completion_record must be a source-relative filename")
    record_parts = record.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in record_parts):
        raise ValueError(f"{prefix}.completion_record must not contain traversal components")
    sample_id_field = value["sample_id_field"]
    if not isinstance(sample_id_field, str) or not sample_id_field.strip():
        raise ValueError(f"{prefix}.sample_id_field must be a nonempty field name")
    expected = value["required_values"]
    if not isinstance(expected, dict) or not expected:
        raise ValueError(f"{prefix}.required_values must be a nonempty mapping")
    if any(not isinstance(key, str) or not key for key in expected):
        raise ValueError(f"{prefix}.required_values keys must be nonempty field names")
    if sample_id_field in expected:
        raise ValueError(f"{prefix}.required_values must not duplicate sample_id_field")
    counts = value["collection_counts"]
    if not isinstance(counts, dict) or not counts:
        raise ValueError(f"{prefix}.collection_counts must be a nonempty mapping")
    for name, count in counts.items():
        if not isinstance(name, str) or not name or isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{prefix}.collection_counts values must be nonnegative integers")
    empty_fields = value["empty_fields"]
    if (not isinstance(empty_fields, (list, tuple)) or not empty_fields
            or any(not isinstance(name, str) or not name.strip() for name in empty_fields)
            or len(set(empty_fields)) != len(empty_fields)):
        raise ValueError(f"{prefix}.empty_fields must be a nonempty list of unique field names")
    namespace = value["cache_namespace"]
    if (not isinstance(namespace, str) or not namespace or namespace in {".", ".."}
            or namespace == "low_res_ssh"
            or not all(char.isascii() and (char.isalnum() or char in "_-") for char in namespace)):
        raise ValueError(f"{prefix}.cache_namespace must be a simple directory name")
    provenance = value["provenance"]
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError(f"{prefix}.provenance must be a nonempty mapping")
    if {"record", "sha256"} & set(provenance):
        raise ValueError(f"{prefix}.provenance cannot override computed record or sha256")
    if not resample_path:
        raise ValueError(f"{prefix} requires a configured samples.{sample_id}.resample_5um source")
    return copy.deepcopy(value)


def validate_public_example_source(value: dict) -> dict:
    """Validate one public SWC source without changing valid field casing."""
    from urllib.parse import urlsplit

    if not isinstance(value, dict):
        raise ValueError("sources.public_example must be a mapping")
    example = dict(value)
    for key in ("source_url", "metadata_url"):
        url = example.get(key)
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.username or parsed.password or parsed.fragment):
            raise ValueError(f"sources.public_example.{key} must be a plain HTTP(S) URL")
    record_id = example.get("record_id")
    if not isinstance(record_id, str) or not record_id.strip():
        raise ValueError("sources.public_example.record_id must be nonempty text")
    record_file = example.get("record_file")
    if (not isinstance(record_file, str) or not record_file.lower().endswith(".swc")
            or Path(record_file).name != record_file or PureWindowsPath(record_file).name != record_file
            or ".." in record_file):
        raise ValueError("sources.public_example.record_file must be a simple .swc basename")
    sha = example.get("sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
        raise ValueError("sources.public_example.sha256 must be 64 hexadecimal characters")
    return example


def load(path: str | Path | None = None, base_dir: str | Path | None = None) -> dict:
    """Load schema-v1 JSON or YAML and resolve paths against its declared base.

    An explicit argument or VISPA_CONFIG path wins and is never created. With no
    override, the own per-user YAML wins, then the package-owned neutral YAML
    is used in memory. Legacy files remain available by explicit path.
    """
    explicit = path is not None
    env_path = os.environ.get(ENV_VAR)
    origin = "explicit" if explicit else "environment" if env_path else "user_yaml"
    if explicit:
        source = Path(path).expanduser()
    elif env_path:
        source = Path(env_path).expanduser()
    else:
        target = default_config_path()
        if target.is_file():
            source = target
            origin = "user_yaml"
        else:
            source = target
            origin = "package_default"
    source = source.resolve()
    if origin == "package_default":
        content = _template_bytes()
    elif source.is_file():
        content = source.read_bytes()
    else:
        base = Path(base_dir).expanduser() if base_dir else source.parent
        return _empty_config(source, base, origin=origin)
    raw = _parse_config_bytes(content, source)
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: top level must be a mapping")
    unknown = set(raw) - {"version", "base_dir", "defaults", "samples", "visual_toolkit", "sources",
                          "dataset_manifest", "legacy_raw_swc_root"}
    if unknown:
        raise ValueError(f"{source}: unknown top-level keys {sorted(unknown)}")
    if raw.get("version") != SCHEMA_VERSION:
        raise ValueError(f"{source}: unsupported version {raw.get('version')!r}; expected {SCHEMA_VERSION}")
    configured_base = Path(base_dir).expanduser() if base_dir else Path(raw.get("base_dir") or source.parent).expanduser()
    if not configured_base.is_absolute():
        configured_base = (source.parent / configured_base).resolve()
    defaults_raw = raw.get("defaults", {})
    if defaults_raw is None:
        defaults_raw = {}
    if not isinstance(defaults_raw, dict):
        raise ValueError("defaults must be a mapping")
    defaults = {key: _resolve(defaults_raw.get(key), configured_base) for key in
                ("ds00_root", "resample_5um_root", "swc_cache_root", "swc_root", "cache_root", "output_root")}
    # A per-sample relative swc_cache follows the declared SWC roots only. It must
    # not inherit the per-user cache_root fallback, which would move caches out of
    # the config's own tree when swc_root is absent.
    declared_swc_cache_base = defaults["swc_cache_root"] or defaults["swc_root"]
    user_data = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")) / "VisPa"
    if defaults["cache_root"] is None:
        defaults["cache_root"] = user_data / "cache"
    if defaults["output_root"] is None:
        defaults["output_root"] = user_data / "output"
    if defaults["swc_cache_root"] is None:
        defaults["swc_cache_root"] = defaults["swc_root"] or defaults["cache_root"]
    raw_samples = raw.get("samples", {})
    if raw_samples is None:
        raw_samples = {}
    if not isinstance(raw_samples, dict):
        raise ValueError("samples must be a mapping")
    samples = {}
    for sample_id, entry in raw_samples.items():
        if entry is None:
            entry = {}
        if not isinstance(entry, dict):
            raise ValueError(f"samples.{sample_id} must be a mapping")
        if entry.get("ds00_processed") is not None and entry.get("ds00_relative") is not None:
            raise ValueError(f"samples.{sample_id} cannot set both ds00_processed and ds00_relative")
        ds00_path = (_relative_under(entry.get("ds00_relative"), defaults["ds00_root"],
                                     f"samples.{sample_id}.ds00_relative")
                     if entry.get("ds00_relative") is not None
                     else _resolve(entry.get("ds00_processed"), configured_base))
        resample_path = _resolve(entry.get("resample_5um"), defaults["resample_5um_root"] or configured_base)
        policy = _resample_policy(entry.get("resample_5um_policy"), str(sample_id), resample_path)
        corrected = entry.get("resample_5um_corrected", policy is not None)
        if not isinstance(corrected, bool):
            raise ValueError(f"samples.{sample_id}.resample_5um_corrected must be a boolean")
        if corrected and policy is None:
            raise ValueError(f"samples.{sample_id}.resample_5um_corrected requires a complete resample_5um_policy")
        if not corrected and policy is not None:
            raise ValueError(f"samples.{sample_id}.resample_5um_policy conflicts with resample_5um_corrected: false")
        samples[str(sample_id)] = {
            "monkey": None if entry.get("monkey") is None else str(entry["monkey"]),
            "ds00_processed": ds00_path,
            "ds00_sha256": entry.get("ds00_sha256"),
            "resample_5um": resample_path,
            "swc_cache": _resolve(entry.get("swc_cache"), declared_swc_cache_base or configured_base),
            "ds00_expected_geometry": _geometry_descriptor(entry.get("ds00_expected_geometry"), str(sample_id)),
            "resample_5um_corrected": corrected,
            "resample_5um_policy": policy,
        }
    # Preserve the legacy optional-section behavior: null is equivalent to absent.
    ui = raw.get("visual_toolkit", {})
    if ui is None:
        ui = {}
    if not isinstance(ui, dict):
        raise ValueError("visual_toolkit must be a mapping")
    scoped_settings = ui.get("settings", {})
    if not isinstance(scoped_settings, dict):
        raise ValueError("visual_toolkit.settings must be a mapping")
    unknown_scopes = set(scoped_settings) - {"review", "brain-view", "montage"}
    if unknown_scopes:
        raise ValueError(f"visual_toolkit.settings has unknown scope(s): {sorted(unknown_scopes)}")
    for scope, values in scoped_settings.items():
        if not isinstance(values, dict):
            raise ValueError(f"visual_toolkit.settings.{scope} must be a mapping")
    visual_toolkit = {"output_root": _resolve(ui.get("output_root"), configured_base),
                      "auto_reload": bool(ui.get("auto_reload", True)),
                      "worker_python": _resolve(ui.get("worker_python"), configured_base),
                      "default_sample": ui.get("default_sample", ""),
                      "default_neuron": ui.get("default_neuron", ""),
                      "auto_load": ui.get("auto_load", False),
                      "startup_mode": ui.get("startup_mode", "configured"),
                      "settings": copy.deepcopy(scoped_settings)}
    # Optional external tracing tool. Both paths are resolved here so the GUI
    # never has to reinterpret a relative path against the process cwd.
    fnt_tracer = ui.get("fnt_tracer") or {}
    if not isinstance(fnt_tracer, dict):
        raise ValueError("visual_toolkit.fnt_tracer must be a mapping")
    unknown_fnt = set(fnt_tracer) - {"executable", "converter_executable", "project_root", "auto_download",
                                     "cache_root", "server_base_url", "catalog_base_url",
                                     "timeout_seconds", "max_response_bytes"}
    if unknown_fnt:
        raise ValueError(
            f"visual_toolkit.fnt_tracer has unknown key(s): {sorted(unknown_fnt)}")
    visual_toolkit["fnt_tracer"] = {
        key: (_resolve(fnt_tracer.get(key), configured_base)
              if fnt_tracer.get(key) else None)
        for key in ("executable", "converter_executable", "project_root")}
    if visual_toolkit["fnt_tracer"]["converter_executable"] is None:
        executable = visual_toolkit["fnt_tracer"]["executable"]
        if executable is not None:
            visual_toolkit["fnt_tracer"]["converter_executable"] = executable.with_name("fnt-from-swc.exe")
    auto_download = fnt_tracer.get("auto_download", True)
    if not isinstance(auto_download, bool):
        raise ValueError("visual_toolkit.fnt_tracer.auto_download must be a boolean")
    visual_toolkit["fnt_tracer"]["auto_download"] = auto_download
    visual_toolkit["fnt_tracer"]["cache_root"] = _resolve(
        fnt_tracer.get("cache_root"), configured_base) if fnt_tracer.get("cache_root") else None
    for key in ("server_base_url", "catalog_base_url"):
        value = fnt_tracer.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"visual_toolkit.fnt_tracer.{key} must be a nonempty URL")
        visual_toolkit["fnt_tracer"][key] = value
    for key, default in (("timeout_seconds", 30), ("max_response_bytes", 64 * 1024 * 1024)):
        value = fnt_tracer.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"visual_toolkit.fnt_tracer.{key} must be a positive integer")
        visual_toolkit["fnt_tracer"][key] = value
    for key in ("default_sample", "default_neuron"):
        if not isinstance(visual_toolkit[key], str):
            raise ValueError(f"visual_toolkit.{key} must be a string")
    if not isinstance(visual_toolkit["auto_load"], bool):
        raise ValueError("visual_toolkit.auto_load must be a boolean")
    if visual_toolkit["startup_mode"] not in {"configured", "public-example"}:
        raise ValueError("visual_toolkit.startup_mode must be 'configured' or 'public-example'")
    default_sample, default_neuron = visual_toolkit["default_sample"], visual_toolkit["default_neuron"]
    if bool(default_sample) != bool(default_neuron):
        raise ValueError("visual_toolkit.default_sample and default_neuron must both be set or both be blank")
    if default_sample and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", default_sample):
        raise ValueError("visual_toolkit.default_sample must be a path-safe string identifier")
    if default_neuron:
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", default_neuron)
                or ".." in default_neuron or ("." in default_neuron and not default_neuron.lower().endswith(".swc"))):
            raise ValueError("visual_toolkit.default_neuron must be an SWC basename")
    if visual_toolkit["output_root"] is None:
        visual_toolkit["output_root"] = defaults["output_root"]
    raw_sources = raw.get("sources", {})
    if raw_sources is None:
        raw_sources = {}
    if not isinstance(raw_sources, dict):
        raise ValueError("sources must be a mapping")
    sources = dict(raw_sources)
    if sources.get("dataset_manifest") is not None and sources.get("dataset_manifest_relative") is not None:
        raise ValueError("sources cannot set both dataset_manifest and dataset_manifest_relative")
    if sources.get("dataset_manifest_relative") is not None:
        sources["dataset_manifest"] = _relative_under(
            sources.pop("dataset_manifest_relative"), defaults["ds00_root"],
            "sources.dataset_manifest_relative")
    if sources.get("ssh_sample_id") is not None:
        sources["ssh_sample_id"] = str(sources["ssh_sample_id"])
    for key in ("dataset_manifest", "legacy_raw_swc_root"):
        if raw.get(key) is not None:
            sources[key] = raw[key]
    for key in ("dataset_manifest", "legacy_raw_swc_root"):
        if sources.get(key):
            sources[key] = _resolve(sources[key], configured_base)
    if (sources.get("raw_swc_base") and (sources.get("http_host") or sources.get("http_base_url"))
            and not sources.get("legacy_raw_swc_root")):
        # Keep remotely fetched raw trees persistent across loads while keeping
        # shared profiles free of machine-specific cache paths.
        sources["legacy_raw_swc_root"] = defaults["cache_root"] / "swc_raw"
    example = sources.get("public_example")
    if example is not None:
        sources["public_example"] = validate_public_example_source(example)
    tables = sources.get("neuron_tables")
    if tables is not None:
        if not isinstance(tables, dict):
            raise ValueError("sources.neuron_tables must be a mapping")
        tables = dict(tables)
        layout = tables.get("layout", "per_sample")
        if layout != "per_sample":
            raise ValueError("sources.neuron_tables.layout must be per_sample")
        tables["layout"] = layout
        if tables.get("root"):
            tables["root"] = _resolve(tables["root"], configured_base)
        sources["neuron_tables"] = tables
    for key, fields in (("atlas", ("root",)),
                        ("flatmap", ("julia_executable", "monkeyrec", "cache", "output"))):
        block = sources.get(key)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise ValueError(f"sources.{key} must be a mapping")
        block = dict(block)
        if key == "atlas" and block.get("version") not in (None, "NMT_v2.1_sym"):
            raise ValueError("sources.atlas.version must be NMT_v2.1_sym")
        for field in fields:
            if block.get(field):
                block[field] = _resolve(block[field], configured_base)
        sources[key] = block
    catalog = sources.get("neuron_catalog")
    if catalog is not None:
        if not isinstance(catalog, dict):
            raise ValueError("sources.neuron_catalog must be a mapping")
        catalog = dict(catalog)
        mode = catalog.get("mode", "csv")
        if not isinstance(mode, str) or mode not in {"csv", "live-iondata"}:
            raise ValueError("sources.neuron_catalog.mode must be 'csv' or 'live-iondata'")
        catalog["mode"] = mode
        if mode == "csv":
            if not catalog.get("path"):
                raise ValueError("sources.neuron_catalog.path is required for CSV mode")
            catalog["path"] = _resolve(catalog["path"], configured_base)
        else:
            if catalog.get("path"):
                catalog["path"] = _resolve(catalog["path"], configured_base)
            if catalog.get("snapshot_path"):
                catalog["snapshot_path"] = _resolve(catalog["snapshot_path"], configured_base)
        if (mode == "live-iondata"
                or any(key in catalog for key in ("host", "timeout_seconds", "max_response_bytes"))):
            host = catalog.get("host")
            from urllib.parse import urlsplit
            if not isinstance(host, str) or not host.strip() or host != host.strip():
                raise ValueError("sources.neuron_catalog.host must be an HTTP(S) origin without a path or query")
            parsed_host = urlsplit(host)
            if (parsed_host.scheme not in {"http", "https"} or not parsed_host.netloc
                    or parsed_host.username or parsed_host.password
                    or parsed_host.path not in {"", "/"} or parsed_host.query or parsed_host.fragment):
                raise ValueError("sources.neuron_catalog.host must be an HTTP(S) origin without credentials or path")
            try:
                parsed_host.port
            except ValueError as exc:
                raise ValueError("sources.neuron_catalog.host has an invalid port") from exc
            timeout = catalog.get("timeout_seconds", 10)
            if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                    or not math.isfinite(timeout) or timeout < 1 or timeout > 60):
                raise ValueError("sources.neuron_catalog.timeout_seconds must be between 1 and 60")
            byte_limit = catalog.get("max_response_bytes", 8 * 1024 * 1024)
            if (isinstance(byte_limit, bool) or not isinstance(byte_limit, int)
                    or byte_limit < 1024 or byte_limit > 32 * 1024 * 1024):
                raise ValueError("sources.neuron_catalog.max_response_bytes must be between 1024 and 33554432")
            catalog["host"] = f"{parsed_host.scheme}://{parsed_host.netloc}"
            catalog["timeout_seconds"] = float(timeout)
            catalog["max_response_bytes"] = byte_limit
        column_map = catalog.get("columns") or {}
        if not isinstance(column_map, dict):
            raise ValueError("sources.neuron_catalog.columns must be a mapping")
        catalog["columns"] = {str(key): str(value) for key, value in column_map.items()}
        sources["neuron_catalog"] = catalog
    brain_view = sources.get("brain_view")
    if brain_view is not None:
        if not isinstance(brain_view, dict):
            raise ValueError("sources.brain_view must be a mapping")
        brain_view = dict(brain_view)
        for key in ("mesh_path", "processed_swc_root"):
            if not brain_view.get(key):
                raise ValueError(f"sources.brain_view.{key} is required")
            brain_view[key] = _resolve(brain_view[key], configured_base)
        # These declarations are intentionally optional at config-load time:
        # generic meshes must not inherit projectome's historical convention.
        # The 3D worker preflight requires them when a view is requested.
        for key in ("coordinate_frame", "coordinate_units"):
            if brain_view.get(key) is not None:
                brain_view[key] = str(brain_view[key])
        if brain_view.get("region_mesh_root") is not None:
            brain_view["region_mesh_root"] = _resolve(
                brain_view["region_mesh_root"], configured_base)
        if brain_view.get("region_manifest") is not None:
            brain_view["region_manifest"] = _resolve(
                brain_view["region_manifest"], configured_base)
        brain_view["region_color"] = _parse_color(
            brain_view.get("region_color", [0.3, 0.7, 1.0]),
            "sources.brain_view.region_color")
        mesh_label = brain_view.get("mesh_label")
        if mesh_label is not None:
            if (not isinstance(mesh_label, str) or not mesh_label.strip()
                    or len(mesh_label.strip()) > 18
                    or any(not 32 <= ord(character) <= 126
                           for character in mesh_label.strip())):
                raise ValueError(
                    "sources.brain_view.mesh_label must be 1-18 printable ASCII characters")
            brain_view["mesh_label"] = mesh_label.strip()
        settings = brain_view.get("settings") or {}
        if not isinstance(settings, dict):
            raise ValueError("sources.brain_view.settings must be a mapping")
        brain_view["settings"] = dict(settings)
        sources["brain_view"] = brain_view
    result = {"path": source, "base_dir": configured_base, "defaults": defaults,
              "samples": samples, "visual_toolkit": visual_toolkit, "sources": sources,
              "config_origin": origin}
    declared_scopes = [scope for scope, values in scoped_settings.items() if values]
    if declared_scopes:
        _validate_effective_settings(result, declared_scopes)
    return result


def _validate_effective_settings(config: dict, scopes) -> None:
    """Validate declared values after merging package defaults and legacy layers."""
    for scope in sorted(set(scopes)):
        try:
            resolve_settings(scope, config=config)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"visual_toolkit.settings.{scope}: {exc}") from exc


def _materialized_settings(config: dict | None) -> dict:
    """Return effective validated values for every settings scope.

    Focused settings are stored as the flat dotted keys the configuration schema
    and CLI overrides use, not as the renderer's nested value dictionary.
    """

    materialized = {}
    for scope in SCOPES:
        resolved = resolve_settings(scope, config=config)
        flat = {}
        for key in settings_schema(scope)["settings"]:
            node = resolved
            for part in key.split("."):
                node = node[part]
            flat[key] = copy.deepcopy(node)
        materialized[scope] = flat
    return materialized


def initialize_default_config(output: str | Path | None = None,
                              from_path: str | Path | None = None,
                              *, dry_run: bool = False) -> dict:
    """Create YAML without overwriting; legacy sources require from_path.

    Explicit output paths use neutral package defaults unless from_path is supplied.
    An explicit migration preserves the user's JSON source bytes. The created
    file carries validated effective settings for every scope, so a new config is
    complete without inheriting process or package defaults implicitly.
    """
    import hashlib
    import tempfile

    target = Path(output).expanduser() if output is not None else default_config_path()
    if output is not None and target.suffix.lower() not in YAML_SUFFIXES:
        raise ValueError(f"config-init --output must end with .yaml or .yml: {target}")
    target = target.resolve()
    if target.exists():
        existing_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        return {"action": "already_exists", "config_path": str(target),
                "output_sha256": existing_hash, "source_kind": "existing_target"}

    selected_source = Path(from_path).expanduser().resolve() if from_path is not None else None

    source_stat = None
    source_base = None
    if selected_source is not None:
        if not selected_source.is_file():
            raise FileNotFoundError(f"config source does not exist: {selected_source}")
        if selected_source.suffix.lower() not in CONFIG_SUFFIXES:
            raise ValueError(f"config source must end with .json, .yaml or .yml: {selected_source}")
        source_stat = selected_source.stat()
        source_bytes = selected_source.read_bytes()
        raw = _parse_config_bytes(source_bytes, selected_source)
        if not isinstance(raw, dict):
            raise ValueError(f"{selected_source}: top level must be a mapping")
        loaded = load(selected_source)
        source_base = Path(raw.get("base_dir") or selected_source.parent).expanduser()
        if not source_base.is_absolute():
            source_base = (selected_source.parent / source_base).resolve()
        if selected_source.parent.resolve() != target.parent.resolve():
            raw = dict(raw)
            raw["base_dir"] = str(source_base)
        source_kind = "explicit_source"
        source_label = str(selected_source)
        source_hash = hashlib.sha256(source_bytes).hexdigest()
    else:
        raw = _parse_config_bytes(_template_bytes(), Path("config_deb.yaml"))
        loaded = None
        source_label = "package:vispa/config_deb.yaml"
        source_hash = hashlib.sha256(_template_bytes()).hexdigest()
        source_kind = "package_defaults"
    settings_block = _materialized_settings(loaded if loaded is not None else raw)
    visual = raw.get("visual_toolkit")
    if not isinstance(visual, dict):
        visual = {}
    visual = dict(visual)
    visual["settings"] = settings_block
    raw = dict(raw)
    raw["visual_toolkit"] = visual
    import yaml
    output_bytes = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True).encode("utf-8")

    plan = {"action": "would_create" if dry_run else "created",
            "config_path": str(target), "source": source_label,
            "source_kind": source_kind, "source_sha256": source_hash,
            "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "preserved_base_dir": (str(source_base) if selected_source is not None
                                   and selected_source.parent.resolve() != target.parent.resolve()
                                   else None)}
    if dry_run:
        return plan

    if selected_source is not None:
        current_stat = selected_source.stat()
        if (current_stat.st_size != source_stat.st_size
                or current_stat.st_mtime_ns != source_stat.st_mtime_ns
                or hashlib.sha256(selected_source.read_bytes()).hexdigest() != source_hash):
            raise RuntimeError(f"config source changed during migration: {selected_source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                           dir=str(target.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(output_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            return {"action": "already_exists", "config_path": str(target),
                    "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "source_kind": "concurrent_target"}
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    if hashlib.sha256(target.read_bytes()).hexdigest() != plan["output_sha256"]:
        raise RuntimeError(f"published config hash did not match plan: {target}")
    return plan


def default_output_root(config: dict | None = None) -> Path:
    """Return the configured output root or the per-user VisPa folder."""
    config = config if config is not None else load()
    return Path(config.get("visual_toolkit", {}).get("output_root") or
                config.get("defaults", {}).get("output_root") or
                (Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")) / "VisPa" / "output"))




def sample(sample_id: str, config: dict | None = None) -> dict | None:
    config = config if config is not None else load()
    row = config["samples"].get(str(sample_id))
    return dict(row) if row else None


def sample_ids(config: dict | None = None) -> list[str]:
    return sorted((config if config is not None else load())["samples"])


def check(sample_id: str | None = None, config: dict | None = None) -> list[dict]:
    config = config if config is not None else load()
    ids = [str(sample_id)] if sample_id else sample_ids(config)
    rows = []
    for sid in ids:
        entry = config["samples"].get(sid)
        if entry is None:
            rows.append({"sample": sid, "dataset": "-", "path": None, "exists": None, "note": "not configured"})
            continue
        for kind in DATASET_KINDS:
            path = entry.get(kind)
            rows.append({"sample": sid, "dataset": kind, "path": str(path) if path else None,
                         "exists": Path(path).exists() if path else None})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check explicit VisPa dataset links")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sample")
    parser.add_argument("--config")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if not args.check:
        parser.print_help()
        return 2
    config = load(args.config)
    if not config["samples"]:
        print(f"no dataset config found at {config['path']}")
        return 2
    rows = check(args.sample, config)
    if args.json:
        print(json.dumps({"config": str(config["path"]), "rows": rows}, indent=2))
    else:
        for row in rows:
            print(f"{row['sample']}\t{row['dataset']}\t{row['exists']}\t{row['path']}")
    return int(args.strict and any(row["exists"] is False for row in rows))


# Shared scoped settings.

SCOPES = ("review", "brain-view", "montage")


def _require_scope(scope: str, *, discovery: bool = False) -> None:
    allowed = (*SCOPES, "all") if discovery else SCOPES
    if scope not in allowed:
        raise ValueError(f"scope must be one of {', '.join(allowed)}")


def parse_overrides(overrides: Mapping[str, Any] | list[str] | tuple[str, ...] | None) -> dict[str, Any]:
    """Parse mappings or repeated KEY=VALUE items, JSON-decoding values when possible.

    Unquoted strings are retained on JSON parse failure. This deliberately keeps the
    review API's historical comma-separated sequences, colors, and ``auto`` values.
    """
    if overrides is None:
        return {}
    if isinstance(overrides, Mapping):
        return {str(key): copy.deepcopy(value) for key, value in overrides.items()}
    if not isinstance(overrides, (list, tuple)):
        raise TypeError("overrides must be a mapping or a list of PATH=VALUE strings")
    parsed: dict[str, Any] = {}
    for item in overrides:
        if not isinstance(item, str) or "=" not in item:
            raise ValueError(f"--set expects PATH=VALUE, got {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--set setting name cannot be empty")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        parsed[key] = value
    return parsed


def _review_schema(config=None) -> dict[str, Any]:
    result = copy.deepcopy(review_settings_schema())
    unit_by_key = {
        "marker.color": "hex RGB",
        "marker.min_px": "display pixels",
        "marker.crosshair_px": "display pixels",
        "marker.label_fontsize": "points",
        "marker.label_mode": "none | short | numbered",
        "marker.label_offset_px": "display pixels",
        "soma_window.cubes_xy": "source cubes",
        "soma_window.cubes_xy_steps": "source cubes",
        "soma_window.max_cubes_xy": "source cubes",
        "context.width_um": "µm",
        "context.height_um": "µm",
        "context.depth_um": "µm",
        "context.swc_overlay_depth_um": "µm",
        "widefield.gain": "display multiplier",
        "widefield.threshold": "input intensity",
        "scale_bar_um.soma": "µm",
        "scale_bar_um.context": "µm",
        "scale_bar_um.sagittal": "µm or auto",
        "scale_bar_candidates_um": "µm",
        "figure.panel_figsize": "inches (width, height)",
        "figure.panel_dpi": "dots per inch",
        "figure.review_figsize": "inches (width, height)",
        "figure.review_dpi": "dots per inch",
    }
    for key, spec in result["settings"].items():
        spec["unit"] = unit_by_key[key]
    if config is not None:
        current = resolve_settings("review", config=config)
        for key, spec in result["settings"].items():
            node = current
            for part in key.split("."):
                node = node[part]
            spec["current"] = list(node) if isinstance(node, tuple) else copy.deepcopy(node)
    return result


def _brain_view_schema(config=None) -> dict[str, Any]:
    metadata = {
        "eye_direction": ("float[3]", "centered display direction", "finite vector; nonzero and not parallel to up"),
        "up": ("float[3]", "centered display direction", "finite vector; nonzero and not parallel to eye_direction"),
        "camera_distance_scale": ("number", "mesh-diagonal multiplier", "> 0; fit distance = scale × √3 × mesh diagonal"),
        "line_width": ("number", "pixels", "> 0; processed-neuron line width"),
        "soma_radius": ("number", "declared stored coordinate units", "> 0; no unit conversion is applied"),
        "background": ("float[3]", "normalized RGB", "each component in [0, 1]"),
        "mesh_color": ("float[3]", "normalized RGB", "each component in [0, 1]"),
        "neuron_color": ("float[3]", "normalized RGB", "each component in [0, 1]"),
        "soma_color": ("float[3]", "normalized RGB", "each component in [0, 1]"),
        "window_size": ("integer[2]", "pixels (width, height)", "each dimension ≥ 100"),
    }
    settings = {}
    for key, default in BRAIN_VIEW_DEFAULT_SETTINGS.items():
        kind, unit, constraint = metadata[key]
        settings[key] = {
            "type": kind,
            "default": copy.deepcopy(default),
            "current": copy.deepcopy(default),
            "unit": unit,
            "minimum": None,
            "maximum": None,
            "range": constraint,
            "vector_relation": constraint if key in {"eye_direction", "up"} else None,
            "effect": {
                "eye_direction": "Initial viewing direction in centered display coordinates; framing only.",
                "up": "Camera up direction in centered display coordinates.",
                "camera_distance_scale": "Scales the initial bounds-fit camera distance.",
                "line_width": "Width of the processed-neuron line.",
                "soma_radius": "Display-only marker radius for the processed-SWC root; not a biological soma measurement.",
                "background": "Window and snapshot background color.",
                "mesh_color": "Brain mesh display color.",
                "neuron_color": "Processed-neuron display color.",
                "soma_color": "Distinct processed-SWC root/soma marker color.",
                "window_size": "Initial viewer window width and height.",
            }[key],
        }
    settings["camera_distance_scale"].update(minimum=0, minimum_exclusive=True)
    settings["line_width"].update(minimum=0, minimum_exclusive=True)
    settings["soma_radius"].update(minimum=0, minimum_exclusive=True)
    settings["window_size"].update(minimum=100, minimum_exclusive=False)
    for key in ("background", "mesh_color", "neuron_color", "soma_color"):
        settings[key].update(minimum=0, maximum=1)
    if config is not None:
        current = resolve_settings("brain-view", config=config)
        for key, spec in settings.items():
            spec["current"] = copy.deepcopy(current[key])
    return {"schema": "visual-toolkit.legacy-gl-settings.v1", "settings": settings}


def _montage_schema(config=None) -> dict[str, Any]:
    settings = copy.deepcopy(MONTAGE_SETTING_SPECS)
    for key, spec in settings.items():
        spec["current"] = copy.deepcopy(spec["default"])
        spec["minimum"] = spec.get("min")
        spec["maximum"] = spec.get("max")
    if config is not None:
        current = resolve_settings("montage", config=config)
        for key, spec in settings.items():
            spec["current"] = copy.deepcopy(current[key])
    return {"schema": "visual-toolkit.montage-settings.v1", "settings": settings}


def _validate_config_mapping(config):
    if not isinstance(config, Mapping):
        raise ValueError("settings config must be a path or a loaded config mapping")
    visual = config.get("visual_toolkit", {})
    if not isinstance(visual, Mapping):
        raise ValueError("visual_toolkit must be a mapping")
    scoped = visual.get("settings", {})
    if not isinstance(scoped, Mapping):
        raise ValueError("visual_toolkit.settings must be a mapping")
    unknown = set(scoped) - set(SCOPES)
    if unknown:
        raise ValueError(f"visual_toolkit.settings has unknown scope(s): {sorted(unknown)}")
    for scope, values in scoped.items():
        if not isinstance(values, Mapping):
            raise ValueError(f"visual_toolkit.settings.{scope} must be a mapping")
    sources = config.get("sources", {})
    if not isinstance(sources, Mapping):
        raise ValueError("sources must be a mapping")
    brain = sources.get("brain_view", {})
    if not isinstance(brain, Mapping):
        raise ValueError("sources.brain_view must be a mapping")
    if "settings" in brain and not isinstance(brain["settings"], Mapping):
        raise ValueError("sources.brain_view.settings must be a mapping")
    return config


def _load_config(config):
    if config is None:
        return None
    if isinstance(config, Mapping):
        return _validate_config_mapping(config)
    return _validate_config_mapping(load(config))


def _deep_merge(base, overlay):
    result = copy.deepcopy(dict(base))
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _mapping_paths(value, prefix=""):
    paths = set()
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        paths.add(path)
        if isinstance(item, Mapping):
            paths.update(_mapping_paths(item, path))
    return paths


def _json_value(value):
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _settings_config(config, scope: str) -> dict[str, Any]:
    if config is None:
        return {}
    visual = config.get("visual_toolkit", {})
    scoped = visual.get("settings", {}) if isinstance(visual, Mapping) else {}
    configured = copy.deepcopy(scoped.get(scope, {})) if isinstance(scoped, Mapping) else {}
    if scope == "brain-view":
        legacy = config.get("sources", {}).get("brain_view", {}).get("settings", {})
        if isinstance(legacy, Mapping):
            configured = {**copy.deepcopy(legacy), **configured}
    return configured


def config_source(config):
    """Return the selected config path for receipts, or None when omitted."""
    if config is None:
        return None
    loaded = _load_config(config)
    path = loaded.get("path") if isinstance(loaded, Mapping) else None
    return str(path) if path is not None else None


def settings_schema(scope: str = "all", config=None) -> dict[str, Any]:
    """Return scope metadata without optional render dependencies.

    Without ``config``, brain-view and montage current values are package defaults.
    With a config path or loaded mapping, current reflects its validated settings.
    """
    _require_scope(scope, discovery=True)
    loaded = _load_config(config) if config is not None else None
    if scope == "review":
        result = _review_schema(loaded)
    elif scope == "brain-view":
        result = _brain_view_schema(loaded)
    elif scope == "montage":
        result = _montage_schema(loaded)
    else:
        return {
            "schema": "visual-toolkit.settings.v1",
            "scopes": {name: settings_schema(name, config=loaded) for name in SCOPES},
        }
    if loaded is not None:
        result["config_path"] = str(loaded.get("path")) if loaded.get("path") is not None else None
    return result


def resolve_settings(scope: str, overrides=None, base: Mapping[str, Any] | None = None, *, config=None) -> dict[str, Any]:
    """Return a validated deep copy; precedence is defaults/base, config, overrides."""
    _require_scope(scope)
    if base is not None and not isinstance(base, Mapping):
        raise ValueError("base must be a mapping")
    parsed = parse_overrides(overrides)
    loaded = _load_config(config) if config is not None else None
    configured = _settings_config(loaded, scope)
    if scope == "review":
        initial = _DEFAULT_REVIEW_SETTINGS if loaded is not None else review_settings_snapshot()
        candidate = _deep_merge(initial, base or {})
        known = set(review_settings_schema()["settings"])
        prefixes = {".".join(path.split(".")[:index])
                    for path in known for index in range(1, len(path.split(".")))}
        unknown_base = _mapping_paths(base or {}) - known - prefixes
        if unknown_base:
            raise ValueError(f"unknown review setting(s) in base: {', '.join(sorted(unknown_base))}")
        apply_setting_overrides(configured, settings=candidate)
        apply_setting_overrides(parsed, settings=candidate)
        return candidate
    if scope == "brain-view":
        legacy_and_scoped = {**configured}
        if base is not None:
            legacy_and_scoped = {**copy.deepcopy(dict(base)), **legacy_and_scoped}
        return resolve_brain_view_settings(legacy_and_scoped, parsed)

    configured_base = copy.deepcopy(dict(base)) if base is not None else {}
    configured_base.update(configured)
    return resolve_montage_settings(parsed, base=configured_base)


def apply_settings(scope: str, overrides, settings: MutableMapping[str, Any] | None = None, *, config=None) -> dict[str, Any]:
    """Atomically apply overrides to a caller-owned mapping or review globals.

    With no explicit target, only review settings may update existing process-global
    renderer defaults. Other scopes require a mutable settings mapping.
    """
    _require_scope(scope)
    parsed = parse_overrides(overrides)
    if settings is None:
        if scope != "review":
            raise ValueError(f"apply_settings({scope!r}) requires an explicit mutable settings target")
        candidate = resolve_settings(scope, parsed, config=config)
        before = review_settings_snapshot()
        changed = {}
        for key in _SETTING_SPECS:
            prior = _setting_at(before, key)
            value = _setting_at(candidate, key)
            if _json_value(prior) != _json_value(value):
                changed[key] = _json_value(value)
        REVIEW_SETTINGS.clear()
        REVIEW_SETTINGS.update(candidate)
        _sync_review_setting_constants()
        return changed
    if not isinstance(settings, MutableMapping):
        raise TypeError("settings must be a mutable mapping")
    candidate = resolve_settings(scope, parsed, base=settings, config=config)
    schema = settings_schema(scope)
    leaves = schema["settings"].keys()
    changed = {}
    missing = object()
    for key in leaves:
        if "." in key:
            node = candidate
            for part in key.split("."):
                node = node[part]
            before = settings
            for part in key.split("."):
                if not isinstance(before, Mapping) or part not in before:
                    before = missing
                    break
                before = before[part]
            if before is missing or _json_value(before) != _json_value(node):
                changed[key] = _json_value(node)
        elif key in candidate and (key not in settings or
                                   _json_value(settings[key]) != _json_value(candidate[key])):
            changed[key] = _json_value(candidate[key])
    settings.clear()
    settings.update(candidate)
    return changed


def _flat_setting_value(settings: Mapping[str, Any], key: str):
    node = settings
    for part in key.split("."):
        node = node[part]
    return _json_value(node)


def _packaged_tuning_defaults() -> dict[str, dict[str, Any]]:
    packaged = load(packaged_config_path())
    return {
        scope: {key: _flat_setting_value(resolve_settings(scope, config=packaged), key)
                for key in settings_schema(scope)["settings"]}
        for scope in SCOPES
    }


def tuning_status(config, scope: str = "all") -> dict[str, Any]:
    """Report effective saved tuning differences from packaged DEB defaults."""
    _require_scope(scope, discovery=True)
    loaded = _load_config(config)
    if loaded is None:
        raise ValueError("tuning requires a selected configuration")
    defaults = _packaged_tuning_defaults()
    scopes = SCOPES if scope == "all" else (scope,)
    differences = {}
    for name in scopes:
        current = resolve_settings(name, config=loaded)
        changed = {}
        for key, default in defaults[name].items():
            saved = _flat_setting_value(current, key)
            if saved != default:
                changed[key] = {"default": default, "saved": saved}
        differences[name] = changed
    return {
        "schema": "vispa.tuning.v1",
        "config_path": config_source(loaded),
        "defaults_source": str(packaged_config_path()),
        "scope": scope,
        "different": sum(len(values) for values in differences.values()),
        "differences": differences,
    }


def update_tuning(config, scope: str = "all", overrides=None, *,
                  reset_key: str | None = None, reset_scope: bool = False,
                  reset_all: bool = False, dry_run: bool = True) -> dict[str, Any]:
    """Preview or persist validated tuning in the selected config itself.

    Exactly one operation is accepted: set one scope's repeated ``KEY=VALUE``
    overrides, reset one key, reset one scope, or reset all scopes. ``dry_run``
    defaults to true so callers must explicitly authorize persistence.
    """
    import hashlib
    _require_scope(scope, discovery=True)
    operations = [bool(parse_overrides(overrides)), reset_key is not None,
                  bool(reset_scope), bool(reset_all)]
    if sum(operations) != 1:
        raise ValueError("choose exactly one tuning operation: overrides, reset_key, reset_scope, or reset_all")
    if (overrides or reset_key is not None) and scope == "all":
        raise ValueError("setting or resetting one key requires an explicit scope")
    selected = Path(config_source(config) or "").expanduser().resolve()
    if not selected.is_file():
        raise FileNotFoundError("selected tuning configuration does not exist")
    before = selected.read_bytes()
    before_text = before.decode("utf-8")
    expected = hashlib.sha256(before).hexdigest()
    raw = parse_text(before_text, selected)
    original_raw = copy.deepcopy(raw)
    defaults = _packaged_tuning_defaults()
    visual = raw.setdefault("visual_toolkit", {})
    if not isinstance(visual, dict):
        raise ValueError("visual_toolkit must be a mapping")
    saved = visual.setdefault("settings", {})
    if not isinstance(saved, dict):
        raise ValueError("visual_toolkit.settings must be a mapping")

    if reset_all:
        visual["settings"] = {}
        saved = visual["settings"]
        brain = raw.get("sources", {}).get("brain_view", {})
        if isinstance(brain, dict):
            brain.pop("settings", None)
        operation = "reset_all"
    elif reset_scope:
        saved.pop(scope, None)
        if scope == "brain-view":
            brain = raw.get("sources", {}).get("brain_view", {})
            if isinstance(brain, dict):
                brain.pop("settings", None)
        operation = "reset_scope"
    elif reset_key is not None:
        if reset_key not in defaults[scope]:
            raise KeyError(f"unknown {scope} setting {reset_key!r}")
        scoped = saved.get(scope)
        if isinstance(scoped, dict):
            scoped.pop(reset_key, None)
            if not scoped:
                saved.pop(scope, None)
        if scope == "brain-view":
            legacy = raw.get("sources", {}).get("brain_view", {}).get("settings")
            if isinstance(legacy, dict):
                legacy.pop(reset_key, None)
        operation = "reset_key"
    else:
        parsed = parse_overrides(overrides)
        resolved = resolve_settings(scope, parsed, config=config)
        target = saved.setdefault(scope, {})
        if not isinstance(target, dict):
            raise ValueError(f"visual_toolkit.settings.{scope} must be a mapping")
        for key in parsed:
            if key not in settings_schema(scope)["settings"]:
                raise KeyError(f"unknown {scope} setting {key!r}")
            target[key] = _flat_setting_value(resolved, key)
        operation = "set"

    # Absence normally means the package default. If a future packaged DEB value
    # intentionally differs from the code default, retain only that necessary leaf.
    reset_targets = ({name: tuple(defaults[name]) for name in SCOPES} if reset_all else
                     {scope: tuple(defaults[scope])} if reset_scope else
                     {scope: (reset_key,)} if reset_key is not None else {})
    for name, keys in reset_targets.items():
        resolved = resolve_settings(name, config=raw)
        for key in keys:
            default = defaults[name][key]
            if _flat_setting_value(resolved, key) != default:
                visual.setdefault("settings", {}).setdefault(name, {})[key] = copy.deepcopy(default)
                resolved = resolve_settings(name, config=raw)
    for name in SCOPES:
        resolve_settings(name, config=raw)
    content = before_text if raw == original_raw else dump_text(raw, selected)
    output_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    status = tuning_status(raw, scope="all")
    status["config_path"] = str(selected)
    result = {
        "schema": "vispa.tuning-update.v1", "operation": operation,
        "dry_run": bool(dry_run), "config_path": str(selected),
        "input_sha256": expected, "output_sha256": output_hash,
        "changed": output_hash != expected,
        "comments_preserved": content == before_text or selected.suffix.lower() == ".json" or "#" not in before_text,
        "status": status,
    }
    if not dry_run and result["changed"]:
        saved_result = save_config(selected, content, expected_sha256=expected)
        result["backup"] = str(saved_result["backup"]) if saved_result["backup"] else None
    else:
        result["backup"] = None
    return result


__all__ = ["SCOPES", "parse_overrides", "settings_schema", "resolve_settings",
           "apply_settings", "tuning_status", "update_tuning", "config_source"]


# Lossless form projection for common configuration fields.


# Labels are deliberately user-facing; keys remain the existing config schema.
FIELDS = (
    ("Data folders", "defaults.ds00_root", "DS00 folder (sample images and relative manifest follow this)", "dir"),
    ("Data folders", "defaults.resample_5um_root", "5 µm image folder", "dir"),
    ("Data folders", "defaults.swc_cache_root", "SWC cache folder", "dir"),
    ("Data folders", "defaults.swc_root", "Local SWC folder", "dir"),
    ("Data folders", "defaults.cache_root", "Download cache folder", "dir"),
    ("Data folders", "defaults.output_root", "Figure output folder", "dir"),
    ("Sources", "sources.neuron_catalog.host", "Neuron catalog address", "text"),
    ("Sources", "sources.neuron_catalog.mode", "Neuron catalog source", "catalog_mode"),
    ("Sources", "sources.neuron_catalog.path", "Neuron catalog CSV file (CSV mode)", "file"),
    ("Sources", "sources.neuron_catalog.timeout_seconds", "Catalog timeout (seconds)", "positive_number"),
    ("Sources", "sources.dataset_manifest_relative", "Manifest path under DS00 folder", "text"),
    ("Sources", "sources.dataset_manifest", "Explicit manifest file (overrides relative path)", "file"),
    ("Sources", "sources.legacy_raw_swc_root", "Raw SWC source folder", "dir"),
    ("Sources", "sources.raw_swc_base", "Raw SWC download address", "text"),
    ("Sources", "sources.http_host", "Image server address", "text"),
    ("Sources", "sources.http_path", "Image server path", "text"),
    ("Brain view", "sources.brain_view.mesh_path", "Brain mesh file", "file"),
    ("Brain view", "sources.brain_view.processed_swc_root", "Processed SWC folder", "dir"),
    ("FNT", "visual_toolkit.fnt_tracer.executable", "fnt-tracer program", "file"),
    ("FNT", "visual_toolkit.fnt_tracer.auto_download", "Download FNT during Render", "bool"),
    ("FNT", "visual_toolkit.fnt_tracer.cache_root", "FNT cache folder (blank uses download cache)", "dir"),
    ("FNT", "visual_toolkit.fnt_tracer.server_base_url", "FNT server address", "text"),
    ("FNT", "visual_toolkit.fnt_tracer.catalog_base_url", "FNT catalog address", "text"),
    ("FNT", "visual_toolkit.fnt_tracer.timeout_seconds", "FNT timeout (seconds)", "positive_int"),
    ("Startup", "visual_toolkit.default_sample", "Default sample ID", "text"),
    ("Startup", "visual_toolkit.default_neuron", "Default neuron ID", "text"),
    ("Startup", "visual_toolkit.auto_load", "Load default on startup", "bool"),
)

def parse_text(content: str, path: str | Path) -> dict:
    if Path(path).suffix.lower() == ".json":
        raw = json.loads(content)
    else:
        import yaml
        raw = yaml.safe_load(content)
    if not isinstance(raw, dict):
        raise ValueError("Configuration must contain a top-level mapping")
    return raw


def dump_text(raw: dict, path: str | Path) -> str:
    if Path(path).suffix.lower() == ".json":
        return json.dumps(raw, indent=2, ensure_ascii=False) + "\n"
    import yaml
    return yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)


def field_value(raw: dict, dotted: str):
    node = raw
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _field_exists(raw: dict, dotted: str) -> bool:
    node = raw
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def apply_fields(raw: dict, values: dict[str, object]) -> dict:
    """Copy and change only exposed leaf values; all other YAML data survives."""
    result = copy.deepcopy(raw)
    allowed = {field[1]: field[3] for field in FIELDS}
    relative_key = "sources.dataset_manifest_relative"
    explicit_key = "sources.dataset_manifest"
    relative_changed = (relative_key in values and
                        (str(values[relative_key]).strip() or None) != field_value(raw, relative_key))
    explicit_changed = (explicit_key in values and
                        (str(values[explicit_key]).strip() or None) != field_value(raw, explicit_key))
    if relative_changed and explicit_changed and str(values[relative_key]).strip() and str(values[explicit_key]).strip():
        raise ValueError("Manifest: choose a path under the DS00 folder or an explicit file, not both")
    for dotted, supplied in values.items():
        kind = allowed[dotted]
        if kind == "bool":
            if not isinstance(supplied, bool):
                raise ValueError(f"{dotted}: select on or off")
            value = supplied
        else:
            value = str(supplied).strip() or None
            if kind == "catalog_mode" and value not in (None, "live-iondata", "csv"):
                raise ValueError(f"{dotted}: select live-iondata or csv")
            if kind == "sha256" and value is not None:
                if re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
                    raise ValueError(f"{dotted}: enter 64 hexadecimal SHA-256 characters")
            if kind == "positive_number" and value is not None:
                try:
                    value = float(value)
                except ValueError as exc:
                    raise ValueError(f"{dotted}: enter a positive number") from exc
                if not 0 < value < float("inf"):
                    raise ValueError(f"{dotted}: enter a positive number")
            if kind == "positive_int" and value is not None:
                if not value.isdecimal() or int(value) <= 0:
                    raise ValueError(f"{dotted}: enter a positive whole number")
                value = int(value)
        if (field_value(raw, dotted) is None and value is None) or (
                kind == "bool" and not _field_exists(raw, dotted) and value is False):
            continue
        node = result
        parts = dotted.split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if child is None:
                child = {}
                node[part] = child
            if not isinstance(child, dict):
                raise ValueError(f"{dotted}: {part} is not a mapping")
            node = child
        node[parts[-1]] = value
    if explicit_changed and field_value(result, explicit_key):
        result.get("sources", {}).pop("dataset_manifest_relative", None)
    elif relative_changed and field_value(result, relative_key):
        result.get("sources", {}).pop("dataset_manifest", None)
    return result

# Pure-Python renderer configuration definitions; renderers delegate here.
# --- REVIEW SETTINGS (one source for the GUI, bulk runners and every panel renderer) ---
# Everything the Soma / Context / Sagittal review figures need: what to acquire, how
# to draw it, and the single target marker. Callers read these values instead of
# repeating numbers, and explicit plot/CLI parameters still override them.
REVIEW_SETTINGS = {
    # One cyan/turquoise open box with a cross through the exact point marks the
    # target in every panel type (Soma, Context, Sagittal) and in the review figure.
    'marker': {
        'color': '#00e5ee',
        'min_px': 8.0,          # smallest drawn box side, in display pixels
        'crosshair_px': 320.0,  # cross arm length from the exact centre
        'label_fontsize': 12,
        'label_mode': 'none',
        'label_offset_px': 22.0,
    },
    # Soma panel: soma-centred native window, expressed in cubes. The runner starts
    # at the largest step and uses the largest step whose cubes it can load, so the
    # soma stays centred instead of landing near a cube edge.
    'soma_window': {
        'cubes_xy': 1.5,                    # requested window size, in cubes
        'cubes_xy_steps': (1.5, 1.25, 1.0),  # descending centred alternatives
        'max_cubes_xy': 3.0,                # hard cap: the acquired 3 x 3 cube grid
    },
    'context': {'width_um': 8000, 'height_um': 8000, 'depth_um': 30,
                'swc_overlay_depth_um': 100.0},
    'widefield': {'gain': 2.0, 'threshold': 100},
    # Drawn scale bars: the Soma/Context panels keep their legacy fixed bars and the
    # sagittal panel picks the largest 1/2/5 mm bar that fits its field of view.
    'scale_bar_um': {'soma': 30.0, 'context': 500.0, 'sagittal': 'auto'},
    # 1/2/5 x 10^k mm scale bars; the drawn bar is the largest one that still reads
    # as a small feature of the panel, so the three review panels stay comparable.
    'scale_bar_candidates_um': (100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0,
                                10000.0, 20000.0, 50000.0),
    'figure': {'panel_figsize': (12, 12), 'panel_dpi': 600,
               'review_figsize': (30, 11.6), 'review_dpi': 200},
}

TARGET_MARKER_COLOR = REVIEW_SETTINGS['marker']['color']

# Uniform legacy display defaults; explicit plot-call overrides remain supported.
WIDEFIELD_DEFAULT_PARAMETERS = (REVIEW_SETTINGS['widefield']['gain'],
                                REVIEW_SETTINGS['widefield']['threshold'])


# Legacy call-site suffixes map to the current review names, which now drive both
# the plot titles and the written filenames (SomaBlock -> Soma, WideField -> Context).
LEGACY_SUFFIX_NAMES = {'SomaBlock': 'Soma', 'WideField': 'Context'}


def _output_name(suffix) -> str:
    """Current review name for a legacy call-site suffix."""
    return LEGACY_SUFFIX_NAMES.get(str(suffix), str(suffix))


SCALE_BAR_CANDIDATES_UM = REVIEW_SETTINGS['scale_bar_candidates_um']


def _auto_scale_bar_um(fov_um, fraction=0.2):
    """Largest decade scale bar no longer than ``fraction`` of the field width."""
    limit = abs(float(fov_um[0])) * float(fraction)
    fits = [value for value in SCALE_BAR_CANDIDATES_UM if value <= limit]
    return fits[-1] if fits else SCALE_BAR_CANDIDATES_UM[0]


def _stamp() -> str:
    """Per-figure timestamp for quick tracking; the role suffix stays last."""
    return time.strftime('%Y%m%d-%H%M%S')


def resolve_widefield_parameters(sample_id, bg_intensity=None, manual_threshold=None):
    """Resolve uniform legacy display defaults, honoring explicit overrides."""
    default_gain, default_threshold = WIDEFIELD_DEFAULT_PARAMETERS
    gain = default_gain if bg_intensity is None else float(bg_intensity)
    threshold = default_threshold if manual_threshold is None else float(manual_threshold)
    if not math.isfinite(gain) or gain < 0:
        raise ValueError("bg_intensity must be finite and non-negative")
    if not math.isfinite(threshold):
        raise ValueError("manual_threshold must be finite")
    return gain, threshold


def review_settings_snapshot() -> dict:
    """Deep copy of the resolved review settings, for run manifests and receipts."""
    return copy.deepcopy(REVIEW_SETTINGS)


# Public parameter contract for the GUI, command line and Python callers.
_DEFAULT_REVIEW_SETTINGS = copy.deepcopy(REVIEW_SETTINGS)
_SETTING_SPECS = {
    'marker.color': {'type':'color','effect':'Box and cross color in all review panels.'},
    'marker.min_px': {'type':'number','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Nominal target-box minimum side in pixels; the renderer applies a 0.65 side scale.'},
    'marker.crosshair_px': {'type':'number','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Compatibility setting; review crosshair arms are drawn at a fixed 320 display pixels.'},
    'marker.label_fontsize': {'type':'integer','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Target label font size in points.'},
    'marker.label_mode': {'type':'enum','choices':['none','short','numbered'],'effect':'Inline soma label: none (legend only), short S, or numbered 1 callout; marker position is unchanged.'},
    'marker.label_offset_px': {'type':'number','minimum':0,'maximum':None,'effect':'Target label offset in display pixels.'},
    'soma_window.cubes_xy': {'type':'number','minimum':0,'minimum_exclusive':True,'maximum':3,'effect':'Requested soma-centred XY window size in source cubes; source acquisition is capped at three cubes.'},
    'soma_window.cubes_xy_steps': {'type':'number_sequence','minimum':0,'minimum_exclusive':True,'maximum':3,'min_items':1,'effect':'Descending centred XY window alternatives in source cubes.'},
    'soma_window.max_cubes_xy': {'type':'number','minimum':0,'minimum_exclusive':True,'maximum':3,'effect':'Maximum acquired XY cube span; the available acquisition is three cubes.'},
    'context.width_um': {'type':'integer','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Widefield context crop width in micrometres.'},
    'context.height_um': {'type':'integer','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Widefield context crop height in micrometres.'},
    'context.depth_um': {'type':'integer','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Widefield context slab depth in micrometres.'},
    'context.swc_overlay_depth_um': {'type':'number','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Total soma-centred depth window for the raw SWC projection in micrometres; the image slab stays context.depth_um.'},
    'widefield.gain': {'type':'number','minimum':0,'maximum':None,'effect':'Widefield display gain; fluorescence values are unchanged.'},
    'widefield.threshold': {'type':'integer','minimum':None,'maximum':None,'effect':'Finite widefield display threshold for the green-mask overlay.'},
    'scale_bar_um.soma': {'type':'number','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Soma panel scale-bar length in micrometres.'},
    'scale_bar_um.context': {'type':'number','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Context panel scale-bar length in micrometres.'},
    'scale_bar_um.sagittal': {'type':'positive_or_auto','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Sagittal scale-bar length in micrometres, or auto to select a fitting 1/2/5 bar.'},
    'scale_bar_candidates_um': {'type':'number_sequence','minimum':0,'minimum_exclusive':True,'maximum':None,'min_items':1,'effect':'Ascending physical scale-bar candidates used by auto selection.'},
    'figure.panel_figsize': {'type':'number_sequence','minimum':0,'minimum_exclusive':True,'maximum':None,'exact_items':2,'effect':'Single-panel Matplotlib size in inches (width, height).'},
    'figure.panel_dpi': {'type':'integer','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Single-panel PNG resolution in dots per inch.'},
    'figure.review_figsize': {'type':'number_sequence','minimum':0,'minimum_exclusive':True,'maximum':None,'exact_items':2,'effect':'Three-panel review figure size in inches (width, height).'},
    'figure.review_dpi': {'type':'integer','minimum':0,'minimum_exclusive':True,'maximum':None,'effect':'Three-panel review PNG resolution in dots per inch.'},
}


def _setting_at(settings, path):
    node = settings
    for key in path.split('.'):
        node = node[key]
    return node


def _assign_setting(settings, path, value):
    keys = path.split('.')
    node = settings
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value


def _sync_review_setting_constants():
    """Refresh legacy cached globals and renderer class defaults from the active settings."""
    global TARGET_MARKER_COLOR, WIDEFIELD_DEFAULT_PARAMETERS, SCALE_BAR_CANDIDATES_UM
    TARGET_MARKER_COLOR = REVIEW_SETTINGS['marker']['color']
    WIDEFIELD_DEFAULT_PARAMETERS = (REVIEW_SETTINGS['widefield']['gain'],
                                    REVIEW_SETTINGS['widefield']['threshold'])
    SCALE_BAR_CANDIDATES_UM = REVIEW_SETTINGS['scale_bar_candidates_um']
    modules = (sys.modules.get('vispa.renderers.microscopy_panels'),
               sys.modules.get('vispa.toolkit'))
    for toolkit in dict.fromkeys(module for module in modules if module is not None):
        toolkit.TARGET_MARKER_COLOR = TARGET_MARKER_COLOR
        toolkit.WIDEFIELD_DEFAULT_PARAMETERS = WIDEFIELD_DEFAULT_PARAMETERS
        toolkit.SCALE_BAR_CANDIDATES_UM = SCALE_BAR_CANDIDATES_UM
        renderer = getattr(toolkit, 'VisPa', None)
        if renderer is not None:
            renderer.PANEL_FIGSIZE = REVIEW_SETTINGS['figure']['panel_figsize']
            renderer.PANEL_DPI = REVIEW_SETTINGS['figure']['panel_dpi']
            renderer.TRIO_FIGSIZE = REVIEW_SETTINGS['figure']['review_figsize']
            renderer.TRIO_DPI = REVIEW_SETTINGS['figure']['review_dpi']


def _parse_setting_value(path, raw, current):
    spec = _SETTING_SPECS[path]
    kind = spec['type']
    if kind == 'enum':
        value = str(raw).strip().lower()
        if value not in spec['choices']:
            raise ValueError(f"Review setting {path!r} needs one of {spec['choices']}")
        return value
    if kind == 'color':
        value = str(raw).strip()
        if not (len(value) == 7 and value.startswith('#')
                and all(ch in '0123456789abcdefABCDEF' for ch in value[1:])):
            raise ValueError(f"Review setting {path!r} needs a #rrggbb colour")
        return value
    if kind == 'positive_or_auto' and isinstance(raw, str) and raw.strip().lower() == 'auto':
        return 'auto'
    if kind == 'number_sequence':
        if isinstance(raw, str):
            parts = [part.strip() for part in raw.split(',')]
        elif isinstance(raw, (list, tuple)):
            parts = list(raw)
        else:
            raise ValueError(f"Review setting {path!r} needs comma-separated numbers")
        if not parts or any(part == '' or isinstance(part, bool) for part in parts):
            raise ValueError(f"Review setting {path!r} needs comma-separated numbers")
        try:
            return tuple(float(part) for part in parts)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Review setting {path!r} needs comma-separated numbers") from exc
    if isinstance(raw, bool):
        raise ValueError(f"Review setting {path!r} needs a number")
    try:
        if kind == 'integer':
            numeric = float(raw)
            if not math.isfinite(numeric) or not numeric.is_integer():
                raise ValueError
            value = int(numeric)
        else:
            value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Review setting {path!r} needs a {kind}") from exc
    if not math.isfinite(float(value)):
        raise ValueError(f"Review setting {path!r} needs a finite number")
    return value


def _validate_review_settings(settings):
    for path, spec in _SETTING_SPECS.items():
        value = _setting_at(settings, path)
        if spec['type'] == 'enum':
            if value not in spec['choices']:
                raise ValueError(f"Review setting {path!r} needs one of {spec['choices']}")
            continue
        if spec['type'] == 'color':
            if not (isinstance(value, str) and len(value) == 7 and value.startswith('#')
                    and all(ch in '0123456789abcdefABCDEF' for ch in value[1:])):
                raise ValueError(f"Review setting {path!r} needs a #rrggbb colour")
            continue
        if spec['type'] == 'positive_or_auto' and value == 'auto':
            continue
        values = value if spec['type'] == 'number_sequence' else (value,)
        if not isinstance(values, (tuple, list)):
            raise ValueError(f"Review setting {path!r} has the wrong value type")
        if 'exact_items' in spec and len(values) != spec['exact_items']:
            raise ValueError(f"Review setting {path!r} needs exactly {spec['exact_items']} values")
        if 'min_items' in spec and len(values) < spec['min_items']:
            raise ValueError(f"Review setting {path!r} needs at least {spec['min_items']} value")
        for item in values:
            try:
                number = float(item)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Review setting {path!r} needs numeric values") from exc
            minimum = spec.get('minimum')
            maximum = spec.get('maximum')
            below_minimum = (minimum is not None and
                             (number <= minimum if spec.get('minimum_exclusive') else number < minimum))
            above_maximum = maximum is not None and number > maximum
            if not math.isfinite(number) or below_minimum or above_maximum:
                constraints = []
                if minimum is not None:
                    operator = '>' if spec.get('minimum_exclusive') else '>='
                    constraints.append(f"{operator} {minimum}")
                if maximum is not None:
                    constraints.append(f"<= {maximum}")
                detail = ' and '.join(constraints) if constraints else 'finite'
                raise ValueError(f"Review setting {path!r} values must be {detail}")
        if spec['type'] == 'integer' and int(value) != value:
            raise ValueError(f"Review setting {path!r} must be an integer")
        if path == 'soma_window.cubes_xy_steps' and any(a <= b for a,b in zip(values,values[1:])):
            raise ValueError("Review setting 'soma_window.cubes_xy_steps' must be strictly descending")
        if path == 'scale_bar_candidates_um' and any(a >= b for a,b in zip(values,values[1:])):
            raise ValueError("Review setting 'scale_bar_candidates_um' must be strictly ascending")
    soma = settings['soma_window']
    if float(soma['cubes_xy']) > float(soma['max_cubes_xy']):
        raise ValueError("soma_window.cubes_xy cannot exceed soma_window.max_cubes_xy")
    if any(float(step) > float(soma['max_cubes_xy']) for step in soma['cubes_xy_steps']):
        raise ValueError("soma_window.cubes_xy_steps cannot exceed soma_window.max_cubes_xy")


def _json_setting_value(value):
    return list(value) if isinstance(value, tuple) else value


def review_settings_schema() -> dict:
    """Return editable settings with defaults, current values, ranges and effects."""
    current = review_settings_snapshot()
    settings = {}
    for path, spec in _SETTING_SPECS.items():
        settings[path] = {
            **spec,
            'default': _json_setting_value(_setting_at(_DEFAULT_REVIEW_SETTINGS, path)),
            'current': _json_setting_value(_setting_at(current, path)),
        }
    return {'schema':'visual-toolkit.review-settings.v1','settings':settings}


def apply_setting_overrides(overrides, settings=None):
    """Atomically apply PATH=VALUE list or mapping overrides to review settings.

    Examples: ``{'marker.color': '#00e5ee'}`` or
    ``['figure.panel_figsize=12,12', 'soma_window.cubes_xy_steps=1.5,1.25,1']``.
    A supplied settings mapping is changed only after the entire candidate validates;
    it never changes process-global renderer constants.
    """
    if settings is None:
        target = REVIEW_SETTINGS
        global_target = True
    else:
        if not isinstance(settings, MutableMapping):
            raise TypeError('settings must be a mutable mapping')
        target = settings
        global_target = target is REVIEW_SETTINGS
    if hasattr(overrides, 'items'):
        items = list(overrides.items())
    elif overrides is None:
        items = []
    elif isinstance(overrides, (list, tuple)):
        items = []
        for item in overrides:
            if not isinstance(item, str) or '=' not in item:
                raise ValueError(f"--set expects PATH=VALUE, got {item!r}")
            key, raw = item.split('=',1)
            items.append((key,raw))
    else:
        raise TypeError('overrides must be a mapping or a list of PATH=VALUE strings')
    candidate = copy.deepcopy(target)
    changed = {}
    for path, raw in items:
        path = str(path).strip()
        if path not in _SETTING_SPECS:
            raise KeyError(f"Unknown review setting {path!r}; run 'vispa settings' to list settings")
        value = _parse_setting_value(path, raw, _setting_at(candidate,path))
        _assign_setting(candidate,path,value)
        changed[path] = _json_setting_value(value)
    _validate_review_settings(candidate)
    target.clear()
    target.update(candidate)
    if global_target:
        _sync_review_setting_constants()
    return changed


BRAIN_VIEW_DEFAULT_SETTINGS = {
    "eye_direction": [-1.3, 1.6, 1.5],
    "up": [0.0, 0.0, 1.0],
    "camera_distance_scale": 0.40,
    "line_width": 2.0,
    "soma_radius": 500.0,
    "background": [0.0, 0.0, 0.0],
    "mesh_color": [0.8, 0.8, 0.8],
    "neuron_color": [1.0, 0.5, 0.0],
    "soma_color": [0.0, 1.0, 1.0],
    "window_size": [1100, 800],
}
_SETTINGS_KEYS = frozenset(BRAIN_VIEW_DEFAULT_SETTINGS)


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


def resolve_brain_view_settings(config_settings: dict | None = None, overrides: dict | None = None) -> dict:
    """Resolve and validate brain-view values while preserving the private alias."""
    if config_settings is not None and not isinstance(config_settings, dict):
        raise ValueError("sources.brain_view.settings must be a mapping")
    resolved = {**BRAIN_VIEW_DEFAULT_SETTINGS, **(config_settings or {}), **(overrides or {})}
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
    for key in ("background", "mesh_color", "neuron_color", "soma_color"):
        resolved[key] = _parse_color(resolved[key], key)
    size = resolved["window_size"]
    if not isinstance(size, (list, tuple)) or len(size) != 2 or any(
            isinstance(x, bool) or not isinstance(x, int) or x < 100 for x in size):
        raise ValueError("window_size must contain two integers of at least 100 pixels")
    resolved["window_size"] = [int(size[0]), int(size[1])]
    return resolved


MONTAGE_DEFAULT_SETTINGS: dict[str, Any] = {
    "figure_size_inches": (18.2, 4.4),
    "figure_dpi": 120,
    "max_dimension": 210,
    "otsu_sample_stride": 8,
    "otsu_clip_percentile": 99.5,
    "intensity_high_percentile": 99.3,
    "minimum_intensity_span": 1.0,
    "blur_sigma_voxels": (0.45, 0.45, 0.95),
    "foreground_threshold": 0.08,
    "min_foreground_voxels": 1000,
    "max_foreground_points": 300000,
    "view_extent_percentiles": (0.6, 99.4),
    "depth_percentiles": (0.3, 99.7),
    "projection_padding_fraction": 0.07,
    "minimum_extent_mm": 5.0,
    "projection_bin_mm": 0.36,
    "horizontal_bins_px": (150, 260),
    "vertical_bins_px": (150, 280),
    "depth_step_mm": 0.55,
    "depth_bins": (56, 110),
    "ray_extinction": 8.0,
    "layer_alpha_cap": 0.88,
    "normalization_percentile": 99.5,
    "display_gamma": 0.88,
    "background_cutoff": 0.012,
    "min_positive_pixels": 200,
    "min_filled_fraction": 0.04,
    "green_channel_scale": 0.985,
    "blue_channel_scale": 0.94,
}

# A compact operator-facing schema. Ranges constrain display parameters only;
# values do not declare anatomy, registration, or scientific acceptance.
_SETTING_METADATA: dict[str, dict[str, Any]] = {
    "figure_size_inches": {"default": [18.2, 4.4], "units": "inches", "range": [1, 100], "effect": "single-volume figure width and height"},
    "figure_dpi": {"default": 120, "units": "dots per inch", "range": [36, 600], "effect": "single-volume PNG output resolution"},
    "max_dimension": {"default": 210, "units": "voxels", "range": [1, 4096], "effect": "maximum downsampled array dimension"},
    "otsu_sample_stride": {"default": 8, "units": "samples", "range": [1, 4096], "effect": "stride used for the Otsu histogram input"},
    "otsu_clip_percentile": {"default": 99.5, "units": "%", "range": [0, 100], "effect": "upper clipping percentile for Otsu values"},
    "intensity_high_percentile": {"default": 99.3, "units": "%", "range": [0, 100], "effect": "high intensity used to normalize display volume"},
    "minimum_intensity_span": {"default": 1.0, "units": "input intensity", "range": [1e-12, None], "effect": "minimum separation between low and high display intensities"},
    "blur_sigma_voxels": {"default": [0.45, 0.45, 0.95], "units": "voxels per array axis", "range": [0, 1000], "effect": "Gaussian smoothing applied to the downsampled display volume"},
    "foreground_threshold": {"default": 0.08, "units": "normalized intensity", "range": [0, 1], "effect": "threshold for foreground samples used to locate the projection origin"},
    "min_foreground_voxels": {"default": 1000, "units": "voxels", "range": [1, None], "effect": "minimum foreground count before rendering"},
    "max_foreground_points": {"default": 300000, "units": "points", "range": [1, None], "effect": "maximum foreground samples used to locate the projection origin"},
    "view_extent_percentiles": {"default": [0.6, 99.4], "units": "%", "range": [0, 100], "effect": "legacy direct composite_view default only; montage uses full input extent"},
    "depth_percentiles": {"default": [0.3, 99.7], "units": "%", "range": [0, 100], "effect": "legacy direct composite_view default only; montage uses full input depth"},
    "projection_padding_fraction": {"default": 0.07, "units": "fraction", "range": [0, 1], "effect": "legacy direct composite_view default only; montage uses full input extent"},
    "minimum_extent_mm": {"default": 5.0, "units": "mm", "range": [1e-12, None], "effect": "minimum width, height, and depth accepted for a view"},
    "projection_bin_mm": {"default": 0.36, "units": "mm per pixel", "range": [1e-12, None], "effect": "nominal projected image sampling interval"},
    "horizontal_bins_px": {"default": [150, 260], "units": "pixels", "range": [1, 4096], "effect": "minimum and maximum projected image width"},
    "vertical_bins_px": {"default": [150, 280], "units": "pixels", "range": [1, 4096], "effect": "minimum and maximum projected image height"},
    "depth_step_mm": {"default": 0.55, "units": "mm per ray step", "range": [1e-12, None], "effect": "nominal sampling interval through the volume"},
    "depth_bins": {"default": [56, 110], "units": "samples", "range": [1, 1024], "effect": "minimum and maximum ray sample count"},
    "ray_extinction": {"default": 8.0, "units": "unitless", "range": [1e-12, None], "effect": "opacity growth rate for each ray sample"},
    "layer_alpha_cap": {"default": 0.88, "units": "fraction", "range": [0, 1], "effect": "maximum opacity of one ray layer"},
    "normalization_percentile": {"default": 99.5, "units": "%", "range": [0, 100], "effect": "positive composite intensity percentile mapped to full display range"},
    "display_gamma": {"default": 0.88, "units": "unitless", "range": [1e-12, None], "effect": "gamma applied to normalized composite intensity"},
    "background_cutoff": {"default": 0.012, "units": "normalized intensity", "range": [0, 1], "effect": "values below this display level become black"},
    "min_positive_pixels": {"default": 200, "units": "pixels", "range": [1, None], "effect": "minimum nonzero composite pixel count"},
    "min_filled_fraction": {"default": 0.04, "units": "fraction", "range": [0, 1], "effect": "minimum fraction of pixels above the fill threshold"},
    "green_channel_scale": {"default": 0.985, "units": "fraction", "range": [0, 1], "effect": "green channel tint multiplier"},
    "blue_channel_scale": {"default": 0.94, "units": "fraction", "range": [0, 1], "effect": "blue channel tint multiplier"},
}


def _setting_type(value: Any) -> str:
    if isinstance(value, (tuple, list)):
        item_type = "integer" if value and all(isinstance(item, int) and not isinstance(item, bool) for item in value) else "float"
        return f"{item_type}[{len(value)}]"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    return "float"

MONTAGE_SETTING_SPECS: dict[str, dict[str, Any]] = {
    key: {
        "type": _setting_type(spec["default"]),
        "default": copy.deepcopy(spec["default"]),
        "effect": spec["effect"],
        "unit": spec["units"],
        "min": spec["range"][0],
        "max": spec["range"][1],
    }
    for key, spec in _SETTING_METADATA.items()
}



def resolve_montage_settings(
    overrides: Mapping[str, Any] | None = None,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deep-copied validated settings; never mutate inputs or globals."""
    values = copy.deepcopy(MONTAGE_DEFAULT_SETTINGS)
    for layer in (base, overrides):
        if layer is None:
            continue
        unknown = sorted(set(layer) - set(values))
        if unknown:
            raise ValueError(f"unknown montage setting(s): {', '.join(unknown)}")
        values.update(copy.deepcopy(dict(layer)))

    def number(key: str, low: float, high: float | None) -> None:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{key} must be a finite number")
        if value < low or (high is not None and value > high):
            raise ValueError(f"{key} must be in [{low}, {high if high is not None else 'infinity'}]")

    def integer(key: str, low: int, high: int | None = None) -> None:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        if value < low or (high is not None and value > high):
            raise ValueError(f"{key} must be in [{low}, {high if high is not None else 'infinity'}]")

    vals = values["figure_size_inches"]
    if not isinstance(vals, (list, tuple)) or len(vals) != 2 or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or not 1 <= v <= 100
        for v in vals
    ):
        raise ValueError("figure_size_inches must contain two finite values in [1, 100]")
    values["figure_size_inches"] = tuple(float(v) for v in vals)
    integer("figure_dpi", 36, 600)
    integer("max_dimension", 1, 4096)
    integer("otsu_sample_stride", 1, 4096)
    number("otsu_clip_percentile", 0, 100)
    number("intensity_high_percentile", 0, 100)
    number("minimum_intensity_span", 1e-12, None)
    for key in ("blur_sigma_voxels",):
        vals = values[key]
        if not isinstance(vals, (list, tuple)) or len(vals) != 3:
            raise ValueError(f"{key} must contain three values")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or v < 0 or v > 1000 for v in vals):
            raise ValueError(f"{key} values must be finite and in [0, 1000]")
        values[key] = tuple(float(v) for v in vals)
    number("foreground_threshold", 0, 1)
    integer("min_foreground_voxels", 1)
    integer("max_foreground_points", 1)
    for key in ("view_extent_percentiles", "depth_percentiles"):
        vals = values[key]
        if not isinstance(vals, (list, tuple)) or len(vals) != 2:
            raise ValueError(f"{key} must contain two ordered percentiles")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in vals) or not 0 <= vals[0] < vals[1] <= 100:
            raise ValueError(f"{key} must satisfy 0 <= lower < upper <= 100")
        values[key] = tuple(float(v) for v in vals)
    number("projection_padding_fraction", 0, 1)
    number("minimum_extent_mm", 1e-12, None)
    number("projection_bin_mm", 1e-12, None)
    for key in ("horizontal_bins_px", "vertical_bins_px", "depth_bins"):
        vals = values[key]
        maximum = 1024 if key == "depth_bins" else 4096
        if not isinstance(vals, (list, tuple)) or len(vals) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= maximum for v in vals) or vals[0] > vals[1]:
            raise ValueError(f"{key} must contain ordered integers in [1, {maximum}]")
        values[key] = tuple(vals)
    for key in ("depth_step_mm", "ray_extinction", "display_gamma"):
        number(key, 1e-12, None)
    for key in ("layer_alpha_cap", "background_cutoff", "min_filled_fraction", "green_channel_scale", "blue_channel_scale"):
        number(key, 0, 1)
    number("normalization_percentile", 0, 100)
    integer("min_positive_pixels", 1)
    return values


def save_config(path: str | Path, content: str, expected_sha256: str | None = None) -> dict:
    """Validate and atomically save JSON/YAML, preserving unchanged bytes.

    Returns `{"changed": bool, "backup": Path | None}`. A stale expected hash
    rejects the save before any write. Backups are created only for replacements.
    """
    import hashlib
    import tempfile
    from datetime import datetime
    target = Path(path).expanduser().resolve()
    packaged = Path(str(packaged_config_path())).resolve()
    if target.name.casefold() == "vispa_config.default.yaml" or target == packaged:
        raise ValueError("Default YAML is read-only; select an active configuration to save.")
    if target.suffix.lower() not in CONFIG_SUFFIXES:
        raise ValueError("Configuration filename must end with .json, .yaml or .yml")
    if not isinstance(content, str):
        raise TypeError("content must be text")
    before = target.read_bytes() if target.exists() else None
    if expected_sha256 is not None:
        if before is None or hashlib.sha256(before).hexdigest() != expected_sha256:
            raise ValueError("Configuration changed outside this window. Reload before saving.")
    encoded = content.encode("utf-8")
    if before == encoded:
        return {"changed": False, "backup": None}
    raw = parse_text(content, target)
    if raw.get("version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported config version {raw.get('version')!r}")
    temporary = None
    backup = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=target.suffix,
                                         prefix=".vispa_config_", dir=target.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        loaded = load(temporary)
        scopes = loaded.get("visual_toolkit", {}).get("settings", {})
        legacy = loaded.get("sources", {}).get("brain_view", {}).get("settings", {})
        for scope in SCOPES:
            if scopes.get(scope) or (scope == "brain-view" and legacy):
                resolve_settings(scope, config=loaded)
        if before is not None:
            backups = target.parent / "config_backups"
            backups.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup = backups / f"{target.stem}_{stamp}{target.suffix}"
            with backup.open("xb") as saved:
                saved.write(before)
        current = target.read_bytes() if target.exists() else None
        if current != before:
            raise ValueError("Configuration changed outside this window. Reload before saving.")
        os.replace(temporary, target)
        temporary = None
    except Exception:
        if backup is not None and backup.exists() and temporary is not None:
            backup.unlink()
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"changed": True, "backup": backup}


if __name__ == "__main__":
    raise SystemExit(main())
