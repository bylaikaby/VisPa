"""Run region analysis and FNT clustering with current ReMAP, then publish a VisPa bulk list.

Version: 1.11.0.dev18 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
Status: candidate

The region step calls ReMAP's population planner. The FNT step calls ReMAP's
saved-score reader and average/complete/single linkage. Source SWC bytes are
only read. Publication can target an explicit fMOST share slot or a fresh
local root. VisPa review plots are a separate bulk command.

Operator:
  python -m batch.remap_stepwise --case batch/remap_stepwise.example.json --limit 1 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


FMOST_SHARE_BASE = r"\\10.102.8.200\microscopy_data\fMOST"
SHARE_SLOTS = {
    "remap_outputs": Path("remap_outputs"),
    "outputs": Path("outputs"),
    "resources": Path("resources") / "remap_stepwise",
}
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\Z")
_NEURON = re.compile(r"[A-Za-z0-9_-]+\.swc\Z", re.IGNORECASE)
_CASE_KEYS = {
    "schema", "run_id", "share_slot", "share_base", "allow_all",
    "region", "fnt", "soma", "vispa_config",
}
_REGION_KEYS = {
    "sample_id", "neuron_ids", "swc_source_dir", "atlas", "atlas_key", "template",
    "hemisphere_mask", "cortex_hierarchy_csv", "subcortical_hierarchy_csv",
    "atlas_level", "source_date", "registry_path", "source_id", "generate_plots",
    "coordinate_scale", "coordinate_offset", "declared_space", "source_units",
    "refined_soma",
}
_REQUIRED_REGION = (
    "atlas", "atlas_key", "template", "hemisphere_mask",
    "cortex_hierarchy_csv", "subcortical_hierarchy_csv",
)
_FNT_KEYS = {"distance", "joined_fnt", "k", "linkage", "symmetrization"}
_SOMA_KEYS = {"source", "raw_swc_dir", "units"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _token(value, label: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ValueError(f"{label} must be a short letter, digit, underscore or hyphen token")
    return value


def _neuron(value) -> str:
    if not isinstance(value, str) or not _NEURON.fullmatch(value):
        raise ValueError("Each neuron id must be an explicit .swc filename")
    return value


def _bool(value, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be true or false")
    return value


def _unknown(payload: dict, allowed: set[str], label: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"Unknown {label} key(s): {sorted(unknown)}")


def _path(value, base: Path, label: str, *, kind: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a path")
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    try:
        path = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} does not exist: {path}") from exc
    if kind == "file" and not path.is_file():
        raise ValueError(f"{label} must be a file")
    if kind == "dir" and not path.is_dir():
        raise ValueError(f"{label} must be a directory")
    return path


def _inside(child: Path, parent: Path) -> bool:
    child = Path(child).resolve()
    parent = Path(parent).resolve()
    return child == parent or parent in child.parents


def share_run_path(base: str, slot: str, sample: str, run_id: str) -> Path:
    """Resolve one run directory under a named fMOST slot."""
    if slot not in SHARE_SLOTS:
        raise ValueError(
            "share_slot must be remap_outputs, outputs, or resources")
    sample = _token(sample, "sample_id")
    run_id = _token(run_id, "run_id")
    if not isinstance(base, str) or not base.strip():
        raise ValueError("share_base must be the fMOST share root")
    relative = SHARE_SLOTS[slot] / sample / run_id
    if slot == "resources" and tuple(SHARE_SLOTS[slot].parts[:2]) != ("resources", "remap_stepwise"):
        raise ValueError("resources publication stays under resources/remap_stepwise")
    base_path = Path(base).expanduser()
    try:
        base_resolved = base_path.resolve()
        destination = (base_resolved / relative).resolve()
    except OSError:
        base_resolved = base_path
        destination = base_path / relative
    if not _inside(destination, base_resolved):
        raise ValueError("Share destination escapes the declared fMOST base")
    return destination


def remap_version_supported(text: str) -> bool:
    """Accept ReMAP 0.1.0.dev4 and any later 0.1.0 or newer release."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?", str(text).strip())
    if match is None:
        return False
    base = tuple(int(match.group(index)) for index in range(1, 4))
    if base > (0, 1, 0):
        return True
    if base < (0, 1, 0):
        return False
    if match.group(4) is None:
        return True
    return int(match.group(4)) >= 4


