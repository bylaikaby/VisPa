"""Load explicit, portable VisPa dataset configuration.

Version: 1.11.0.dev4 (local/unreleased)
Last updated: 2026-10-23
Change history: ../../CHANGELOG.md
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
from pathlib import Path
from pathlib import PureWindowsPath

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


def _template_bytes() -> bytes:
    from importlib.resources import files

    return files("vispa").joinpath("default_config.yaml").read_bytes()


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
    unknown_fnt = set(fnt_tracer) - {"executable", "project_root", "auto_download",
                                     "cache_root", "server_base_url", "catalog_base_url",
                                     "timeout_seconds", "max_response_bytes"}
    if unknown_fnt:
        raise ValueError(
            f"visual_toolkit.fnt_tracer has unknown key(s): {sorted(unknown_fnt)}")
    visual_toolkit["fnt_tracer"] = {
        key: (_resolve(fnt_tracer.get(key), configured_base)
              if fnt_tracer.get(key) else None)
        for key in ("executable", "project_root")}
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
        from urllib.parse import urlsplit
        if not isinstance(example, dict):
            raise ValueError("sources.public_example must be a mapping")
        example = dict(example)
        for key in ("source_url", "metadata_url"):
            value = example.get(key)
            parsed = urlsplit(value) if isinstance(value, str) else None
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
        sources["public_example"] = example
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
    from .settings import resolve_settings

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
    from .settings import SCOPES, resolve_settings, settings_schema

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
        raw = _parse_config_bytes(_template_bytes(), Path("default_config.yaml"))
        loaded = None
        source_label = "package:vispa/default_config.yaml"
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


if __name__ == "__main__":
    raise SystemExit(main())
