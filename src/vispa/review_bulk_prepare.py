"""Freeze one animal of exact raw-SWC review jobs with a managed byte cache.

Version: 1.21.6 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
Status: candidate

Operator: python -m vispa.review_bulk_prepare --config PATH --sample SAMPLE
          (--identities CSV | --catalog) --output-jobs PATH --cache-root PATH
          (--limit N | --all) [--raw-root PATH ...] [--source-receipt PATH]
          [--allow-download] [--run-name NAME] [--dry-run]

The preparation result reports exact failed neuron IDs and grouped source errors.
Callers may atomically replace a matching partial jobs file when retrying.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from vispa.config import load
from vispa.data_input_adaptor import (
    PortalSWCProvider, _guard_managed_cache, _publish_swc_versioned,
    acquire_neuron_sides, list_neurons, read_swc,
)

from .review_bulk_render import _atomic_json, _sha256, neuron_folder_name, validate_run_name


_SAMPLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\Z")
_NEURON = re.compile(r"[A-Za-z0-9_-]+\.swc\Z", re.IGNORECASE)


def _region_entries(row: dict) -> dict:
    """Keep only observed region fields; a structured soma_region stays intact."""
    entries = {}
    structured = row.get("soma_region")
    if structured is not None:
        if not isinstance(structured, dict):
            raise ValueError("soma_region must be an object when provided")
        entries["soma_region"] = structured
    for field in ("checked_region", "ion_atlas", "portal_region"):
        value = row.get(field)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"{field} must be a string")
            entries[field] = value
    return entries


def _selected_region(entries: dict) -> tuple[str | None, str | None]:
    structured = entries.get("soma_region") or {}
    for field in ("checked_region", "ion_atlas"):
        for container, path in ((structured, f"soma_region.{field}"), (entries, field)):
            value = container.get(field)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f"{path} must be a string")
                if value.strip():
                    return value.strip(), path
    value = entries.get("portal_region")
    if value and value.strip():
        return value.strip(), "portal_region"
    return None, None


def _source_receipt_info(path: Path | None, digest: str | None,
                         sample: str, neuron: str) -> dict:
    """Read cache provenance without treating retrieval time as source date."""
    if path is None:
        return {"status": "source_absent"}
    receipt = path.with_name(path.name + ".source.json")
    if not receipt.is_file():
        return {"status": "receipt_absent"}
    data = receipt.read_bytes()
    try:
        content = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "receipt_unreadable", "path": str(receipt),
                "receipt_sha256": hashlib.sha256(data).hexdigest()}
    matched = (isinstance(content, dict) and content.get("sample_id") == sample and
               content.get("neuron_id") == neuron and content.get("sha256") == digest)
    return {"status": "verified_identity_and_hash" if matched else "identity_or_hash_mismatch",
            "path": str(receipt), "receipt_sha256": hashlib.sha256(data).hexdigest(),
            "retrieved_at_utc": content.get("retrieved_at_utc") if matched else None,
            "freshness": content.get("freshness") if matched else None,
            "origin_url": content.get("origin_url") if matched else None}


def _identities_from_csv(path: Path, sample: str) -> tuple[list[str], dict, dict[str, dict]]:
    path = path.resolve(strict=True)
    data = path.read_bytes()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    if not {"sample", "neuron_id"}.issubset(reader.fieldnames or []):
        raise ValueError("Identities CSV requires sample and neuron_id columns")
    rows = [row for row in reader if row["sample"] == sample]
    names = [row["neuron_id"] for row in rows]
    regions = {row["neuron_id"]: _region_entries(row) for row in rows}
    return names, {"kind": "csv", "path": str(path), "sha256": hashlib.sha256(data).hexdigest()}, regions


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
              limit: int | None, all_jobs: bool, run_name: str | None = None,
              *, regions: list[str] | None = None) -> dict:
    if run_name is None:
        run_name = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("review_%Y-%m-%d_%H-%M-%S")
    run_name = validate_run_name(run_name)
    if not _SAMPLE.fullmatch(sample):
        raise ValueError("sample must be one path-safe animal sample ID")
    config_path = config_path.resolve(strict=True)
    config = load(config_path)
    from .config import context_unavailable_authorized
    context_source_status = ("missing_declared_5um_source" if
                             context_unavailable_authorized(config, sample) else
                             "configured_5um_source" if
                             (config.get("samples", {}).get(sample) or {}).get("resample_5um") else
                             "missing_unapproved_5um_source")
    if bool(identities) == catalog:
        raise ValueError("Choose exactly one of --identities and --catalog")
    if all_jobs == (limit is not None) or (limit is not None and limit < 1):
        raise ValueError("Choose a positive --limit or explicit --all")
    catalog_excluded = []
    if catalog:
        snapshot = list_neurons(sample, config)
        regions_by_neuron = {row["neuron_id"]: _region_entries(row)
                             for row in snapshot["rows"]}
        catalog_excluded = [
            {"neuron_id": row["neuron_id"], "reason": str(row.get("exclude") or "").strip()}
            for row in snapshot["rows"] if str(row.get("exclude") or "").strip()]
        names = [row["neuron_id"] for row in snapshot["rows"]
                 if not str(row.get("exclude") or "").strip()]
        identity_source = {key: snapshot.get(key) for key in
                           ("source_kind", "source_path", "sha256", "fetched_at", "count", "snapshot_id")}
    else:
        names, identity_source, regions_by_neuron = _identities_from_csv(identities, sample)
    if not names or len(names) != len(set(name.casefold() for name in names)):
        raise ValueError("Selected identities must be nonempty and unique")
    if any(not _NEURON.fullmatch(name) for name in names):
        raise ValueError("Each identity must be an exact simple .swc filename")
    if any(not isinstance(region, str) or not region or region != region.strip()
           for region in (regions or [])):
        raise ValueError("Each --region must be a nonempty exact atlas label")
    requested_regions = sorted(set(regions or []))
    expected, expected_source = _expected_hashes(source_receipt, sample)
    if expected and set(names) != set(expected):
        raise ValueError("Source receipt IDs differ from selected animal identities")
    available_regions = {entries.get("portal_region") for entries in regions_by_neuron.values()}
    unknown = set(requested_regions) - available_regions
    if unknown:
        raise ValueError("Unknown atlas region: " + ", ".join(sorted(unknown)))
    names = sorted(name for name in names if not requested_regions or
                   regions_by_neuron.get(name, {}).get("portal_region") in requested_regions)
    if not names:
        raise ValueError("No eligible neurons match the selected atlas regions")
    selected = names if all_jobs else names[:limit]
    roots = [root.resolve(strict=True) for root in raw_roots]
    cache_root = cache_root.expanduser().resolve()
    declared_root = (config.get("sources") or {}).get("legacy_raw_swc_root")
    declared = Path(declared_root).expanduser().resolve() if declared_root else None
    canonical = (Path(config["defaults"]["cache_root"]) / "swc_raw").expanduser().resolve()
    shared_config_cache = cache_root == canonical == declared
    _guard_managed_cache(cache_root, config.get("sources") or {},
                         allow_equal_raw=shared_config_cache)
    if any(cache_root == root or cache_root.is_relative_to(root) or root.is_relative_to(cache_root)
           for root in roots):
        raise ValueError("Managed cache must be separate from raw source roots")
    if declared is not None:
        if declared.is_relative_to(cache_root) and not shared_config_cache:
            raise ValueError("Managed cache must be separate from declared raw source root")
        if declared not in roots and declared != cache_root:
            roots.append(declared)
    try:
        side_batch = acquire_neuron_sides(sample, selected, config)
        side_results = side_batch["results"]
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        reason = f"VisPa native atlas region acquisition failed: {exc}"
        side_batch = {"status": "unavailable", "source": {"reason": reason}}
        side_results = {name: {"status": "error", "side": None,
                               "reason": reason, "source": None} for name in selected}
    jobs = []
    observed_at_utc = datetime.now(timezone.utc).isoformat()
    for name in selected:
        region_entries = regions_by_neuron.get(name) or {}
        region, region_field = _selected_region(region_entries)
        if region and (len(region) > 200 or any(ord(char) < 32 for char in region)):
            raise ValueError(f"Invalid portal_region text for {name}")
        candidates = [cache_root / sample / name] + [root / sample / name for root in roots]
        candidates = [path for path in candidates if path.is_file()]
        hashes = {_sha256(path) for path in candidates}
        if len(hashes) > 1:
            raise ValueError(f"Conflicting raw source bytes for {sample}/{name}")
        digest = next(iter(hashes), None)
        source_receipt = _source_receipt_info(candidates[0] if candidates else None,
                                              digest, sample, name)
        source_mtime_utc = (datetime.fromtimestamp(candidates[0].stat().st_mtime, timezone.utc).isoformat()
                            if candidates else None)
        if digest and expected and digest != expected[name]:
            raise ValueError(f"Raw source hash differs from receipt for {sample}/{name}")
        vispa_region = side_results.get(name, {"status": "unknown", "side": None,
                                               "reason": "No VisPa region result", "source": None})
        verified_side = (vispa_region.get("side") if vispa_region.get("status") == "verified"
                         and vispa_region.get("side") in {"Left", "Right"} else None)
        jobs.append({"sample_id": sample, "neuron_id": name,
                     "context_source_status": context_source_status,
                     "vispa_region": vispa_region,
                     "neuron_folder": neuron_folder_name(sample, name, region, side=verified_side),
                     "soma_region": region,
                     "soma_region_entries": region_entries,
                     "soma_region_source": ({**identity_source, "field": region_field} if region else None),
                     "raw_source_path": str(candidates[0]) if candidates else None,
                     "raw_swc_sha256": digest, "expected_raw_swc_sha256": expected.get(name),
                     "raw_source_receipt": source_receipt,
                     "source_acquisition_date": None,
                     "source_acquisition_date_status": "unknown; no verified date in source metadata",
                     "source_observed_at_utc": observed_at_utc,
                     "raw_source_file_mtime_utc": source_mtime_utc,
                     "raw_source_file_mtime_role": "filesystem mtime; not acquisition date",
                     "cache_path": str(cache_root / sample / name),
                     "render_ready": bool(digest),
                     "soma_error": None if digest else "raw SWC absent from declared roots; download requires --allow-download"})
    return {"schema": "vispa.review_bulk.prepare.v1", "sample_id": sample,
            "run_name": run_name,
            "vispa_config": str(config_path), "vispa_config_sha256": _sha256(config_path),
            "figure_output_root": str(config["visual_toolkit"]["figure_output_root"]),
            "identity_source": identity_source, "expected_source": expected_source,
            "vispa_region_lookup": {"status": side_batch.get("status"),
                                    "source": side_batch.get("source"),
                                    "counts": side_batch.get("counts")},
            "region_filter": {"labels": requested_regions, "field": "portal_region",
                              "source": identity_source},
            "catalog_excluded": catalog_excluded,
            "cache_root": str(cache_root), "selected_count": len(jobs),
            "available_count": sum(job["render_ready"] for job in jobs),
            "missing_count": sum(not job["render_ready"] for job in jobs),
            "allow_all": all_jobs, "jobs": jobs}


def prepare_jobs(plan: dict, output_jobs: Path, *, dry_run: bool, allow_download: bool,
                 replace_existing: bool = False) -> dict:
    result = {**plan, "output_jobs": str(output_jobs.resolve()), "dry_run": dry_run,
              "allow_download": allow_download, "status": "dry_run" if dry_run else "in_progress"}
    if dry_run:
        return result
    output_jobs = output_jobs.resolve()
    if output_jobs.exists() and not replace_existing:
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
                         "context_source_status": item["context_source_status"],
                         "neuron_folder": item["neuron_folder"],
                         "render_ready": True, "soma_xyz": list(tree.root.xyz),
                         "soma_units": "raw SWC stored coordinates (nominal um)",
                         "soma_coordinate_source": str(target) + f"#root-node-{tree.root.id}",
                         "raw_swc_path": str(target), "raw_swc_sha256": digest,
                         "raw_source_path": str(source) if source else "portal managed cache",
                         "raw_source_receipt": item["raw_source_receipt"],
                         "source_acquisition_date": item["source_acquisition_date"],
                         "source_acquisition_date_status": item["source_acquisition_date_status"],
                         "source_observed_at_utc": item["source_observed_at_utc"],
                         "raw_source_file_mtime_utc": item["raw_source_file_mtime_utc"],
                         "raw_source_file_mtime_role": item["raw_source_file_mtime_role"],
                         "soma_region": item["soma_region"],
                         "vispa_region": item["vispa_region"],
                         "soma_region_entries": item["soma_region_entries"],
                         "soma_region_source": item["soma_region_source"],
                         "fnt_marker": None, "fnt_cluster": None})
        except (OSError, RuntimeError, ValueError) as exc:
            jobs.append({"sample_id": item["sample_id"], "neuron_id": item["neuron_id"],
                         "context_source_status": item["context_source_status"],
                         "neuron_folder": item["neuron_folder"],
                         "render_ready": False, "soma_error": str(exc)})
    payload = {"schema": "vispa.review_bulk.v1", "sample_id": plan["sample_id"],
               "run_name": plan["run_name"],
               "vispa_config": plan["vispa_config"],
               "vispa_config_sha256": plan["vispa_config_sha256"],
               "figure_output_root": plan["figure_output_root"],
               "allow_all": plan["allow_all"],
               "output_layout": "sample_neurons_flat", "identity_source": plan["identity_source"],
               "vispa_region_lookup": plan["vispa_region_lookup"],
               "region_filter": plan["region_filter"],
               "catalog_excluded": plan["catalog_excluded"],
               "source_receipt": plan["expected_source"], "cache_root": plan["cache_root"],
               "jobs": jobs}
    output_jobs.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(output_jobs, payload)
    failures = [{"neuron_id": job["neuron_id"], "error": job.get("soma_error")}
                for job in jobs if not job["render_ready"]]
    grouped = {}
    for failure in failures:
        entry = grouped.setdefault(failure["error"], {
            "error": failure["error"], "count": 0, "neuron_ids": []})
        entry["count"] += 1
        entry["neuron_ids"].append(failure["neuron_id"])
    result["status"] = "prepared" if not failures else "partial"
    result["prepared_count"] = len(jobs) - len(failures)
    result["failed_count"] = len(failures)
    result["failures"] = failures
    result["failure_summary"] = sorted(
        grouped.values(), key=lambda item: (-item["count"], str(item["error"])))
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
    parser.add_argument("--run-name", help="path-safe readable name for this new review run")
    parser.add_argument("--region", action="append", default=[],
                        help="exact IONData atlas region; repeat to include several regions")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--limit", type=int)
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = plan_jobs(args.config, args.sample, args.identities, args.catalog,
                         args.raw_root, args.cache_root, args.source_receipt,
                         args.limit, args.all, args.run_name, regions=args.region)
        result = prepare_jobs(plan, args.output_jobs,
                              dry_run=args.dry_run, allow_download=args.allow_download)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"dry_run", "prepared"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
