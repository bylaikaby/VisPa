"""Freeze one animal of exact raw-SWC review jobs with a managed byte cache.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../CHANGELOG.md
Status: candidate

Operator: python -m batch.prepare_review_bulk --config PATH --sample SAMPLE
          (--identities CSV | --catalog) --output-jobs PATH --cache-root PATH
          (--limit N | --all) [--raw-root PATH ...] [--source-receipt PATH]
          [--allow-download] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re

from vispa.config import load
from vispa.data_input_adaptor import (
    PortalSWCProvider, _guard_managed_cache, _publish_swc_versioned,
    list_neurons, read_swc,
)

from .render_review_bulk import _atomic_json, _sha256


_SAMPLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\Z")
_NEURON = re.compile(r"[A-Za-z0-9_-]+\.swc\Z", re.IGNORECASE)


def _identities_from_csv(path: Path, sample: str) -> tuple[list[str], dict]:
    path = path.resolve(strict=True)
    data = path.read_bytes()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    if not {"sample", "neuron_id"}.issubset(reader.fieldnames or []):
        raise ValueError("Identities CSV requires sample and neuron_id columns")
    names = [row["neuron_id"] for row in reader if row["sample"] == sample]
    return names, {"kind": "csv", "path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def _expected_hashes(path: Path | None, sample: str) -> tuple[dict[str, str], dict | None]:
    if path is None:
        return {}, None
    path = path.resolve(strict=True)
    data = path.read_bytes()
    record = json.loads(data)
    if record.get("sample_id") not in (None, sample):
        raise ValueError("Source receipt identifies a different sample")
    if record.get("raw_folder") and Path(record["raw_folder"]).name != sample:
        raise ValueError("Source receipt raw folder identifies a different sample")
    files = record.get("source_files")
    if not isinstance(files, list):
        raise ValueError("Source receipt requires source_files")
    expected = {}
    for item in files:
        name, digest = item.get("id"), item.get("sha256")
        if not isinstance(name, str) or not _NEURON.fullmatch(name):
            raise ValueError("Source receipt has an invalid neuron ID")
        if name in expected or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("Source receipt has duplicate IDs or invalid hashes")
        expected[name] = digest.lower()
    if record.get("manifest_count") is not None and record.get("manifest_count") != len(expected):
        raise ValueError("Source receipt count does not match source_files")
    return expected, {"kind": "source_receipt", "path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                      "sample_id": sample}


def plan_jobs(config_path: Path, sample: str, identities: Path | None, catalog: bool,
              raw_roots: list[Path], cache_root: Path, source_receipt: Path | None,
              limit: int | None, all_jobs: bool) -> dict:
    if not _SAMPLE.fullmatch(sample):
        raise ValueError("sample must be one path-safe animal sample ID")
    config_path = config_path.resolve(strict=True)
    config = load(config_path)
    if bool(identities) == catalog:
        raise ValueError("Choose exactly one of --identities and --catalog")
    if all_jobs == (limit is not None) or (limit is not None and limit < 1):
        raise ValueError("Choose a positive --limit or explicit --all")
    catalog_excluded = []
    if catalog:
        snapshot = list_neurons(sample, config)
        catalog_excluded = [
            {"neuron_id": row["neuron_id"], "reason": str(row.get("exclude") or "").strip()}
            for row in snapshot["rows"] if str(row.get("exclude") or "").strip()]
        names = [row["neuron_id"] for row in snapshot["rows"]
                 if not str(row.get("exclude") or "").strip()]
        identity_source = {key: snapshot.get(key) for key in
                           ("source_kind", "source_path", "sha256", "fetched_at", "count", "snapshot_id")}
    else:
        names, identity_source = _identities_from_csv(identities, sample)
    if not names or len(names) != len(set(name.casefold() for name in names)):
        raise ValueError("Selected identities must be nonempty and unique")
    if any(not _NEURON.fullmatch(name) for name in names):
        raise ValueError("Each identity must be an exact simple .swc filename")
    names = sorted(names)
    selected = names if all_jobs else names[:limit]
    expected, expected_source = _expected_hashes(source_receipt, sample)
    if expected and set(names) != set(expected):
        raise ValueError("Source receipt IDs differ from selected animal identities")
    roots = [root.resolve(strict=True) for root in raw_roots]
    cache_root = cache_root.expanduser().resolve()
    _guard_managed_cache(cache_root, config.get("sources") or {})
    if any(cache_root == root or cache_root.is_relative_to(root) or root.is_relative_to(cache_root)
           for root in roots):
        raise ValueError("Managed cache must be separate from raw source roots")
    declared_root = (config.get("sources") or {}).get("legacy_raw_swc_root")
    if declared_root:
        declared = Path(declared_root).expanduser().resolve()
        if declared.is_relative_to(cache_root):
            raise ValueError("Managed cache must be separate from declared raw source root")
        if declared not in roots and declared != cache_root:
            roots.append(declared)
    jobs = []
    for name in selected:
        candidates = [cache_root / sample / name] + [root / sample / name for root in roots]
        candidates = [path for path in candidates if path.is_file()]
        hashes = {_sha256(path) for path in candidates}
        if len(hashes) > 1:
            raise ValueError(f"Conflicting raw source bytes for {sample}/{name}")
        digest = next(iter(hashes), None)
        if digest and expected and digest != expected[name]:
            raise ValueError(f"Raw source hash differs from receipt for {sample}/{name}")
        jobs.append({"sample_id": sample, "neuron_id": name,
                     "raw_source_path": str(candidates[0]) if candidates else None,
                     "raw_swc_sha256": digest, "expected_raw_swc_sha256": expected.get(name),
                     "cache_path": str(cache_root / sample / name),
                     "render_ready": bool(digest),
                     "soma_error": None if digest else "raw SWC absent from declared roots; download requires --allow-download"})
    return {"schema": "vispa.review_bulk.prepare.v1", "sample_id": sample,
            "vispa_config": str(config_path), "vispa_config_sha256": _sha256(config_path),
            "figure_output_root": str(config["visual_toolkit"]["figure_output_root"]),
            "identity_source": identity_source, "expected_source": expected_source,
            "catalog_excluded": catalog_excluded,
            "cache_root": str(cache_root), "selected_count": len(jobs),
            "available_count": sum(job["render_ready"] for job in jobs),
            "missing_count": sum(not job["render_ready"] for job in jobs),
            "allow_all": all_jobs, "jobs": jobs}


def prepare_jobs(plan: dict, output_jobs: Path, *, dry_run: bool, allow_download: bool) -> dict:
    result = {**plan, "output_jobs": str(output_jobs.resolve()), "dry_run": dry_run,
              "allow_download": allow_download, "status": "dry_run" if dry_run else "in_progress"}
    if dry_run:
        return result
    output_jobs = output_jobs.resolve()
    if output_jobs.exists():
        raise FileExistsError(f"Jobs file already exists: {output_jobs}")
    if _sha256(Path(plan["vispa_config"])) != plan["vispa_config_sha256"]:
        raise ValueError("VisPa config changed after preparation plan")
    config = load(plan["vispa_config"])
    cache_root = Path(plan["cache_root"])
    portal = PortalSWCProvider(config, cache_root=cache_root) if allow_download else None
    jobs = []
    for item in plan["jobs"]:
        source = Path(item["raw_source_path"]) if item["raw_source_path"] else None
        target = Path(item["cache_path"])
        expected = item["expected_raw_swc_sha256"]
        try:
            if source is not None and _sha256(source) != item["raw_swc_sha256"]:
                raise ValueError("raw source changed after plan")
            if target.is_file():
                if source is not None and _sha256(target) != item["raw_swc_sha256"]:
                    raise ValueError("managed cache differs from declared source")
            elif source is not None:
                _publish_swc_versioned(target, source.read_bytes(), str(source), role="raw",
                                       sample_id=item["sample_id"], neuron_id=item["neuron_id"],
                                       freshness="local-exact-copy")
            elif portal is not None:
                portal.getRawNeuronTreeByID(item["sample_id"], item["neuron_id"])
            if not target.is_file():
                raise FileNotFoundError("raw SWC unavailable in managed cache")
            digest = _sha256(target)
            if item["raw_swc_sha256"] and digest != item["raw_swc_sha256"]:
                raise ValueError("managed SWC differs from planned raw source hash")
            if expected and digest != expected:
                raise ValueError("managed SWC differs from expected source receipt")
            tree = read_swc(target)
            jobs.append({"sample_id": item["sample_id"], "neuron_id": item["neuron_id"],
                         "render_ready": True, "soma_xyz": list(tree.root.xyz),
                         "soma_units": "raw SWC stored coordinates (nominal um)",
                         "soma_coordinate_source": str(target) + f"#root-node-{tree.root.id}",
                         "raw_swc_path": str(target), "raw_swc_sha256": digest,
                         "raw_source_path": str(source) if source else "portal managed cache",
                         "soma_region": None, "fnt_marker": None, "fnt_cluster": None})
        except (OSError, RuntimeError, ValueError) as exc:
            jobs.append({"sample_id": item["sample_id"], "neuron_id": item["neuron_id"],
                         "render_ready": False, "soma_error": str(exc)})
    payload = {"schema": "vispa.review_bulk.v1", "sample_id": plan["sample_id"],
               "vispa_config": plan["vispa_config"],
               "vispa_config_sha256": plan["vispa_config_sha256"],
               "allow_all": plan["allow_all"],
               "output_layout": "sample_neurons", "identity_source": plan["identity_source"],
               "catalog_excluded": plan["catalog_excluded"],
               "source_receipt": plan["expected_source"], "cache_root": plan["cache_root"],
               "jobs": jobs}
    output_jobs.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(output_jobs, payload)
    result["status"] = "prepared" if all(job["render_ready"] for job in jobs) else "partial"
    result["prepared_count"] = sum(job["render_ready"] for job in jobs)
    result["failed_count"] = sum(not job["render_ready"] for job in jobs)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    from vispa import __version__
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--sample", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--identities", type=Path)
    selection.add_argument("--catalog", action="store_true")
    parser.add_argument("--raw-root", type=Path, action="append", default=[])
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output-jobs", type=Path, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--limit", type=int)
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = plan_jobs(args.config, args.sample, args.identities, args.catalog,
                         args.raw_root, args.cache_root, args.source_receipt,
                         args.limit, args.all)
        result = prepare_jobs(plan, args.output_jobs,
                              dry_run=args.dry_run, allow_download=args.allow_download)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"dry_run", "prepared"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
