"""Shared scoped settings discovery and validation for VisualToolkit.

Version: 1.11.0.dev8 (local/unreleased)
Last updated: 2026-10-23
Change history: ../../CHANGELOG.md
Status: candidate

This module composes existing validators; it does not own rendering defaults.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping, MutableMapping
from typing import Any

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
    from . import toolkit

    result = copy.deepcopy(toolkit.review_settings_schema())
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
    from . import opengl

    metadata = {
        "eye_direction": ("float[3]", "centered display direction", "finite vector; nonzero and not parallel to up"),
        "up": ("float[3]", "centered display direction", "finite vector; nonzero and not parallel to eye_direction"),
        "camera_distance_scale": ("number", "mesh-diagonal multiplier", "> 0; fit distance = scale × √3 × mesh diagonal"),
        "line_width": ("number", "pixels", "> 0; processed-neuron line width"),
        "soma_radius": ("number", "declared stored coordinate units", "> 0; no unit conversion is applied"),
        "background": ("float[3]", "normalized RGB", "each component in [0, 1]"),
        "mesh_color": ("float[3]", "normalized RGB", "each component in [0, 1]"),
        "neuron_color": ("float[3]", "normalized RGB", "each component in [0, 1]"),
        "window_size": ("integer[2]", "pixels (width, height)", "each dimension ≥ 100"),
    }
    settings = {}
    for key, default in opengl.DEFAULT_SETTINGS.items():
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
                "soma_radius": "Display radius for processed-neuron soma nodes.",
                "background": "Window and snapshot background color.",
                "mesh_color": "Brain mesh display color.",
                "neuron_color": "Processed-neuron display color.",
                "window_size": "Initial viewer window width and height.",
            }[key],
        }
    settings["camera_distance_scale"].update(minimum=0, minimum_exclusive=True)
    settings["line_width"].update(minimum=0, minimum_exclusive=True)
    settings["soma_radius"].update(minimum=0, minimum_exclusive=True)
    settings["window_size"].update(minimum=100, minimum_exclusive=False)
    for key in ("background", "mesh_color", "neuron_color"):
        settings[key].update(minimum=0, maximum=1)
    if config is not None:
        current = resolve_settings("brain-view", config=config)
        for key, spec in settings.items():
            spec["current"] = copy.deepcopy(current[key])
    return {"schema": "visual-toolkit.legacy-gl-settings.v1", "settings": settings}


def _montage_schema(config=None) -> dict[str, Any]:
    from . import volume_montage

    settings = copy.deepcopy(volume_montage.SETTING_SPECS)
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
    from .dataset_config import load

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
        from . import toolkit

        candidate = _deep_merge(toolkit.review_settings_snapshot(), base or {})
        known = set(toolkit.review_settings_schema()["settings"])
        prefixes = {".".join(path.split(".")[:index])
                    for path in known for index in range(1, len(path.split(".")))}
        unknown_base = _mapping_paths(base or {}) - known - prefixes
        if unknown_base:
            raise ValueError(f"unknown review setting(s) in base: {', '.join(sorted(unknown_base))}")
        toolkit.apply_setting_overrides(configured, settings=candidate)
        toolkit.apply_setting_overrides(parsed, settings=candidate)
        return candidate
    if scope == "brain-view":
        from . import opengl

        legacy_and_scoped = {**configured}
        if base is not None:
            legacy_and_scoped = {**copy.deepcopy(dict(base)), **legacy_and_scoped}
        return opengl.resolve_settings(legacy_and_scoped, parsed)
    from . import volume_montage

    configured_base = copy.deepcopy(dict(base)) if base is not None else {}
    configured_base.update(configured)
    return volume_montage.resolve_settings(parsed, base=configured_base)


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
        from . import toolkit

        resolve_settings(scope, parsed, config=config)  # validate the full layered result first
        loaded = _load_config(config) if config is not None else None
        updates = {**_settings_config(loaded, scope), **parsed}
        before = toolkit.review_settings_snapshot()
        normalized = toolkit.apply_setting_overrides(updates)
        changed = {}
        for key, value in normalized.items():
            prior = before
            for part in key.split("."):
                prior = prior[part]
            if _json_value(prior) != _json_value(value):
                changed[key] = _json_value(value)
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


__all__ = ["SCOPES", "parse_overrides", "settings_schema", "resolve_settings", "apply_settings", "config_source"]
