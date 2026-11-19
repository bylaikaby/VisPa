"""FNT production and exploratory morph clustering.

Server binaries are used when the shared bin directory is complete.
The local FNT 0.99.155 bin is the fallback.

Version: 0.2.2.dev2 (local/unreleased)
Last updated: 2026-11-18
Change history:
- 2026-11-18: Hash-verified prepared-distance runner with explicit extended timeout and failure-output retention.
- 2026-11-18: Explicit max_cases opt-in (default32, cap1000); compact hard-linked join inputs avoid Windows command-length limits without changing FNT processing.
- 2026-10-29: Legacy FNT producer.
- 2026-11-10: Moved under morph_clustering/. Server FNT bin first, local bin after 8 seconds. Intermediates go to the FNT cache.
- 2026-11-10: A run that never writes receipt.json removes only the output directory it created.
- 2026-11-17: Share validated ratio normalization with saved-score comparison.
Status: candidate
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import rankdata

from .clustering_validation import read_fnt_distances, validate_distance_matrix
from ..region_analysis import parse_swc
from .._version import __version__

TRANSFORMS = ("legacy_nodewise_fold", "none", "whole_neuron_reflect")
REPRESENTATIONS = ("raw", "log1p", "spearman_profile")
LINKAGES = ("average", "complete", "single", "ward_d2", "ward_presquared")
FNT_TOOLS = ("fnt-from-swc.exe", "fnt-decimate.exe", "fnt-join.exe", "fnt-dist.exe")
SERVER_FNT_BIN = Path(r"\\10.102.8.200\microscopy_data\fMOST\resources\dependencies\fnt\fnt-tracer-0.99.155\bin")
LOCAL_FNT_BIN = Path(r"C:\Users\laika_yan\Downloads\fnt-0.99.155\bin")
SERVER_REMAP_OUTPUTS = Path(r"\\10.102.8.200\microscopy_data\fMOST\remap_outputs")
SERVER_FNT_CACHE = Path(r"\\10.102.8.200\microscopy_data\fMOST\VisPa\cached_data\fnt")


def _complete_fnt_bin(directory: Path, timeout: float | None = None) -> bool:
    """Return whether all four FNT executables are present. A timeout treats a silent share as absent."""
    def present() -> bool:
        try:
            return directory.is_dir() and all((directory / name).is_file() for name in FNT_TOOLS)
        except OSError:
            return False
    if timeout is None:
        return present()
    done: dict[str, bool] = {}
    worker = threading.Thread(target=lambda: done.__setitem__("ok", present()), daemon=True)
    worker.start()
    worker.join(timeout)
    return bool(done.get("ok"))


def resolve_fnt_binaries(configured: str | None = None, *, server_timeout: float = 8) -> tuple[Path, str]:
    """Use the server FNT bin when it answers, otherwise the local copy."""
    if _complete_fnt_bin(SERVER_FNT_BIN, timeout=server_timeout):
        return SERVER_FNT_BIN, "server"
    if _complete_fnt_bin(LOCAL_FNT_BIN):
        return LOCAL_FNT_BIN, "local"
    if configured:
        chosen = Path(configured)
        if _complete_fnt_bin(chosen):
            return chosen.resolve(), "configured"
    tried = [str(SERVER_FNT_BIN), str(LOCAL_FNT_BIN)]
    if configured:
        tried.append(str(configured))
    raise FileNotFoundError("FNT executables were not found. Tried: " + "; ".join(tried))


def _discard_unreceipted(root: Path) -> None:
    """Remove an output directory this run created when it has no receipt.

    A finished directory, one that already contains ``receipt.json``, is left
    in place. Source SWCs are outside this directory.
    """
    if root.exists() and not (root / "receipt.json").is_file():
        shutil.rmtree(root, ignore_errors=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preprocess_swc(source: Path, destination: Path, mode: str, midline_x: float) -> dict:
    """Write one scoped copy; legacy mode matches the old nodewise rule."""
    if mode not in TRANSFORMS or not math.isfinite(midline_x):
        raise ValueError("Invalid FNT coordinate transform")
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    rows = parse_swc("".join(lines), str(source))
    root_x = next(row[2] for row in rows if row[6] == -1)
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#"):
            parts = line.split()
            if len(parts) != 7:
                raise ValueError(f"Expected seven-column SWC: {source}")
    changed = 0
    with destination.open("w", encoding="utf-8", newline="\n") as out:
        for line in lines:
            if not line.strip() or line.lstrip().startswith("#"):
                out.write(line)
                continue
            parts = line.split()
            x = float(parts[2])
            reflect = (mode == "legacy_nodewise_fold" and x > midline_x) or (
                mode == "whole_neuron_reflect" and root_x > midline_x
            )
            if reflect:
                parts[2] = str(2 * midline_x - x)
                changed += 1
            out.write(" ".join(parts) + "\n")
    return {"mode": mode, "midline_x": midline_x, "root_x": root_x,
            "reflected_nodes": changed, "output_sha256": sha256(destination)}


def validate_settings(config: dict, overrides: dict | None = None, *, offline: bool = False) -> dict:
    """Resolve public settings before any output is created."""
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    cfg = dict(config)
    allowed = {"workspace_root", "binary_dir", "output_root", "cache_root", "timeout_seconds",
               "cases", "cohort_table", "selected_uids", "preprocessing", "decimation", "clustering", "max_cases"}
    nested = {"preprocessing": {"mode", "midline_x"},
              "decimation": {"enabled", "distance", "area"},
              "clustering": {"enabled", "score_mode", "representation", "linkage",
                             "penalty_factor", "penalty_absolute", "candidate_k", "type_by_uid"},
              "cohort_table": {"path", "sample_id_column", "neuron_id_column",
                               "swc_path_column", "swc_sha256_column"}}
    unknown = set(cfg) - allowed
    if unknown:
        raise ValueError(f"Unknown FNT config keys: {sorted(unknown)}")
    for section, keys in nested.items():
        if section in cfg:
            if not isinstance(cfg[section], dict):
                raise ValueError(f"{section} must be an object")
            unknown = set(cfg[section]) - keys
            if unknown:
                raise ValueError(f"Unknown {section} keys: {sorted(unknown)}")
    preprocess = {"mode": "legacy_nodewise_fold", "midline_x": 32000.0,
                  **cfg.get("preprocessing", {})}
    decimate = {"enabled": True, "distance": 5000.0, "area": 5000.0, **cfg.get("decimation", {})}
    cluster = {"enabled": False, "score_mode": "raw", "representation": "spearman_profile",
               "linkage": "ward_d2", "penalty_factor": 1.5, "penalty_absolute": 0.0, "candidate_k": [],
               "type_by_uid": {}, **cfg.get("clustering", {})}
    timeout_seconds = int(cfg.get("timeout_seconds", 600))
    if not 10 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be 10..3600")
    for key, value in overrides.items():
        if key in ("mode", "midline_x"):
            preprocess["mode" if key == "mode" else key] = value
        elif key in ("distance", "area"):
            decimate[key] = value
        elif key == "decimation_enabled":
            decimate["enabled"] = value
        elif key in ("score_mode", "representation", "linkage", "penalty_factor", "penalty_absolute", "candidate_k"):
            cluster[key] = value
        else:
            raise ValueError(f"Unknown override {key}")
    preprocess["midline_x"] = float(preprocess["midline_x"])
    decimate["distance"] = float(decimate["distance"])
    decimate["area"] = float(decimate["area"])
    cluster["penalty_factor"] = float(cluster["penalty_factor"])
    cluster["penalty_absolute"] = float(cluster["penalty_absolute"])
    if type(decimate["enabled"]) is not bool:
        raise ValueError("decimation.enabled must be a boolean")
    if type(cluster["enabled"]) is not bool:
        raise ValueError("clustering.enabled must be a boolean")
    if preprocess["mode"] not in TRANSFORMS or not math.isfinite(preprocess["midline_x"]):
        raise ValueError("Invalid preprocessing mode or midline")
    for key in ("distance", "area"):
        if not math.isfinite(decimate[key]) or decimate[key] <= 0:
            raise ValueError(f"Invalid decimation {key}")
    if cluster["score_mode"] not in ("raw", "ratio") or cluster["representation"] not in REPRESENTATIONS or cluster["linkage"] not in LINKAGES:
        raise ValueError("Invalid clustering mode")
    if not math.isfinite(cluster["penalty_factor"]) or cluster["penalty_factor"] < 0:
        raise ValueError("penalty_factor must be finite and nonnegative")
    if not math.isfinite(cluster["penalty_absolute"]) or cluster["penalty_absolute"] < 0 or (cluster["penalty_factor"] > 0 and cluster["penalty_absolute"] > 0):
        raise ValueError("penalty_absolute must be nonnegative and exclusive of penalty_factor")
    if not isinstance(cluster["candidate_k"], list) or len(set(cluster["candidate_k"])) != len(cluster["candidate_k"]) or any(type(k) is not int or k < 2 for k in cluster["candidate_k"]):
        raise ValueError("candidate_k must be unique integers >=2")
    if "cases" in cfg and "cohort_table" in cfg:
        raise ValueError("Choose cases or cohort_table, not both")
    cases = cfg.get("cases")
    table_source = None
    if cases is None and "cohort_table" in cfg:
        table = cfg["cohort_table"]
        table_path = Path(table["path"])
        if not table_path.is_file() or table_path.suffix.lower() not in (".csv", ".xlsx"):
            raise ValueError("cohort_table must be an existing CSV or XLSX")
        frame = pd.read_csv(table_path, dtype=str, keep_default_na=False) if table_path.suffix.lower() == ".csv" else pd.read_excel(table_path, dtype=str).fillna("")
        columns = {key: table.get(key + "_column", default) for key, default in (
            ("sample_id", "SampleID"), ("neuron_id", "NeuronID"),
            ("swc_path", "SWCPath"), ("swc_sha256", "SWCSHA256"))}
        if any(column not in frame.columns for column in columns.values()):
            raise ValueError("cohort_table is missing a declared identity/path/hash column")
        requested = cfg.get("selected_uids")
        if not isinstance(requested, list) or not requested or len(set(requested)) != len(requested):
            raise ValueError("cohort_table requires nonempty unique selected_uids")
        rows = {}
        for _, row in frame.iterrows():
            uid = str(row[columns["sample_id"]]) + "|" + str(row[columns["neuron_id"]])
            if uid in rows:
                raise ValueError(f"Duplicate UID in cohort table: {uid}")
            rows[uid] = {key: str(row[column]) for key, column in columns.items()}
        if any(uid not in rows for uid in requested):
            raise ValueError("selected_uids contains an identity missing from cohort_table")
        cases = [rows[uid] for uid in requested]
        table_source = {"path": str(table_path.resolve()), "sha256": sha256(table_path),
                        "columns": columns, "selected_uids": requested}
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty explicit list")
    max_cases = cfg.get("max_cases", 32)
    if type(max_cases) is not int or not 1 <= max_cases <= 1000:
        raise ValueError("max_cases must be an integer in 1..1000")
    if len(cases) > max_cases:
        raise ValueError(f"FNT pipeline accepts at most {max_cases} cases")
    ids = []
    resolved_cases = []
    for case in cases:
        if not isinstance(case, dict) or set(case) - {"sample_id", "neuron_id", "swc_path", "swc_sha256"}:
            raise ValueError("Invalid FNT case keys")
        sample, neuron = str(case["sample_id"]), str(case["neuron_id"])
        uid = f"{sample}|{neuron}"
        path = Path(case["swc_path"])
        if not re.fullmatch(r"[0-9a-f]{64}", str(case["swc_sha256"])):
            raise ValueError(f"Invalid source SHA-256: {uid}")
        if (not re.fullmatch(r"[A-Za-z0-9-]+", sample)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.swc", neuron)
                or ".." in neuron
                or (not offline and not path.is_file())):
            raise ValueError(f"Invalid case {uid}")
        current = case["swc_sha256"] if offline else sha256(path)
        if current != case["swc_sha256"]:
            raise ValueError(f"Source SWC hash mismatch: {uid}")
        ids.append(uid)
        resolved_cases.append({"uid": uid, "sample_id": sample, "neuron_id": neuron,
                               "swc_path": str(path.resolve()), "swc_sha256": current})
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate exact neuron UID")
    markers = [c["sample_id"] + "_" + c["neuron_id"].removesuffix(".swc") for c in resolved_cases]
    if len({m.casefold() for m in markers}) != len(markers):
        raise ValueError("Case-insensitive FNT output collision")
    if cluster["enabled"]:
        if len(cases) < 3 or any(k >= len(cases) for k in cluster["candidate_k"]):
            raise ValueError("Clustering requires >=3 cases and candidate_k below n")
        if (cluster["penalty_factor"] > 0 or cluster["penalty_absolute"] > 0) and set(cluster["type_by_uid"]) != set(ids):
            raise ValueError("Penalty requires one exact broad label per selected UID")
        if (cluster["penalty_factor"] > 0 or cluster["penalty_absolute"] > 0) and any(not isinstance(v, str) or not v.strip() for v in cluster["type_by_uid"].values()):
            raise ValueError("Penalty labels must be nonempty strings")
    output = _directory(cfg.get("output_root") or str(SERVER_REMAP_OUTPUTS))
    if cfg.get("cache_root"):
        cache = _directory(cfg["cache_root"])
    elif cfg.get("output_root") and not str(output).lower().startswith(str(SERVER_REMAP_OUTPUTS).lower()):
        cache = output / "fnt_cache"
    else:
        cache = SERVER_FNT_CACHE
    if offline:
        if "binary_dir" not in cfg:
            raise ValueError("offline FNT settings require binary_dir")
        binaries = Path(cfg["binary_dir"]).resolve()
        binary_source = "offline"
    else:
        binaries, binary_source = resolve_fnt_binaries(cfg.get("binary_dir"))
    tools = {}
    for name in FNT_TOOLS:
        path = binaries / name
        if not offline and not path.is_file():
            raise FileNotFoundError(path)
        tools[name] = {"path": str(path), "sha256": None if offline else sha256(path)}
    return {"max_cases": max_cases, "cases": resolved_cases, "cohort_table": table_source,
            "output_root": str(output), "cache_root": str(cache), "binary_dir": str(binaries),
            "binary_source": binary_source,
            "tools": tools, "preprocessing": preprocess, "decimation": decimate,
            "clustering": cluster, "timeout_seconds": timeout_seconds,
            "method_limit": "FNT 0.99.155 local decimator is not Gou gapr adaptive decimator; optional paper linkage/penalty do not establish paper reproduction",
            "source_config": cfg}


def _directory(value: str) -> Path:
    """Keep a UNC path literal. Resolving it would touch the share."""
    path = Path(value)
    return path if str(path).startswith("\\\\") else path.resolve()


def _command(args: list[Path | str], log: Path, timeout_seconds: int, *, cwd: Path | None = None) -> None:
    with log.open("ab") as stream:
        subprocess.run([str(arg) for arg in args], check=True, stdout=stream, stderr=stream,
                       timeout=timeout_seconds, cwd=cwd)


def _rename_fnt_marker(path: Path, marker: str) -> None:
    data = path.read_bytes()
    start = data.rfind(b" Neuron ")
    end = data.find(b"\n", start)
    if start < 0 or end < 0:
        raise ValueError(f"Missing FNT marker: {path}")
    patched = data[:start] + b" Neuron " + marker.encode("ascii") + data[end:]
    if patched != data:
        path.write_bytes(patched)


def _prepare_analysis_fnt(converted, destination, settings, executable, log, timeout):
    """Preserve legacy decimation by default; allow explicit geometry control."""
    if destination.exists():
        destination.unlink()
    if settings.get("enabled", True):
        _command([executable, "-d", settings["distance"], "-a", settings["area"],
                  converted, destination], log, timeout)
    else:
        destination.write_bytes(converted.read_bytes())


def analysis_matrix(raw: np.ndarray, representation: str, penalty_factor: float,
                    broad_labels: list[str] | None = None, penalty_absolute: float = 0.0) -> np.ndarray:
    base = validate_distance_matrix(raw)
    if representation == "raw":
        result = base.copy()
    elif representation == "log1p":
        result = np.log1p(base)
    elif representation == "spearman_profile":
        ranks = np.apply_along_axis(rankdata, 1, base)
        if np.any(np.std(ranks, axis=1) == 0):
            raise ValueError("Constant FNT distance profile")
        result = np.clip(1 - np.corrcoef(ranks), 0, 2)
        result = (result + result.T) / 2
    else:
        raise ValueError(representation)
    np.fill_diagonal(result, 0)
    if penalty_factor or penalty_absolute:
        if broad_labels is None or len(broad_labels) != len(result):
            raise ValueError("Penalty requires aligned broad labels")
        labels = np.asarray(broad_labels)
        result += (penalty_factor * result.max() + penalty_absolute) * (labels[:, None] != labels[None, :])
    return validate_distance_matrix(result)


def hierarchy(matrix: np.ndarray, method: str) -> np.ndarray:
    """ward_presquared follows installed Clustering.jl on squared inputs."""
    values = validate_distance_matrix(matrix)
    if method in ("average", "complete", "single"):
        return linkage(squareform(values), method=method)
    if method == "ward_d2":
        return linkage(squareform(values), method="ward")
    if method == "ward_presquared":
        tree = linkage(squareform(np.sqrt(values)), method="ward")
        tree[:, 2] **= 2
        return tree
    raise ValueError(method)


def ratio_matrix(distance: Path, values: np.ndarray) -> np.ndarray:
    """Normalize validated triangular FNT scores by Match + NoMatch."""
    with Path(distance).open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != len(values) * (len(values) + 1) // 2:
        raise ValueError("Ratio requires complete five-column triangular FNT output")
    ratios = np.full(values.shape, np.nan)
    for row in rows:
        i, j = int(row["I"]), int(row["J"])
        den = float(row["Match"]) + float(row["NoMatch"])
        if not math.isfinite(den) or den <= 0:
            raise ValueError("Invalid FNT normalization denominator")
        ratios[i, j] = ratios[j, i] = float(row["Score"]) / den
    np.fill_diagonal(ratios, 0)
    return validate_distance_matrix(ratios)

def analyze_saved_scores(distance: Path, joined: Path, identities: list[str], settings: dict) -> tuple[dict, dict]:
    """Analyze a hash-bound saved producer table without rerunning FNT binaries."""
    matrix, metadata = read_fnt_distances(distance, joined)
    markers = [uid.split("|")[0] + "_" + uid.split("|")[1].removesuffix(".swc") for uid in identities]
    if list(matrix.index) != markers:
        raise ValueError("Saved distance marker order differs from exact identities")
    values = matrix.to_numpy(float)
    if settings["score_mode"] == "ratio":
        values = ratio_matrix(distance, values)
    labels = [settings["type_by_uid"][uid] for uid in identities] if (settings["penalty_factor"] or settings["penalty_absolute"]) else None
    transformed = analysis_matrix(values, settings["representation"], settings["penalty_factor"], labels, settings["penalty_absolute"])
    tree = hierarchy(transformed, settings["linkage"])
    assignments = {str(k): fcluster(tree, k, criterion="maxclust").tolist()
                   for k in settings["candidate_k"]}
    result = {"identity_order": identities,
              "settings": {k: v for k, v in settings.items() if k != "type_by_uid"},
              "broad_labels": labels, "linkage_rows": tree.tolist(), "final_k": None,
              "candidate_assignments": assignments,
              "realized_k": {k: len(set(v)) for k, v in assignments.items()}}
    return result, metadata


def run_saved_analysis(producer_receipt: Path, plan: dict, dry_run: bool = False) -> dict:
    """Bind an existing complete producer receipt and publish one analysis variant."""
    saved = json.loads(producer_receipt.read_text(encoding="utf-8"))
    distance, joined = Path(saved["distance"]), Path(saved["joined_fnt"])
    if sha256(distance) != saved["distance_sha256"] or sha256(joined) != saved["joined_sha256"]:
        raise ValueError("Saved producer output hash mismatch")
    source_ids = [case["uid"] for case in saved["cases"]]
    if source_ids != [case["uid"] for case in plan["cases"]]:
        raise ValueError("Saved producer and requested identities/order differ")
    if not plan["clustering"]["enabled"]:
        raise ValueError("Saved-score analysis requires clustering.enabled=true")
    result, metadata = analyze_saved_scores(distance, joined, source_ids, plan["clustering"])
    output = Path(plan["output_root"])
    receipt = {"schema": "remap.fnt_analysis.v1", "version": __version__,
               "producer_receipt": str(producer_receipt.resolve()),
               "producer_receipt_sha256": sha256(producer_receipt),
               "distance_sha256": saved["distance_sha256"], "joined_sha256": saved["joined_sha256"],
               "identity_order": source_ids, "distance_metadata": metadata,
               "settings": plan["clustering"], "final_k": None}
    if dry_run:
        return {"plan": plan, "analysis_receipt": receipt, "candidate_hierarchy": result}
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    try:
        hierarchy_path = output / "candidate_hierarchy.json"
        hierarchy_path.write_text(json.dumps(result, indent=2))
        receipt["candidate_hierarchy_sha256"] = sha256(hierarchy_path)
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2))
    except Exception:
        _discard_unreceipted(output)
        raise
    return receipt


def run_pipeline(plan: dict) -> dict:
    limit = plan.get("max_cases", 32)
    if type(limit) is not int or not 1 <= limit <= 1000 or not 1 <= len(plan["cases"]) <= limit:
        raise ValueError(f"FNT pipeline accepts 1..{limit} cases; invalid max_cases or count")
    root = Path(plan["output_root"])
    cache = Path(plan.get("cache_root") or root / "inputs")
    if root.exists():
        raise FileExistsError(root)
    for case in plan["cases"]:
        if sha256(Path(case["swc_path"])) != case["swc_sha256"]:
            raise ValueError(f"Source changed since dry-run: {case['uid']}")
        if Path(case["swc_path"]).is_relative_to(root):
            raise ValueError("Source SWC cannot be inside output root")
    for tool in plan["tools"].values():
        if sha256(Path(tool["path"])) != tool["sha256"]:
            raise ValueError("FNT executable changed since dry-run")
    root.mkdir(parents=True)
    try:
        return _produce_fnt(plan, root, cache)
    except Exception:
        _discard_unreceipted(root)
        raise


def _produce_fnt(plan: dict, root: Path, cache: Path) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    log = root / "commands.log"
    tools = {k: Path(v["path"]) for k, v in plan["tools"].items()}
    produced = []
    for case in plan["cases"]:
        stem = case["sample_id"] + "_" + case["neuron_id"].removesuffix(".swc")
        inputs = cache / case["sample_id"]
        inputs.mkdir(parents=True, exist_ok=True)
        mirrored = inputs / (stem + ".processed.swc")
        fnt = inputs / (stem + ".fnt")
        decimation_enabled = plan["decimation"].get("enabled", True)
        dec = inputs / (stem + (".decimate.fnt" if decimation_enabled else ".undecimated.fnt"))
        transform = preprocess_swc(Path(case["swc_path"]), mirrored,
                                   plan["preprocessing"]["mode"],
                                   float(plan["preprocessing"]["midline_x"]))
        _command([tools["fnt-from-swc.exe"], mirrored, fnt], log, plan["timeout_seconds"])
        _prepare_analysis_fnt(fnt, dec, plan["decimation"], tools["fnt-decimate.exe"],
                              log, plan["timeout_seconds"])
        _rename_fnt_marker(dec, stem)
        produced.append({**case, "marker": stem, "processed_swc": str(mirrored),
                         "processed_swc_sha256": sha256(mirrored), "transform": transform,
                         "converted_fnt": str(fnt), "analysis_fnt": str(dec),
                         "decimation_applied": decimation_enabled,
                         "fnt_sha256": sha256(fnt), "decimated_fnt": str(dec),
                         "decimated_fnt_sha256": sha256(dec)})
    joined = root / "joined.fnt"
    distance = root / "distance.tsv"
    if len(produced) > 32:
        # Hard links preserve exact inputs without duplicating scientific data.
        staging = root / "join_inputs"
        staging.mkdir()
        names = []
        for index, record in enumerate(produced):
            name = f"{index:04d}.fnt"
            os.link(record["decimated_fnt"], staging / name)
            names.append(name)
        _command([tools["fnt-join.exe"], *names, "-o", joined], log,
                 plan["timeout_seconds"], cwd=staging)
    else:
        _command([tools["fnt-join.exe"], *[r["decimated_fnt"] for r in produced], "-o", joined], log, plan["timeout_seconds"])
    markers = re.findall(r"^\d+ Neuron (\S+)\s*$", joined.read_text(errors="replace"), re.M)
    if markers != [r["marker"] for r in produced]:
        raise ValueError("Joined FNT marker order mismatch")
    _command([tools["fnt-dist.exe"], joined, "-o", distance], log, plan["timeout_seconds"])
    matrix, metadata = read_fnt_distances(distance, joined)
    if len(matrix) != len(produced):
        raise ValueError("FNT distance cardinality mismatch")
    result = None
    settings = plan["clustering"]
    if settings["enabled"]:
        result, _ = analyze_saved_scores(distance, joined, [r["uid"] for r in produced], settings)
        (root / "candidate_hierarchy.json").write_text(json.dumps(result, indent=2))
    after = {r["uid"]: sha256(Path(r["swc_path"])) for r in produced}
    if any(after[r["uid"]] != r["swc_sha256"] for r in produced):
        raise ValueError("A source SWC changed during the FNT run")
    receipt = {"schema": "remap.fnt_pipeline.v1", "version": __version__,
               "plan": {k: v for k, v in plan.items() if k != "source_config"},
               "cases": produced, "joined_fnt": str(joined), "joined_sha256": sha256(joined),
               "distance": str(distance), "distance_sha256": sha256(distance),
               "distance_metadata": metadata, "final_k": None,
               "candidate_hierarchy_sha256": sha256(root / "candidate_hierarchy.json") if result else None,
               "source_sha256_after": after}
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2))
    return receipt



def run_prepared_distance(preparation_receipt, original_plan, output_root, timeout_seconds=14400, dry_run=False):
    """Run one distance calculation from hash-verified prepared inputs.

    Retain partial outputs on failure; only receipt.json establishes completion.
    No SWC preprocessing or join is repeated, and incomplete scores are not reused.
    """
    preparation_receipt = Path(preparation_receipt)
    saved = json.loads(preparation_receipt.read_text())
    original_plan = Path(original_plan)
    plan = json.loads(original_plan.read_text())
    output = Path(output_root).resolve()
    if output.exists():
        raise FileExistsError(output)
    if type(timeout_seconds) is not int or not 10 <= timeout_seconds <= 86400:
        raise ValueError("Prepared distance timeout must be10..86400 seconds")
    prepared = preparation_receipt.parent
    for record in saved["artifacts"]:
        path = (prepared / record["path"]).resolve()
        if not path.is_relative_to(prepared.resolve()) or sha256(path) != record["sha256"]:
            raise ValueError("Prepared artifact path/hash mismatch")
    joined = prepared / "joined.fnt"
    markers = re.findall(r"^\d+ Neuron (\S+)\s*$", joined.read_text(errors="replace"), re.M)
    expected = [c["sample_id"]+"_"+c["neuron_id"].removesuffix(".swc") for c in plan["cases"]]
    if markers != expected or markers != saved["ordered_markers"]:
        raise ValueError("Prepared identity/order mismatch")
    tool = plan["tools"]["fnt-dist.exe"]
    if sha256(Path(tool["path"])) != tool["sha256"]:
        raise ValueError("Distance executable changed")
    receipt = {"version": __version__, "status": "prepared", "plan": plan,
               "preparation_receipt": str(preparation_receipt), "preparation_sha256": sha256(preparation_receipt),
               "joined_fnt": str(joined), "joined_sha256": sha256(joined),
               "timeout_seconds": timeout_seconds, "output_root": str(output)}
    if dry_run:
        return receipt
    output.mkdir(parents=True)
    (output / "plan.json").write_text(json.dumps(receipt, indent=2))
    distance = output / "distance.tsv"
    _command([tool["path"], joined, "-o", distance], output / "commands.log", timeout_seconds)
    matrix, metadata = read_fnt_distances(distance, joined)
    if list(matrix.index) != markers:
        raise ValueError("Completed distance identity mismatch")
    for case in plan["cases"]:
        if sha256(Path(case["swc_path"])) != case["swc_sha256"]:
            raise ValueError("Source SWC changed")
    receipt.update(status="complete", distance=str(distance), distance_sha256=sha256(distance),
                   distance_metadata=metadata, source_hashes_unchanged=True)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2))
    return receipt