def resolve_remap(importer=None):
    """Import the current ReMAP population and FNT functions."""
    if importer is None:
        def importer():
            from remap import __version__ as remap_version
            from remap.clustering_validation import read_fnt_distances, safe_linkage
            from remap.population_operator import plan_population, run_population
            from scipy.cluster.hierarchy import fcluster
            return {
                "version": remap_version,
                "plan_population": plan_population,
                "run_population": run_population,
                "read_fnt_distances": read_fnt_distances,
                "safe_linkage": safe_linkage,
                "fcluster": fcluster,
            }
    try:
        api = importer()
    except ImportError as exc:
        raise RuntimeError(
            "Region analysis and FNT clustering need ReMAP 0.1.0.dev4 or newer, "
            "with its pandas, openpyxl and scipy dependencies, importable in this Python"
        ) from exc
    version = str(api.get("version", ""))
    if not remap_version_supported(version):
        raise RuntimeError(f"ReMAP {version or 'unknown'} is older than the required 0.1.0.dev4")
    return api


def load_case(case_path: Path) -> dict:
    """Validate one stepwise case and resolve its local inputs."""
    case_path = Path(case_path).resolve(strict=True)
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Stepwise case must be a JSON object")
    _unknown(payload, _CASE_KEYS, "case")
    if payload.get("schema") != "vispa.remap_stepwise.v1":
        raise ValueError("Expected vispa.remap_stepwise.v1 settings")
    folder = case_path.parent
    region = payload.get("region")
    fnt = payload.get("fnt")
    soma = payload.get("soma")
    if not isinstance(region, dict) or not isinstance(fnt, dict) or not isinstance(soma, dict):
        raise ValueError("region, fnt and soma must be JSON objects")
    _unknown(region, _REGION_KEYS, "region")
    _unknown(fnt, _FNT_KEYS, "fnt")
    _unknown(soma, _SOMA_KEYS, "soma")
    sample = _token(region.get("sample_id"), "sample_id")
    names = region.get("neuron_ids")
    if not isinstance(names, list) or not names:
        raise ValueError("region.neuron_ids must be a nonempty list")
    neurons = [_neuron(name) for name in names]
    if len(neurons) != len(set(neurons)):
        raise ValueError("region.neuron_ids must be unique")
    slot = payload.get("share_slot")
    if slot not in SHARE_SLOTS:
        raise ValueError("share_slot must be remap_outputs, outputs, or resources")
    share_base = payload.get("share_base", FMOST_SHARE_BASE)
    run_id = _token(payload.get("run_id"), "run_id")
    swc_dir = _path(region.get("swc_source_dir"), folder, "region.swc_source_dir", kind="dir")
    inputs = {
        name: _path(region.get(name), folder, f"region.{name}", kind="file")
        for name in _REQUIRED_REGION
    }
    refined = region.get("refined_soma")
    if refined is not None:
        inputs["refined_soma"] = _path(refined, folder, "region.refined_soma", kind="file")
    missing = [name for name in neurons if not (swc_dir / name).is_file() or (swc_dir / name).parent != swc_dir]
    if missing:
        raise FileNotFoundError(
            "Every region neuron must be a file directly inside swc_source_dir: "
            + ", ".join(missing))
    linkage = fnt.get("linkage", "average")
    symmetrization = fnt.get("symmetrization", "max")
    if linkage not in {"average", "complete", "single"}:
        raise ValueError("fnt.linkage must be average, complete, or single")
    if symmetrization not in {"max", "mean"}:
        raise ValueError("fnt.symmetrization must be max or mean")
    k = fnt.get("k")
    if isinstance(k, bool) or not isinstance(k, int) or k < 2:
        raise ValueError("fnt.k must be an integer of at least 2")
    source = soma.get("source")
    if source not in {"raw_swc_root", "summary_phys"}:
        raise ValueError("soma.source must be raw_swc_root or summary_phys")
    units = soma.get("units")
    if not isinstance(units, str) or not units.strip():
        raise ValueError("soma.units must declare the coordinate units used for VisPa review")
    raw_dir = None
    if source == "raw_swc_root":
        raw_dir = _path(soma.get("raw_swc_dir"), folder, "soma.raw_swc_dir", kind="dir")
    elif "raw_swc_dir" in soma:
        raise ValueError("soma.raw_swc_dir is only used when soma.source is raw_swc_root")
    level = region.get("atlas_level", 6)
    if isinstance(level, bool) or not isinstance(level, int) or level != 6:
        raise ValueError("region.atlas_level must be 6 for the current ReMAP population contract")
    declared_space = region.get("declared_space")
    if not isinstance(declared_space, str) or not declared_space.strip():
        raise ValueError("region.declared_space must be a nonempty caller declaration")
    config_path = None
    if payload.get("vispa_config") is not None:
        config_path = _path(payload["vispa_config"], folder, "vispa_config", kind="file")
    declared = share_run_path(share_base, slot, sample, run_id)
    return {
        "schema": payload["schema"],
        "case_path": str(case_path),
        "case_dir": str(folder),
        "case_sha256": _sha256(case_path),
        "run_id": run_id,
        "share_slot": slot,
        "share_base": share_base,
        "declared_share": str(declared),
        "allow_all": _bool(payload.get("allow_all", False), "allow_all"),
        "sample_id": sample,
        "neuron_ids": neurons,
        "swc_source_dir": str(swc_dir),
        "region_inputs": {name: str(path) for name, path in inputs.items()},
        "region_settings": {
            "atlas_level": level,
            "source_date": region.get("source_date"),
            "registry_path": region.get("registry_path"),
            "source_id": region.get("source_id"),
            "generate_plots": _bool(region.get("generate_plots", False), "region.generate_plots"),
            "coordinate_scale": region.get("coordinate_scale", 250),
            "coordinate_offset": region.get("coordinate_offset", [0, 0, 0]),
            "declared_space": declared_space,
            "source_units": region.get("source_units"),
        },
        "fnt": {
            "distance": str(_path(fnt.get("distance"), folder, "fnt.distance", kind="file")),
            "joined_fnt": str(_path(fnt.get("joined_fnt"), folder, "fnt.joined_fnt", kind="file")),
            "k": k,
            "linkage": linkage,
            "symmetrization": symmetrization,
        },
        "soma": {"source": source, "units": units.strip(), "raw_swc_dir": None if raw_dir is None else str(raw_dir)},
        "vispa_config": None if config_path is None else str(config_path),
    }


