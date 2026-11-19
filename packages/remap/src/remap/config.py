"""Load the packaged ReMAP profile.

The profile is stored in the package, in the same role as VisPa's packaged
YAML: resources, cache, and output. REMAP_CONFIG can point at another file.

Version: 0.1.0.dev27 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-10: Packaged YAML profile for resources, cache, and output.
Status: candidate
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def packaged_config() -> Path:
    """Return the YAML profile shipped inside this package."""
    return Path(__file__).resolve().parent / "configs" / "remap_config.yaml"


def load(path=None) -> dict:
    """Read the packaged profile, or the file given by path or REMAP_CONFIG."""
    selected = Path(path or os.environ.get("REMAP_CONFIG") or packaged_config())
    text = selected.read_text(encoding="utf-8")
    if selected.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"ReMAP config must be a mapping: {selected}")
    data["config_path"] = str(selected.resolve())
    return data


def as_population(config: dict, *, sample_id: str, neuron_ids: list[str]) -> dict:
    """Turn a resources/cache/output profile into the population worker settings."""
    if "resources" not in config and "cache" not in config and "output" not in config:
        return config
    resources = config.get("resources") or {}
    cache = config.get("cache") or {}
    output = config.get("output") or {}
    if not sample_id or not neuron_ids:
        raise ValueError("A packaged profile needs --sample-id and --neuron-id")
    swc_root = cache.get("swc")
    if not swc_root:
        raise ValueError("cache.swc is required")
    return {
        "sample_id": sample_id,
        "neuron_ids": list(neuron_ids),
        "swc_source_dir": str(Path(swc_root) / sample_id),
        "iondata_host": resources.get("iondata_host"),
        "atlas": resources.get("atlas"),
        "atlas_key": resources.get("atlas_key"),
        "template": resources.get("template"),
        "hemisphere_mask": resources.get("hemisphere_mask"),
        "cortex_hierarchy_csv": resources.get("cortex_hierarchy_csv"),
        "subcortical_hierarchy_csv": resources.get("subcortical_hierarchy_csv"),
        "declared_space": resources.get("declared_space") or "NMT_v2.1_sym atlas voxel index",
        "output_base": output.get("root"),
        "generate_plots": bool(output.get("generate_plots", False)),
        "swc_plots": "off" if output.get("swc_plots") in {None, False, "off"} else str(output.get("swc_plots")),
        "refresh_swc": bool(output.get("refresh_swc", False)),
        "coordinate_scale": 250,
        "coordinate_offset": [0, 0, 0],
        "source_units": None,
        "source_date": None,
    }
