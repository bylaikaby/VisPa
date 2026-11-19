"""Start region analysis from animal and neuron IDs.

``run_analysis`` fills the SWC cache from IONData when needed, then writes one
workbook per animal. Several animals are one grouped run. ``analyze_one`` remains
the single-SWC metric used when a local file is already declared.

Version: 0.2.1 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-10-25: core.py measured one declared SWC (analyze_one).
- 2026-11-10: Renamed one_neuron.py, then run_analysis.py.
- 2026-11-10: remap run --case animal_id/neuron.swc fills the cache from IONData and writes one workbook per animal. Several animals produce one grouped receipt.
Status: candidate
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import math
from datetime import datetime, timezone
from dataclasses import dataclass

from ._version import __version__

import nibabel as nib
import numpy as np
import pandas as pd

from .region_analysis import RegionAnalysisPerNeuron, parse_swc


@dataclass(frozen=True)
class PreparedAtlas:
    atlas: Path
    atlas_key: Path
    atlas_level: int
    volume: np.ndarray
    key: pd.DataFrame
    atlas_sha256: str
    key_sha256: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _graph(rows: list[tuple], scale: float, offset: tuple[float, float, float]):
    """One edge per branch preserves every edge once and input leaf ordering."""
    nodes = {}
    for node_id, kind, x, y, z, radius, parent in rows:
        mapped = (np.array((x, y, z), dtype=float) / scale) + np.array(offset)
        nodes[node_id] = SimpleNamespace(id=node_id, kind=kind, radius=radius,
                                         parent=parent, x_nii=mapped[0],
                                         y_nii=mapped[1], z_nii=mapped[2])
    children = {node_id: [] for node_id in nodes}
    root = None
    branches = []
    for node_id, *_rest, parent in rows:
        if parent == -1:
            root = nodes[node_id]
        else:
            children[parent].append(node_id)
            branches.append([nodes[parent], nodes[node_id]])
    leaves = [nodes[node_id] for node_id, *_ in rows if not children[node_id]]
    return SimpleNamespace(root=root, branches=branches, terminal_nodes=leaves), len(nodes)


def prepare_atlas(*, atlas: Path, atlas_key: Path, atlas_level: int = 6) -> PreparedAtlas:
    """Validate and cache one atlas level/key/hash for bounded repeated analysis."""
    atlas, atlas_key = Path(atlas), Path(atlas_key)
    if not isinstance(atlas_level, int) or isinstance(atlas_level, bool) or not 1 <= atlas_level <= 6:
        raise ValueError("Atlas level must be an integer from 1 to 6")
    for path in (atlas, atlas_key):
        if not path.is_file():
            raise FileNotFoundError(path)
    image = nib.load(str(atlas))
    volume = np.asarray(image.dataobj)
    if volume.ndim == 5 and volume.shape[3] == 1 and volume.shape[4] >= atlas_level:
        volume = volume[:, :, :, 0, atlas_level - 1]
    if volume.ndim != 3 or any(size == 0 for size in volume.shape):
        raise ValueError("Atlas must be 3D or a 5D hierarchy containing the selected level")
    if not np.isfinite(volume).all() or (volume < 0).any() or not np.equal(volume, np.floor(volume)).all():
        raise ValueError("Atlas labels must be finite nonnegative integers")
    key = pd.read_csv(atlas_key, sep=None, engine="python")
    return PreparedAtlas(atlas.resolve(), atlas_key.resolve(), atlas_level, volume, key,
                         sha256(atlas), sha256(atlas_key))


def analyze_one(*, swc: Path, atlas: Path, atlas_key: Path, sample_id: str,
                neuron_id: str, declared_space: str, coordinate_scale: float,
                coordinate_offset: tuple[float, float, float] = (0, 0, 0),
                atlas_level: int = 6, prepared_atlas: PreparedAtlas | None = None) -> dict:
    """Analyze one declared SWC on an explicitly selected 3D atlas voxel grid.

    ``coordinate_scale`` and ``coordinate_offset`` describe source XYZ -> voxel
    index mapping. They do not establish anatomical registration or units.
    """
    paths = [Path(swc), Path(atlas), Path(atlas_key)]
    if (not sample_id.strip() or sample_id != sample_id.strip() or not neuron_id.strip()
            or neuron_id != neuron_id.strip() or Path(neuron_id).name != neuron_id):
        raise ValueError("Sample and neuron identity must be nonempty; neuron ID must be a basename")
    if Path(swc).name != neuron_id:
        raise ValueError("Neuron ID must exactly match SWC basename")
    if not declared_space.strip():
        raise ValueError("Declare the atlas/source mapping space")
    if not math.isfinite(coordinate_scale) or coordinate_scale <= 0:
        raise ValueError("Coordinate scale must be finite and positive")
    if len(coordinate_offset) != 3 or not all(math.isfinite(v) for v in coordinate_offset):
        raise ValueError("Coordinate offset must have three finite values")
    if not isinstance(atlas_level, int) or isinstance(atlas_level, bool) or not 1 <= atlas_level <= 6:
        raise ValueError("Atlas level must be an integer from 1 to 6")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    if prepared_atlas is None:
        prepared_atlas = prepare_atlas(atlas=paths[1], atlas_key=paths[2], atlas_level=atlas_level)
    elif (prepared_atlas.atlas != paths[1].resolve() or
          prepared_atlas.atlas_key != paths[2].resolve() or
          prepared_atlas.atlas_level != atlas_level):
        raise ValueError("Prepared atlas does not match requested atlas/key/level")
    rows = parse_swc(paths[0].read_text(encoding="utf-8-sig"), str(paths[0]))
    graph, count = _graph(rows, coordinate_scale, coordinate_offset)
    analysis = RegionAnalysisPerNeuron(graph, prepared_atlas.volume, prepared_atlas.key)
    analysis.run()
    regions = list(dict.fromkeys(item["region"] for item in analysis.terminal_regions))
    return {
        "schema": "remap.one_neuron.v1", "sample_id": sample_id, "neuron_id": neuron_id,
        "uid": f"{sample_id}::{neuron_id}",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_date": None,
        "declared_space": declared_space, "atlas_level": atlas_level,
        "coordinate_source_units": "unknown/unspecified; caller supplied numeric mapping only",
        "paths": {"swc": str(paths[0].resolve()), "atlas": str(paths[1].resolve()),
                  "atlas_key": str(paths[2].resolve())},
        "coordinate_mapping": {"source_xyz_divided_by": coordinate_scale,
                               "then_voxel_offset": list(coordinate_offset)},
        "source_sha256": {"swc": sha256(paths[0]), "atlas": prepared_atlas.atlas_sha256,
                          "atlas_key": prepared_atlas.key_sha256},
        "nodes": count, "graph_leaves_all_types": len(graph.terminal_nodes),
        "soma_region": analysis.soma_region, "terminal_regions": regions,
        "terminal_sites": [{"region": item["region"], "voxel": [int(v) for v in item["coords"]]}
                           for item in analysis.terminal_regions],
        "terminal_count_distinct_regions": len(regions),
        "total_length_atlas_voxels": analysis.neuron_total_length,
        "region_projection_length_atlas_voxels": analysis.mapped_brain_region_lengths,
        "qc_status": "technical candidate; anatomical registration unverified",
    }


def parse_cases(cases: list[str]) -> list[dict]:
    """Group ``animal_id/neuron.swc`` cases. One animal stays one workbook."""
    if not cases:
        raise ValueError("At least one animal/neuron case is required")
    grouped: dict[str, list[str]] = {}
    for case in cases:
        text = str(case).strip().replace("\\", "/")
        if text.count("/") != 1:
            raise ValueError("Each case must be animal_id/neuron.swc")
        animal_id, neuron_id = text.split("/", 1)
        if (not animal_id or animal_id != Path(animal_id).name or not neuron_id.endswith(".swc")
                or Path(neuron_id).name != neuron_id):
            raise ValueError("animal_id must be a bare id and neuron_id an SWC basename")
        neurons = grouped.setdefault(animal_id, [])
        if neuron_id not in neurons:
            neurons.append(neuron_id)
    return [{"animal_id": animal_id, "neuron_ids": neuron_ids} for animal_id, neuron_ids in grouped.items()]


def run_analysis(*, cases: list[str], config: dict | None = None, refresh: bool = False,
                 generate_plots: bool | None = None, swc_plots: str | None = None,
                 dry_run: bool = False) -> dict:
    """Run region analysis for one or more animals.

    ``cases`` are ``animal_id/neuron.swc``. Neurons that share an animal go into
    that animal's workbook. More than one animal writes a grouped receipt beside
    those workbooks. Missing SWCs are fetched from the profile IONData host.
    """
    from .config import as_population, load as load_config
    from .population_operator import plan_population, run_population
    from .region_analysis.neuron_loader import ensure_cached_swc

    animals = parse_cases(cases)
    loaded = config if config is not None else load_config()
    plans = []
    for animal in animals:
        settings = as_population(loaded, sample_id=animal["animal_id"], neuron_ids=animal["neuron_ids"])
        if refresh:
            settings["refresh_swc"] = True
        if generate_plots is not None:
            settings["generate_plots"] = generate_plots
        if swc_plots is not None:
            settings["swc_plots"] = swc_plots
        if not dry_run:
            host = settings.get("iondata_host")
            for neuron_id in settings["neuron_ids"]:
                ensure_cached_swc(
                    settings["sample_id"], neuron_id, settings["swc_source_dir"], host,
                    allow_download=bool(host), refresh=bool(settings.get("refresh_swc")),
                )
        plans.append(plan_population(settings))
    if dry_run:
        return {"schema": "remap.run_analysis.v1", "version": __version__, "dry_run": True,
                "animals": [{"animal_id": plan["sample_id"], "neuron_ids": plan["neuron_ids"],
                             "fetch_required": [name for name, item in plan["swcs"].items() if item["fetch_required"]]}
                            for plan in plans]}
    receipts = [run_population(plan) for plan in plans]
    if len(receipts) == 1:
        return receipts[0]
    output_base = Path(plans[0]["output_base"])
    grouped = {
        "schema": "remap.grouped_analysis.v1",
        "version": __version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "animals": [{"animal_id": plan["sample_id"], "neuron_ids": plan["neuron_ids"],
                     "workbook": receipt["workbook"], "rows": receipt["rows"],
                     "receipt": receipt["receipt"]}
                    for plan, receipt in zip(plans, receipts)],
    }
    receipt_path = output_base / "grouped_run_provenance.json"
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(grouped, indent=2), encoding="utf-8")
    grouped["receipt"] = str(receipt_path.resolve())
    return grouped