def select_neurons(case: dict, limit: int | None, all_jobs: bool) -> list[str]:
    neurons = sorted(case["neuron_ids"])
    if all_jobs:
        if limit is not None or case["allow_all"] is not True:
            raise ValueError("--all requires allow_all=true and cannot use --limit")
        return neurons
    if limit is None or isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Use a positive --limit for bounded work, or explicitly opt in to --all")
    return neurons[:limit]


def _separated(root: Path, case: dict) -> None:
    case_dir = Path(case["case_dir"])
    protected = [case_dir, Path(case["swc_source_dir"])]
    if case["soma"]["raw_swc_dir"]:
        protected.append(Path(case["soma"]["raw_swc_dir"]))
    for folder in protected:
        if _inside(root, folder) or _inside(folder, root):
            raise ValueError("Write root must stay outside the case file, analysis SWCs and raw SWCs")


def choose_write_root(case: dict, output_root: Path | None, publish_share: bool) -> tuple[Path, str]:
    if output_root is not None and publish_share:
        raise ValueError("Choose either --output-root or --publish share")
    if publish_share:
        root = Path(case["declared_share"])
        mode = "share"
    elif output_root is not None:
        root = Path(output_root).expanduser().resolve()
        mode = "output_root"
    else:
        raise ValueError("Choose --output-root for a local run or --publish share for the declared fMOST slot")
    _separated(root, case)
    return root, mode


