"""Designated fMOST share atlas profile copied from VisPa's DEB config.

Version: 0.1.0.dev11 (local/unreleased)
Last updated: 2026-11-09
Change history:
- 2026-11-09: Designated fMOST share atlas from VisPa config_deb.yaml. Explicit paths still win.
Status: candidate

The packaged YAML records VisPa ``sources.atlas`` paths. It does not contain
NIfTI or key bytes. Explicit caller paths replace these defaults.
"""
from __future__ import annotations

from functools import lru_cache
import copy
import os
from importlib.resources import files

import yaml


PROFILE_NAME = "config_deb.yaml"
ATLAS_TREE = (
    r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\atlas"
    r"\NMT_v2.1_sym"
)
SIBLING_ATLAS_TREE = r"\\10.102.8.200\microscopy_data\fMOST\resources\atlas"
POPULATION_FIELDS = {
    "atlas": "root",
    "atlas_key": "key",
    "hemisphere_mask": "hemisphere_mask",
}
NOT_DESIGNATED = ("template", "cortex_hierarchy_csv", "subcortical_hierarchy_csv")
_ATLAS_FIELDS = ("root", "key", "hemisphere_mask", "version", "coordinate_scale")


def _read_profile_text() -> str:
    resource = files("remap.configs").joinpath(PROFILE_NAME)
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", PROFILE_NAME)
        with open(fallback, encoding="utf-8") as stream:
            return stream.read()


def validate_share_atlas_path(value: str, field: str) -> str:
    """Accept one file under ``resources\\dependencies\\atlas`` only."""
    if not isinstance(value, str):
        raise ValueError(f"sources.atlas.{field} must be a UNC path")
    if value == SIBLING_ATLAS_TREE or value.startswith(SIBLING_ATLAS_TREE + "\\"):
        raise ValueError(
            f"sources.atlas.{field} must use the fMOST resources\\dependencies\\atlas tree")
    prefix = ATLAS_TREE + "\\"
    name = value[len(prefix):] if value.startswith(prefix) else ""
    if not name or "\\" in name or "/" in name or ".." in name:
        raise ValueError(f"sources.atlas.{field} must be a file in {ATLAS_TREE}")
    return value


@lru_cache(maxsize=1)
def _load_profile() -> dict:
    text = _read_profile_text()
    if "projectome_analysis" in text or "VisPa_publish" in text:
        raise ValueError(
            "Designated atlas profile must stay on the fMOST resources\\dependencies\\atlas tree")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("Designated atlas profile must be a YAML mapping")
    if data.get("schema") != "remap.deb_atlas_profile.v1" or data.get("profile") != "deb":
        raise ValueError("Designated atlas profile schema must be remap.deb_atlas_profile.v1")
    atlas = data.get("sources", {}).get("atlas") if isinstance(data.get("sources"), dict) else None
    if not isinstance(atlas, dict):
        raise ValueError("Designated atlas profile requires sources.atlas")
    missing = [field for field in _ATLAS_FIELDS if field not in atlas]
    if missing:
        raise ValueError(f"Designated atlas profile is missing {missing}")
    for field in ("root", "key", "hemisphere_mask"):
        validate_share_atlas_path(atlas[field], field)
    if atlas["version"] != "NMT_v2.1_sym":
        raise ValueError("Designated atlas version must be NMT_v2.1_sym")
    if atlas["coordinate_scale"] != 250 and atlas["coordinate_scale"] != 250.0:
        raise ValueError("Designated coordinate_scale must be 250")
    copied = data.get("copied_from")
    if not isinstance(copied, dict) or copied.get("path") != "src/vispa/configs/config_deb.yaml":
        raise ValueError("Designated atlas profile must cite VisPa config_deb.yaml")
    if tuple(data.get("not_designated", ())) != NOT_DESIGNATED:
        raise ValueError("Designated atlas profile must leave template and hierarchy CSVs undesignated")
    return data


def load_deb_atlas_profile() -> dict:
    """Return a copy of the packaged DEB atlas profile."""
    return copy.deepcopy(_load_profile())


def designated_population_paths() -> dict[str, str]:
    """Map ReMAP population inputs to VisPa ``sources.atlas`` share paths."""
    atlas = _load_profile()["sources"]["atlas"]
    return {name: atlas[field] for name, field in POPULATION_FIELDS.items()}


def designated_coordinate_scale_um() -> float:
    """Return the designated ``sources.atlas.coordinate_scale`` value."""
    return float(_load_profile()["sources"]["atlas"]["coordinate_scale"])


def designated_atlas_version() -> str:
    """Return the VisPa ``sources.atlas.version`` value."""
    return str(_load_profile()["sources"]["atlas"]["version"])


def atlas_profile_record(*, overrides: list[str] | None = None) -> dict:
    """Provenance recorded with a population plan."""
    data = _load_profile()
    copied = data["copied_from"]
    return {
        "schema": data["schema"],
        "profile": data["profile"],
        "config": f"src/remap/configs/{PROFILE_NAME}",
        "repository": copied["repository"],
        "vispa_path": copied["path"],
        "vispa_commit": copied["commit"],
        "vispa_config_version": copied["config_version"],
        "version": data["sources"]["atlas"]["version"],
        "coordinate_scale": data["sources"]["atlas"]["coordinate_scale"],
        "designated_inputs": list(POPULATION_FIELDS),
        "overrides": list(overrides or []),
    }


def apply_designated_atlas(config: dict) -> dict:
    """Fill omitted atlas, key, and hemisphere-mask paths from the DEB profile.

    An explicit non-null path is kept. ``template`` and hierarchy CSV keys are
    left untouched because VisPa's atlas block does not name them.
    """
    if not isinstance(config, dict):
        raise ValueError("population config must be a JSON object")
    merged = dict(config)
    for key, value in designated_population_paths().items():
        if key not in merged or merged[key] is None:
            merged[key] = value
            continue
        if not isinstance(merged[key], str) or not merged[key].strip():
            raise ValueError(f"{key} must be an explicit path when provided")
    return merged


def dormant_hierarchy_key_candidates(script_dir: str) -> list[str]:
    """Key paths for the unused ``add_hierarchy_columns`` fallback.

    The first path is the designated share key. Neighboring ``atlas`` folders
    remain local fallbacks. ``D:\\projectome_analysis`` is not searched.
    """
    return [
        designated_population_paths()["atlas_key"],
        os.path.join(script_dir, "..", "atlas", "ARM_key_all.txt"),
        os.path.join(script_dir, "atlas", "ARM_key_all.txt"),
        os.path.join("..", "atlas", "ARM_key_all.txt"),
    ]
