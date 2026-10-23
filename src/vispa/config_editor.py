"""Lossless form projection for the common VisPa configuration fields.

Version: 1.11.0.dev7 (local/unreleased)
Last updated: 2026-10-23
Change history: ../../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path


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