def build_region_config(case: dict, neurons: list[str], output_base: Path) -> dict:
    config = {
        "sample_id": case["sample_id"],
        "neuron_ids": list(neurons),
        "swc_source_dir": case["swc_source_dir"],
        "output_base": str(output_base),
        **case["region_inputs"],
        **case["region_settings"],
    }
    if config.get("registry_path") is None:
        config.pop("registry_path")
    if config.get("source_id") is None:
        config.pop("source_id")
    if config.get("source_date") is None:
        config.pop("source_date", None)
    return config


def read_swc_root(path: Path) -> tuple[float, float, float]:
    """Return the unique parent -1 node. The file is not rewritten."""
    roots = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 7:
            raise ValueError(f"Malformed SWC row in {path.name}")
        parent = float(parts[6])
        if parent == -1:
            coords = tuple(float(parts[index]) for index in (2, 3, 4))
            if not all(coord == coord and abs(coord) != float("inf") for coord in coords):
                raise ValueError(f"SWC root coordinates must be finite in {path.name}")
            roots.append(coords)
    if len(roots) != 1:
        raise ValueError(f"{path.name} must contain exactly one parent -1 root")
    return roots[0]


def marker_aliases(sample: str, neuron_id: str) -> list[str]:
    stem = neuron_id[:-4]
    return [neuron_id, stem, f"{sample}_{stem}", f"{sample}-{stem}",
            f"{sample}_{neuron_id}", f"{sample}-{neuron_id}"]


def match_clusters(sample: str, neurons: list[str], marker_to_cluster: dict[str, int]) -> list[dict]:
    used = {}
    matched = []
    for neuron in neurons:
        found = None
        for alias in marker_aliases(sample, neuron):
            if alias in marker_to_cluster:
                found = alias
                break
        if found is not None:
            if found in used:
                raise ValueError(f"FNT marker {found} matches both {used[found]} and {neuron}")
            used[found] = neuron
        matched.append({
            "neuron_id": neuron,
            "fnt_marker": found,
            "fnt_cluster": None if found is None else int(marker_to_cluster[found]),
        })
    return matched


def read_summary_workbook(path: Path) -> list[dict]:
    import pandas as pd
    frame = pd.read_excel(path, sheet_name="Summary")
    return frame.to_dict(orient="records")


def _summary_rows(rows: list[dict], sample: str, neurons: list[str]) -> dict[str, dict]:
    found = {}
    for row in rows:
        if str(row.get("SampleID")) != sample:
            raise ValueError("Summary contains a row from another sample")
        neuron = str(row.get("NeuronID"))
        if neuron in found:
            raise ValueError(f"Summary repeats {neuron}")
        found[neuron] = row
    if set(found) != set(neurons):
        raise ValueError("Summary neurons differ from the selected region cohort")
    return found


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or abs(number) == float("inf"):
        return None
    return number


def soma_for_neuron(case: dict, neuron: str, row: dict) -> dict:
    """Resolve the review soma without changing either SWC."""
    source = case["soma"]["source"]
    record = {"soma_xyz": None, "render_ready": False, "soma_error": None, "raw_swc_sha256": None}
    if source == "summary_phys":
        coords = [_finite_number(row.get(name)) for name in ("Soma_Phys_X", "Soma_Phys_Y", "Soma_Phys_Z")]
        if any(value is None for value in coords):
            record["soma_error"] = "Summary Soma_Phys_X/Y/Z are missing"
            return record
        record["soma_xyz"] = coords
        record["render_ready"] = True
        return record
    path = Path(case["soma"]["raw_swc_dir"]) / neuron
    before = None
    try:
        if path.parent != Path(case["soma"]["raw_swc_dir"]) or not path.is_file():
            raise FileNotFoundError(f"Raw SWC is not directly inside soma.raw_swc_dir: {neuron}")
        before = path.read_bytes()
        record["raw_swc_sha256"] = hashlib.sha256(before).hexdigest()
        record["soma_xyz"] = [float(value) for value in read_swc_root(path)]
        record["render_ready"] = True
    except (OSError, ValueError) as exc:
        record["soma_error"] = str(exc)
    finally:
        if before is not None and path.is_file() and path.read_bytes() != before:
            raise RuntimeError(f"Raw SWC bytes changed while reading {path}")
    return record


def _region_label(row: dict):
    value = row.get("Soma_Region")
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def build_bulk_jobs(case: dict, neurons: list[str], rows: list[dict], matches: list[dict],
                    write_root: Path, receipt_path: Path) -> dict:
    by_id = _summary_rows(rows, case["sample_id"], neurons)
    by_neuron = {item["neuron_id"]: item for item in matches}
    jobs = []
    for neuron in neurons:
        row = by_id[neuron]
        soma = soma_for_neuron(case, neuron, row)
        match = by_neuron[neuron]
        jobs.append({
            "sample_id": case["sample_id"],
            "neuron_id": neuron,
            "soma_region": _region_label(row),
            "soma_xyz": soma["soma_xyz"],
            "soma_units": case["soma"]["units"],
            "soma_coordinate_source": case["soma"]["source"],
            "raw_swc_sha256": soma["raw_swc_sha256"],
            "fnt_marker": match["fnt_marker"],
            "fnt_cluster": match["fnt_cluster"],
            "render_ready": soma["render_ready"],
            "soma_error": soma["soma_error"],
        })
    return {
        "schema": "vispa.review_bulk.v1",
        "sample_id": case["sample_id"],
        "vispa_config": case["vispa_config"],
        "source_stepwise_receipt": str(receipt_path),
        "suggested_plot_root": str(write_root.parent / f"{write_root.name}_vispa_plots"),
        "anatomical_acceptance": "not established",
        "swc_coordinates_rewritten": False,
        "jobs": jobs,
    }


def run_fnt(case: dict, api) -> dict:
    matrix, metadata = api["read_fnt_distances"](
        case["fnt"]["distance"], case["fnt"]["joined_fnt"],
        symmetrization=case["fnt"]["symmetrization"])
    linkage = api["safe_linkage"](matrix, method=case["fnt"]["linkage"])
    labels = api["fcluster"](linkage, case["fnt"]["k"], criterion="maxclust")
    markers = [str(item) for item in list(matrix.index)]
    clusters = [int(item) for item in list(labels)]
    if len(markers) != len(clusters) or len(markers) < 3 or len(set(markers)) != len(markers):
        raise ValueError("FNT clustering must return one unique label per joined marker, at least 3")
    rows = linkage.tolist() if hasattr(linkage, "tolist") else [list(row) for row in linkage]
    return {
        "schema": "remap.fnt_validation.v1",
        "neuron_ids": markers,
        "source_metadata": metadata,
        "linkage_rows": rows,
        "requested_k": case["fnt"]["k"],
        "cluster_labels": clusters,
        "linkage": case["fnt"]["linkage"],
        "symmetrization": case["fnt"]["symmetrization"],
        "method": (
            "saved FNT scores; explicit linkage and k; "
            "source SWCs are not rewritten"
        ),
    }


def _write_fnt(folder: Path, result: dict) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    path = folder / "linkage.json"
    _atomic_json(path, payload)
    assignments = folder / "assignments.csv"
    fd, temporary = tempfile.mkstemp(prefix=".assignments.", suffix=".part", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["marker", "cluster"])
            writer.writeheader()
            for marker, cluster in zip(result["neuron_ids"], result["cluster_labels"]):
                writer.writerow({"marker": marker, "cluster": cluster})
        os.replace(temporary, assignments)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"linkage_json": str(path), "linkage_sha256": _sha256(path),
            "assignments_csv": str(assignments), "assignments_sha256": _sha256(assignments),
            "n_neurons": len(result["neuron_ids"]), "requested_k": result["requested_k"],
            "linkage": result["linkage"], "symmetrization": result["symmetrization"]}


def plan_stepwise(case: dict, neurons: list[str], write_root: Path | None, write_mode: str,
                  api) -> dict:
    """Hash and preflight the selected case without creating the run directory."""
    root = write_root or Path(case["declared_share"])
    region_config = build_region_config(case, neurons, root / "region")
    region_plan = api["plan_population"](region_config)
    distance = Path(case["fnt"]["distance"])
    joined = Path(case["fnt"]["joined_fnt"])
    return {
        "schema": "vispa.remap_stepwise_plan.v1",
        "status": "dry_run",
        "write_mode": write_mode,
        "write_root": None if write_root is None else str(write_root),
        "declared_share": case["declared_share"],
        "share_slot": case["share_slot"],
        "sample_id": case["sample_id"],
        "run_id": case["run_id"],
        "selected_neurons": neurons,
        "region_plan": region_plan,
        "fnt_inputs": {
            "distance": str(distance),
            "distance_sha256": _sha256(distance),
            "joined_fnt": str(joined),
            "joined_fnt_sha256": _sha256(joined),
            "k": case["fnt"]["k"],
            "linkage": case["fnt"]["linkage"],
            "symmetrization": case["fnt"]["symmetrization"],
        },
        "soma": case["soma"],
        "swc_coordinates_rewritten": False,
        "anatomical_acceptance": "not established",
    }


def run_stepwise(case: dict, neurons: list[str], write_root: Path, write_mode: str, *,
                 dry_run: bool, remap_api=None, summary_reader=None) -> dict:
    write_root = Path(write_root)
    _separated(write_root, case)
    api = resolve_remap() if remap_api is None else remap_api
    if dry_run:
        return plan_stepwise(case, neurons, write_root, write_mode, api)
    if write_root.exists():
        raise FileExistsError("Fresh output directory required; existing runs are not overwritten")
    write_root.mkdir(parents=True)
    receipt_path = write_root / "stepwise_receipt.json"
    result = {
        "schema": "vispa.remap_stepwise_receipt.v1",
        "status": "in_progress",
        "write_mode": write_mode,
        "write_root": str(write_root),
        "declared_share": case["declared_share"],
        "share_slot": case["share_slot"],
        "share_base": case["share_base"],
        "sample_id": case["sample_id"],
        "run_id": case["run_id"],
        "case_path": case["case_path"],
        "case_sha256": case["case_sha256"],
        "selected_neurons": neurons,
        "remap_version": api.get("version"),
        "swc_coordinates_rewritten": False,
        "anatomical_acceptance": "not established",
        "error": None,
    }
    try:
        region_config = build_region_config(case, neurons, write_root / "region")
        region_plan = api["plan_population"](region_config)
        region_receipt = api["run_population"](region_plan)
        result["region_receipt"] = region_receipt
        fnt_result = run_fnt(case, api)
        result["fnt"] = _write_fnt(write_root / "fnt", fnt_result)
        reader = summary_reader or read_summary_workbook
        workbook = Path(region_receipt["workbook"])
        rows = reader(workbook)
        matches = match_clusters(
            case["sample_id"], neurons,
            dict(zip(fnt_result["neuron_ids"], fnt_result["cluster_labels"])))
        jobs = build_bulk_jobs(case, neurons, rows, matches, write_root, receipt_path)
        jobs_path = write_root / "vispa_bulk_jobs.json"
        _atomic_json(jobs_path, jobs)
        result["vispa_bulk_jobs"] = str(jobs_path)
        result["vispa_bulk_jobs_sha256"] = _sha256(jobs_path)
        result["render_ready_count"] = sum(1 for job in jobs["jobs"] if job["render_ready"])
        result["status"] = "pass"
    except Exception as exc:
        result["status"] = "partial_or_failed"
        result["error"] = str(exc)
    _atomic_json(receipt_path, result)
    result["receipt"] = str(receipt_path)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--publish", choices=["share"])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--limit", type=int)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        case = load_case(args.case)
        neurons = select_neurons(case, args.limit, args.all)
        if args.dry_run and args.output_root is None and args.publish is None:
            result = plan_stepwise(case, neurons, None, "undeclared", resolve_remap())
        else:
            root, mode = choose_write_root(case, args.output_root, args.publish == "share")
            result = run_stepwise(case, neurons, root, mode, dry_run=args.dry_run)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError, ImportError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"dry_run", "pass"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
