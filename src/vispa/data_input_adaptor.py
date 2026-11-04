"""Explicit data-input adaptor for local SWCs and source-tree providers.

Version: 1.20.1 (local/unreleased)
Last updated: 2026-11-04
Change history: ../../CHANGELOG.md
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import io
import json
import math
import os
import tempfile
import re
import zipfile
from zipfile import BadZipFile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

def load():
    """Load configuration lazily so source parsing remains usable on its own."""
    from .config import load as load_config
    return load_config()

_provider_factory: Callable | None = None
_LEFT_PREFIXES = ("CL_", "SL_", "L-", "L_")
_RIGHT_PREFIXES = ("CR_", "SR_", "R-", "R_")
_ATLAS_CACHE = {}


def set_iondata_provider_factory(factory: Callable | None) -> None:
    """Register a project-specific provider factory; pass None to restore local SWC."""
    global _provider_factory
    _provider_factory = factory


configure_iondata_provider = set_iondata_provider_factory


@dataclass
class SWCNode:
    id: int
    type: int
    x: float
    y: float
    z: float
    radius: float
    parent_id: int

    @property
    def xyz(self):
        return (self.x, self.y, self.z)


@dataclass
class SWCEdge:
    data: list[SWCNode]


@dataclass
class SWCTree:
    root: SWCNode
    edges: list[SWCEdge]
    points: list[SWCNode]


def list_neurons(sample_id: str, config: dict | None = None, *, source: str | None = None) -> dict:
    """Read one sample's catalog from configured CSV or the live IONData API.

    CSV remains the mode for older configurations. Live results are a bounded,
    timestamped in-memory snapshot; there is no implicit CSV fallback.
    """
    _validate_sample_id(sample_id)
    resolved = config if config is not None else load()
    catalog = (resolved.get("sources") or {}).get("neuron_catalog")
    if not isinstance(catalog, dict):
        raise ValueError("no sources.neuron_catalog.path or live-iondata source is configured")
    mode = source if source is not None else catalog.get("mode", "csv")
    if mode not in {"csv", "live-iondata"}:
        raise ValueError("source must be 'csv' or 'live-iondata'")
    if mode == "live-iondata":
        result = _list_live_neurons(sample_id, catalog)
    else:
        csv_catalog = dict(catalog)
        if catalog.get("mode") == "live-iondata":
            csv_catalog["path"] = catalog.get("snapshot_path")
        result = _list_csv_neurons(sample_id, csv_catalog)
    for row in result["rows"]:
        if result.get("snapshot_id"):
            row["snapshot_id"] = result["snapshot_id"]
    return result


def _fetch_soma_catalog(sample_id: str, config: dict | None = None) -> dict:
    """Fetch and validate one sample's bounded IONData soma catalog."""
    _validate_sample_id(sample_id)
    resolved = config if config is not None else load()
    catalog = (resolved.get("sources") or {}).get("neuron_catalog")
    if not isinstance(catalog, dict) or catalog.get("mode") != "live-iondata":
        raise ValueError("live IONData catalog is required for soma-side acquisition")
    request_url = soma_request_url(sample_id, catalog)
    timeout_value = catalog.get("timeout_seconds", 10)
    byte_value = catalog.get("max_response_bytes", 8 * 1024 * 1024)
    if (isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float))
            or not math.isfinite(timeout_value) or not 1 <= timeout_value <= 60):
        raise ValueError("sources.neuron_catalog.timeout_seconds must be between 1 and 60")
    if (isinstance(byte_value, bool) or not isinstance(byte_value, int)
            or not 1024 <= byte_value <= 32 * 1024 * 1024):
        raise ValueError("sources.neuron_catalog.max_response_bytes must be between 1024 and 33554432")
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=float(timeout_value)) as response:
        status = response.getcode()
        raw_bytes = response.read(byte_value + 1)
    if status != 200:
        raise RuntimeError(f"IONData soma catalog returned HTTP {status}: {request_url}")
    if len(raw_bytes) > byte_value:
        raise ValueError(f"IONData soma catalog exceeded the {byte_value}-byte response limit")
    try:
        source_rows = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"IONData soma catalog returned invalid UTF-8 JSON: {request_url}") from exc
    if not isinstance(source_rows, list):
        raise ValueError("IONData soma catalog response must be a JSON array")
    rows = []
    by_neuron = {}
    for index, row in enumerate(source_rows):
        if not isinstance(row, dict) or row.get("sampleid") != sample_id:
            continue
        neuron_id = _safe_neuron_id(
            row.get("name"), f"IONData soma row {index + 1}", sample_id)
        if neuron_id in by_neuron:
            raise ValueError(f"IONData soma catalog has duplicate identity {sample_id}/{neuron_id}")
        record = {
            "neuron_id": neuron_id,
            "soma_xyz": [row.get("somax"), row.get("somay"), row.get("somaz")],
            "row": index + 1,
        }
        rows.append(record)
        by_neuron[neuron_id] = record
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return {
        "sample_id": sample_id,
        "request_url": request_url,
        "fetched_at": fetched_at,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "source_size": len(raw_bytes),
        "rows": rows,
        "by_neuron": by_neuron,
    }


def get_soma_coordinates(sample_id: str, neuron_id: str, config: dict | None = None) -> dict:
    """Acquire one exact soma coordinate from the configured live IONData API."""
    _validate_sample_id(sample_id)
    neuron_id = _safe_neuron_id(neuron_id, "IONData soma lookup", sample_id)
    catalog = _fetch_soma_catalog(sample_id, config)
    record = catalog["by_neuron"].get(neuron_id)
    if record is None:
        raise LookupError(f"IONData soma catalog has no exact identity {sample_id}/{neuron_id}")
    coordinates = _validated_soma_xyz(record, sample_id, neuron_id)
    return {
        "sample_id": sample_id,
        "neuron_id": neuron_id,
        "soma_xyz": coordinates,
        "request_url": catalog["request_url"],
        "fetched_at": catalog["fetched_at"],
        "row": record["row"],
        "sha256": catalog["sha256"],
        "source_size": catalog["source_size"],
    }


def _validated_soma_xyz(record: dict, sample_id: str, neuron_id: str) -> list[float]:
    coordinates = []
    for key, value in zip(("somax", "somay", "somaz"), record.get("soma_xyz") or ()):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise ValueError(
                f"IONData soma row {record.get('row')} has invalid {key} "
                f"for {sample_id}/{neuron_id}")
        coordinates.append(float(value))
    if len(coordinates) != 3:
        raise ValueError(
            f"IONData soma row {record.get('row')} has incomplete coordinates "
            f"for {sample_id}/{neuron_id}")
    return coordinates


def side_from_region(region) -> str | None:
    """Return an explicit side encoded by a region label, without inference."""
    if not isinstance(region, str):
        return None
    text = region.strip()
    if text.startswith(_LEFT_PREFIXES):
        return "Left"
    if text.startswith(_RIGHT_PREFIXES):
        return "Right"
    return None


def _resolve_side_workbook(root: str | Path | None, sample_id: str) -> Path | None:
    """Resolve an explicit workbook or the supported per-sample workbook names."""
    if not root:
        return None
    source = Path(root).expanduser()
    if source.suffix.lower() in {".xlsx", ".xlsm"}:
        return source
    candidates = [
        source / f"{sample_id}_results.xlsx",
        source / f"{sample_id}_FULL.xlsx",
    ]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) > 1:
        raise ValueError(
            f"multiple per-sample neuron workbooks are present in {source}; "
            "configure the exact ReMAP results workbook or a dedicated folder")
    return existing[0] if existing else candidates[0]


def _load_configured_atlas(block: dict):
    """Load one configured VisPa atlas and retain it for the process."""
    from .swc_terminal_candidates import load_atlas

    atlas_path = Path(str(block.get("root") or "")).expanduser().resolve()
    key_path = Path(str(block.get("key") or "")).expanduser().resolve()
    if not block.get("root") or not block.get("key"):
        raise ValueError("sources.atlas.root and sources.atlas.key are required")
    atlas_stat, key_stat = atlas_path.stat(), key_path.stat()
    cache_key = (
        str(atlas_path), atlas_stat.st_size, atlas_stat.st_mtime_ns,
        str(key_path), key_stat.st_size, key_stat.st_mtime_ns,
    )
    atlas = _ATLAS_CACHE.get(cache_key)
    if atlas is None:
        atlas = load_atlas(atlas_path, key_path)
        _ATLAS_CACHE.clear()
        _ATLAS_CACHE[cache_key] = atlas
    return atlas


def _side_from_mask(voxel, atlas, mask_path: str | Path) -> str | None:
    """Map an explicitly configured left/right mask value at one atlas voxel."""
    import nibabel as nib
    import numpy as np

    path = Path(mask_path).expanduser().resolve()
    stat = path.stat()
    cache_key = ("hemisphere-mask", str(path), stat.st_size, stat.st_mtime_ns,
                 atlas.path)
    cached = _ATLAS_CACHE.get(cache_key)
    if cached is None:
        mask_img = nib.load(path)
        if mask_img.shape != atlas.image.shape[:3]:
            raise ValueError("hemisphere mask and atlas must share a 3D grid")
        if str(atlas.path).lower().endswith((".nii", ".nii.gz")):
            atlas_img = nib.load(atlas.path)
            if not np.allclose(mask_img.affine, atlas_img.affine, rtol=0, atol=1e-7):
                raise ValueError("hemisphere mask and atlas affines must match")
        mask = np.asanyarray(mask_img.dataobj)
        plane = atlas.plane(6)
        if plane is None:
            raise ValueError("configured atlas has no level-6 plane")
        value_to_side = {}
        for value in np.unique(mask):
            if int(value) == 0:
                continue
            codes = plane[mask == value]
            sides = [
                side_from_region((atlas.table.get(int(code)) or {}).get("abbreviation"))
                for code in np.unique(codes)
            ]
            has_left, has_right = "Left" in sides, "Right" in sides
            if has_left != has_right:
                value_to_side[int(value)] = "Left" if has_left else "Right"
        cached = (mask, value_to_side)
        _ATLAS_CACHE[cache_key] = cached
    mask, value_to_side = cached
    if not all(0 <= int(voxel[axis]) < mask.shape[axis] for axis in range(3)):
        return None
    return value_to_side.get(int(mask[tuple(int(value) for value in voxel)]))


def _acquire_side_from_soma(sample_id: str, neuron_id: str, config: dict,
                            soma_xyz=None, soma_record=None) -> dict:
    """Apply the shared VisPa side mapping to one known or fetchable soma."""
    result = {"status": "unknown", "side": None, "reason": "", "source": None}
    sources = (config or {}).get("sources") or {}
    atlas_block = sources.get("atlas") or {}
    if not atlas_block:
        table_root = (sources.get("neuron_tables") or {}).get("root")
        return lookup_neuron_side(table_root, sample_id, neuron_id)
    if soma_xyz is None:
        try:
            soma_record = get_soma_coordinates(sample_id, neuron_id, config)
            soma_xyz = soma_record["soma_xyz"]
        except Exception as exc:
            result["reason"] = f"IONData soma acquisition failed: {exc}"
            return result
    try:
        from .swc_terminal_candidates import atlas_names
        atlas = _load_configured_atlas(atlas_block)
        scale = float(atlas_block.get("coordinate_scale_um", 250.0))
        lookup = atlas_names(soma_xyz, atlas, levels=(6,), scale_um=scale)
        region = (lookup.get("names", {}).get(6) or {}).get("abbreviation")
        side = side_from_region(region)
        method = "NMT_atlas_region_prefix"
        if side is None and atlas_block.get("hemisphere_mask"):
            side = _side_from_mask(lookup["voxel"], atlas, atlas_block["hemisphere_mask"])
            method = "NMT_hemisphere_mask"
        if side is None:
            result["reason"] = (
                f"atlas region {region!r} has no explicit side prefix and "
                "the configured hemisphere-mask lookup was inconclusive")
            return result
        result.update(
            status="verified",
            side=side,
            reason=f"soma coordinate maps to {region}",
            source={
                "method": method,
                "producer": "VisPa native atlas side acquisition",
                "soma_xyz": [float(value) for value in soma_xyz],
                "atlas_voxel": lookup["voxel"],
                "atlas_region": region,
                "atlas_scale_um": scale,
                "atlas_path": atlas.path,
                "atlas_key_path": atlas.key_path,
                "atlas_sha256": (atlas.provenance or {}).get("atlas", {}).get("sha256"),
                "atlas_key_sha256": (atlas.provenance or {}).get("atlas_key", {}).get("sha256"),
                "soma_source": soma_record,
            })
        return result
    except Exception as exc:
        result["reason"] = f"VisPa side acquisition failed: {exc}"
        return result


def acquire_neuron_side(sample_id: str, neuron_id: str, config: dict,
                        soma_xyz=None) -> dict:
    """Acquire side from IONData soma coordinates and the configured NMT atlas."""
    return _acquire_side_from_soma(sample_id, neuron_id, config, soma_xyz=soma_xyz)


def acquire_neuron_sides(sample_id: str, neuron_ids, config: dict) -> dict:
    """Acquire sides for a bounded catalog using the single-neuron mechanism."""
    _validate_sample_id(sample_id)
    requested = []
    seen = set()
    for neuron_id in neuron_ids:
        exact = _safe_neuron_id(neuron_id, "catalog side lookup", sample_id)
        if exact not in seen:
            seen.add(exact)
            requested.append(exact)
    sources = (config or {}).get("sources") or {}
    if not sources.get("atlas"):
        results = {
            neuron_id: acquire_neuron_side(sample_id, neuron_id, config)
            for neuron_id in requested
        }
        return {
            "status": "complete",
            "sample_id": sample_id,
            "results": results,
            "counts": _side_counts(results),
            "source": {"method": "configured_side_fallback"},
        }
    try:
        soma_catalog = _fetch_soma_catalog(sample_id, config)
    except Exception as exc:
        reason = f"IONData soma catalog acquisition failed: {exc}"
        results = {
            neuron_id: {
                "status": "error", "side": None, "reason": reason, "source": None,
            }
            for neuron_id in requested
        }
        return {
            "status": "unavailable",
            "sample_id": sample_id,
            "results": results,
            "counts": _side_counts(results),
            "source": {"method": "IONData_soma_catalog", "reason": reason},
        }
    results = {}
    for neuron_id in requested:
        record = soma_catalog["by_neuron"].get(neuron_id)
        if record is None:
            results[neuron_id] = {
                "status": "unknown",
                "side": None,
                "reason": "IONData soma catalog has no exact identity "
                          f"{sample_id}/{neuron_id}",
                "source": None,
            }
            continue
        try:
            coordinates = _validated_soma_xyz(record, sample_id, neuron_id)
        except ValueError as exc:
            results[neuron_id] = {
                "status": "unknown",
                "side": None,
                "reason": str(exc),
                "source": None,
            }
            continue
        soma_record = {
            "sample_id": sample_id,
            "neuron_id": neuron_id,
            "soma_xyz": coordinates,
            "request_url": soma_catalog["request_url"],
            "fetched_at": soma_catalog["fetched_at"],
            "row": record["row"],
            "sha256": soma_catalog["sha256"],
            "source_size": soma_catalog["source_size"],
        }
        results[neuron_id] = _acquire_side_from_soma(
            sample_id, neuron_id, config,
            soma_xyz=coordinates, soma_record=soma_record)
    return {
        "status": "complete",
        "sample_id": sample_id,
        "results": results,
        "counts": _side_counts(results),
        "source": {
            "method": "IONData_soma_catalog+NMT_atlas",
            "request_url": soma_catalog["request_url"],
            "fetched_at": soma_catalog["fetched_at"],
            "sha256": soma_catalog["sha256"],
            "source_size": soma_catalog["source_size"],
        },
    }


def _side_counts(results: dict) -> dict:
    counts = {"Left": 0, "Right": 0, "Unknown": 0}
    for result in results.values():
        side = result.get("side") if result.get("status") == "verified" else None
        counts[side or "Unknown"] += 1
    return counts


def _record_filename_part(value: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-.")
    return text or fallback


def neuron_catalog_table_filename(snapshot: dict, monkey_id: str,
                                  *, recorded_at: datetime | None = None) -> str:
    """Return the timestamped default CSV filename for one catalog snapshot."""
    sample_id = snapshot.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id:
        raise ValueError("catalog snapshot has no exact sample identity")
    recorded = recorded_at or datetime.now().astimezone()
    stamp = recorded.strftime("%Y%m%d_%H%M%S")
    monkey_part = _record_filename_part(monkey_id, "unmapped-monkey")
    sample_part = _record_filename_part(sample_id, "sample")
    return f"{monkey_part}_{sample_part}_neuron_table_{stamp}.csv"


def write_neuron_catalog_table(snapshot: dict, side_result: dict,
                               output_dir: str | Path, monkey_id: str,
                               *, recorded_at: datetime | None = None,
                               output_path: str | Path | None = None) -> dict:
    """Write the current catalog with VisPa side acquisition and provenance."""
    if not catalog_snapshot_unchanged(snapshot):
        raise ValueError("catalog snapshot changed; reload the neuron list before saving")
    sample_id = snapshot.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id:
        raise ValueError("catalog snapshot has no exact sample identity")
    recorded = recorded_at or datetime.now().astimezone()
    generated_path = output_path is None
    if output_path is not None:
        chosen = Path(output_path).expanduser()
        if chosen.suffix.lower() != ".csv":
            chosen = chosen.with_suffix(".csv")
        path = chosen.resolve()
        folder = path.parent
    else:
        folder = Path(output_dir).expanduser().resolve()
        path = folder / neuron_catalog_table_filename(
            snapshot, monkey_id, recorded_at=recorded)
    folder.mkdir(parents=True, exist_ok=True)
    if generated_path and path.exists():
        stem = path.stem
        counter = 2
        while path.exists():
            path = folder / f"{stem}_{counter:02d}.csv"
            counter += 1
    if path.exists():
        raise FileExistsError(f"neuron table already exists: {path}")

    side_results = side_result.get("results") or {}
    source_kind = str(snapshot.get("source_kind") or "unknown")
    source_path = (snapshot.get("request_url") if source_kind == "live-iondata"
                   else snapshot.get("source_path")) or ""
    side_source = side_result.get("source") or {}
    fields = (
        "AnimalID", "SampleID", "NeuronID", "Side", "SideStatus",
        "SideReason", "SideMethod", "AtlasRegion", "AtlasVoxel",
        "SomaX", "SomaY", "SomaZ", "PortalRegion", "CatalogSource",
        "SourcePath", "SourceDate", "FetchedAt", "SnapshotID",
        "CatalogSHA256", "SomaCatalogSHA256", "AtlasSHA256", "RecordedAt",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in snapshot.get("rows", ()):
            neuron_id = row.get("neuron_id", "")
            result = side_results.get(neuron_id) or {
                "status": "not_checked", "side": None,
                "reason": "side acquisition result is unavailable", "source": None,
            }
            result_source = result.get("source") or {}
            soma_source = result_source.get("soma_source") or {}
            soma_xyz = result_source.get("soma_xyz") or soma_source.get("soma_xyz") or []
            atlas_voxel = result_source.get("atlas_voxel") or []
            writer.writerow({
                "AnimalID": str(monkey_id or ""),
                "SampleID": sample_id,
                "NeuronID": neuron_id,
                "Side": result.get("side") or "",
                "SideStatus": result.get("status") or "unknown",
                "SideReason": result.get("reason") or "",
                "SideMethod": result_source.get("method") or side_source.get("method") or "",
                "AtlasRegion": result_source.get("atlas_region") or "",
                "AtlasVoxel": ",".join(str(value) for value in atlas_voxel),
                "SomaX": soma_xyz[0] if len(soma_xyz) > 0 else "",
                "SomaY": soma_xyz[1] if len(soma_xyz) > 1 else "",
                "SomaZ": soma_xyz[2] if len(soma_xyz) > 2 else "",
                "PortalRegion": row.get("portal_region", ""),
                "CatalogSource": source_kind,
                "SourcePath": source_path,
                "SourceDate": snapshot.get("source_date") or "",
                "FetchedAt": snapshot.get("fetched_at") or "",
                "SnapshotID": snapshot.get("snapshot_id") or "",
                "CatalogSHA256": snapshot.get("sha256") or "",
                "SomaCatalogSHA256": (
                    soma_source.get("sha256") or side_source.get("sha256") or ""),
                "AtlasSHA256": result_source.get("atlas_sha256") or "",
                "RecordedAt": recorded.isoformat(timespec="seconds"),
            })
    payload = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "row_count": len(snapshot.get("rows", ())),
        "side_counts": side_result.get("counts") or _side_counts(side_results),
    }


def lookup_neuron_side(root: str | Path | None, sample_id: str,
                       neuron_id: str) -> dict:
    """Return a side for one unambiguous workbook Summary identity."""
    result = {"status": "unknown", "side": None, "reason": "", "source": None}
    if not root:
        result["reason"] = "sources.neuron_tables.root is not configured"
        return result
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id or ""):
        result["reason"] = "invalid sample identity"
        return result
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.swc", neuron_id or ""):
        result["reason"] = "invalid exact neuron identity"
        return result
    try:
        path = _resolve_side_workbook(root, sample_id).resolve()
    except ValueError as exc:
        result["reason"] = str(exc)
        return result
    if not path.is_file():
        result["reason"] = "per-sample ReMAP or FULL workbook is unavailable"
        return result
    try:
        before = path.stat()
        if before.st_size > 64 * 1024 * 1024:
            result["reason"] = "FULL workbook exceeds 64 MiB limit"
            return result
        payload = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            result["reason"] = "FULL workbook changed during read"
            return result
        digest = hashlib.sha256(payload).hexdigest()
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=True)
        try:
            if "Summary" not in workbook.sheetnames:
                result["reason"] = "FULL workbook has no Summary sheet"
                return result
            sheet = workbook["Summary"]
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, ())
            required = ("SampleID", "NeuronID", "Soma_Region")
            if any(headers.count(key) != 1 for key in required):
                result["reason"] = "Summary identity/region columns are missing or duplicated"
                return result
            columns = {key: headers.index(key) for key in required}
            side_column = headers.index("Soma_Side") if headers.count("Soma_Side") == 1 else None
            matches = []
            for row_number, row in enumerate(rows, 2):
                if (str(row[columns["SampleID"]]).strip() == sample_id and
                        str(row[columns["NeuronID"]]).strip() == neuron_id):
                    matches.append((row_number, row))
                    if len(matches) > 1:
                        break
            if len(matches) != 1:
                result["reason"] = ("duplicate exact Summary identity" if matches else
                                    "exact Summary identity not found")
                return result
            row_number, row = matches[0]
            region = str(row[columns["Soma_Region"]] or "").strip()
            region_side = side_from_region(region)
            declared_side = (
                str(row[side_column] or "").strip().upper()
                if side_column is not None else "")
            if declared_side in {"L", "R"} and region_side is not None:
                expected = "Left" if declared_side == "L" else "Right"
                if expected != region_side:
                    result["reason"] = "Summary side conflicts with region prefix"
                    return result
            if region_side is not None:
                side_name = region_side
                side_method = "Soma_Region_prefix"
            elif declared_side in {"L", "R"}:
                side_name = "Left" if declared_side == "L" else "Right"
                side_method = "Summary_Soma_Side"
            else:
                result["reason"] = "Summary side is absent and region has no explicit side prefix"
                return result
            result.update(status="verified", side=side_name,
                          reason=f"exact Summary identity; side from {side_method}",
                          source={"path": str(path), "sha256": digest, "bytes": len(payload),
                                  "sheet": "Summary", "row": row_number,
                                  "sample_id": sample_id, "neuron_id": neuron_id,
                                  "soma_side": declared_side or None,
                                  "soma_region": region, "side_method": side_method,
                                  "producer": ("remap_results" if path.name.endswith("_results.xlsx")
                                               else "full_workbook")})
            return result
        finally:
            workbook.close()
    except (OSError, ValueError, ImportError, BadZipFile, IndexError, TypeError) as exc:
        result["reason"] = f"neuron workbook could not be verified: {exc}"
        return result


def _validate_sample_id(sample_id: str) -> None:
    if not isinstance(sample_id, str):
        raise TypeError("sample_id must be an exact string identifier")
    if (not sample_id or sample_id != sample_id.strip()
            or any(ord(char) < 32 for char in sample_id)):
        raise ValueError("sample_id must be a nonempty exact identifier without control characters")


def _safe_neuron_id(neuron_id, context: str, sample_id: str) -> str:
    if (not isinstance(neuron_id, str) or not neuron_id or neuron_id != neuron_id.strip()
            or "/" in neuron_id or "\\" in neuron_id or ":" in neuron_id
            or ".." in neuron_id or any(ord(char) < 32 for char in neuron_id)):
        raise ValueError(
            f"{context}: neuron ID must be an exact safe basename without path separators, "
            f"colon, or '..' for sample {sample_id!r}")
    return neuron_id


def _list_live_neurons(sample_id: str, catalog: dict) -> dict:
    request_url = catalog_request_url(sample_id, catalog)
    timeout_value = catalog.get("timeout_seconds", 10)
    byte_value = catalog.get("max_response_bytes", 8 * 1024 * 1024)
    if (isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float))
            or not math.isfinite(timeout_value) or not 1 <= timeout_value <= 60):
        raise ValueError("sources.neuron_catalog.timeout_seconds must be between 1 and 60")
    if (isinstance(byte_value, bool) or not isinstance(byte_value, int)
            or not 1024 <= byte_value <= 32 * 1024 * 1024):
        raise ValueError("sources.neuron_catalog.max_response_bytes must be between 1024 and 33554432")
    timeout = float(timeout_value)
    max_bytes = byte_value
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.getcode()
        raw_bytes = response.read(max_bytes + 1)
    if status != 200:
        raise RuntimeError(f"IONData neuron catalog returned HTTP {status}: {request_url}")
    if len(raw_bytes) > max_bytes:
        raise ValueError(f"IONData neuron catalog exceeded the {max_bytes}-byte response limit")
    try:
        source_rows = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"IONData neuron catalog returned invalid UTF-8 JSON: {request_url}") from exc
    if not isinstance(source_rows, list):
        raise ValueError("IONData neuron catalog response must be a JSON array")

    rows = []
    seen = set()
    for index, source_row in enumerate(source_rows):
        if not isinstance(source_row, dict):
            raise ValueError(f"IONData catalog row {index + 1} must be an object")
        row_sample = source_row.get("sampleid")
        if not isinstance(row_sample, str) or row_sample != sample_id:
            raise ValueError(
                f"IONData catalog row {index + 1} has sampleid {row_sample!r}; "
                f"expected exact sample {sample_id!r}")
        neuron_id = _safe_neuron_id(source_row.get("name"), f"IONData row {index + 1}", sample_id)
        if neuron_id in seen:
            raise ValueError(f"IONData catalog has duplicate neuron ID {neuron_id!r} for sample {sample_id!r}")
        seen.add(neuron_id)
        rows.append({
            "sample_id": sample_id,
            "neuron_id": neuron_id,
            "portal_region": _string_or_empty(source_row.get("region"), f"row {index + 1} region"),
            "type": _string_or_empty(source_row.get("type"), f"row {index + 1} type"),
            "exclude": _string_or_empty(source_row.get("exclude"), f"row {index + 1} exclude"),
            "comment": _string_or_empty(source_row.get("comment"), f"row {index + 1} comment"),
        })
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    response_sha = hashlib.sha256(raw_bytes).hexdigest()
    return {"sample_id": sample_id, "monkey_id": "", "source_kind": "live-iondata",
            "source_path": request_url, "request_url": request_url, "source_date": "live",
            "fetched_at": fetched_at, "sha256": response_sha, "source_size": len(raw_bytes),
            "count": len(rows), "rows": rows,
            "snapshot_id": hashlib.sha256(
                f"{sample_id}\0{fetched_at}\0{response_sha}".encode("utf-8")).hexdigest()}


def catalog_request_url(sample_id: str, catalog: dict) -> str:
    """Resolve the observed IONData route without sending a request."""
    _validate_sample_id(sample_id)
    host = str(catalog.get("host") or "").rstrip("/")
    parsed_host = urllib.parse.urlsplit(host)
    if (parsed_host.scheme not in {"http", "https"} or not parsed_host.netloc
            or parsed_host.username or parsed_host.password
            or parsed_host.path or parsed_host.query or parsed_host.fragment):
        raise ValueError("sources.neuron_catalog.host must be an HTTP(S) origin without credentials or path")
    try:
        parsed_host.port
    except ValueError as exc:
        raise ValueError("sources.neuron_catalog.host has an invalid port") from exc
    encoded_id = urllib.parse.quote(sample_id, safe="")
    return f"{host}/neuronbrowser/api/user/selectNeurons?id={encoded_id}"


def soma_request_url(sample_id: str, catalog: dict) -> str:
    """Resolve the observed IONData soma route without sending a request."""
    catalog_url = catalog_request_url(sample_id, catalog)
    suffix = f"selectNeurons?id={urllib.parse.quote(sample_id, safe='')}"
    if not catalog_url.endswith(suffix):
        raise ValueError("IONData catalog URL does not use the expected selectNeurons route")
    return catalog_url[:-len(suffix)] + f"getSoma?fMOST_id={urllib.parse.quote(sample_id, safe='')}"


def _string_or_empty(value, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"IONData {label} must be a scalar string/number/boolean")
    return str(value)


def _list_csv_neurons(sample_id: str, catalog: dict) -> dict:
    if not catalog.get("path"):
        raise ValueError("no sources.neuron_catalog.path is configured for CSV mode")
    path = Path(catalog["path"]).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"configured neuron catalog does not exist: {path}")
    columns = catalog.get("columns") or {}
    sample_column = str(columns.get("sample", "sample"))
    neuron_column = str(columns.get("neuron_id", "neuron_id"))
    region_column = str(columns.get("portal_region", "portal_region"))
    monkey_column = columns.get("monkey")
    before = path.stat()
    raw_bytes = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"{path}: neuron catalog changed while it was being read; retry the list load")
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    required = {sample_column, neuron_column, region_column}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        missing = sorted(required - set(reader.fieldnames or ()))
        raise ValueError(f"{path}: neuron catalog is missing required column(s): {missing}")
    if monkey_column and monkey_column not in reader.fieldnames:
        raise ValueError(f"{path}: neuron catalog is missing monkey column {monkey_column!r}")

    rows = []
    seen = {}
    monkeys = set()
    for line_number, source_row in enumerate(reader, 2):
        exact_sample = source_row.get(sample_column, "")
        if exact_sample != sample_id:
            continue
        neuron_id = source_row.get(neuron_column, "")
        _safe_neuron_id(neuron_id, f"{path}:{line_number}", sample_id)
        if neuron_id in seen:
            raise ValueError(
                f"{path}:{line_number}: duplicate neuron ID {neuron_id!r} for sample {sample_id!r}; "
                f"first seen on line {seen[neuron_id]}"
            )
        seen[neuron_id] = line_number
        region = source_row.get(region_column, "")
        region = "" if region is None else region
        monkey = source_row.get(monkey_column, "") if monkey_column else ""
        monkey = "" if monkey is None else monkey
        if monkey:
            monkeys.add(monkey)
        rows.append({"sample_id": sample_id, "neuron_id": neuron_id,
                     "portal_region": region, "monkey_id": monkey})
    if len(monkeys) > 1:
        raise ValueError(f"{path}: sample {sample_id!r} maps to multiple monkey IDs: {sorted(monkeys)}")
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    return {"sample_id": sample_id, "monkey_id": next(iter(monkeys), ""),
            "source_kind": "csv", "source_path": str(path),
            "source_date": str(catalog.get("source_date") or "unknown"),
            "request_url": None, "fetched_at": None,
            "sha256": raw_sha, "source_size": after.st_size,
            "source_mtime_ns": after.st_mtime_ns, "count": len(rows), "rows": rows}


def catalog_snapshot_unchanged(snapshot: dict) -> bool:
    """Fast invalidation guard for a loaded list; the full SHA is captured at load."""
    if snapshot.get("source_kind") == "live-iondata":
        try:
            expected_id = hashlib.sha256(
                f"{snapshot['sample_id']}\0{snapshot['fetched_at']}\0{snapshot['sha256']}".encode("utf-8")
            ).hexdigest()
            return (isinstance(snapshot.get("sample_id"), str)
                    and isinstance(snapshot.get("snapshot_id"), str)
                    and snapshot["snapshot_id"] == expected_id
                    and len(snapshot.get("sha256", "")) == 64
                    and isinstance(snapshot.get("request_url"), str)
                    and snapshot.get("request_url", "").startswith(("http://", "https://"))
                    and all(row.get("snapshot_id") == expected_id for row in snapshot.get("rows", [])))
        except (KeyError, TypeError, AttributeError):
            return False
    try:
        stat = Path(snapshot["source_path"]).stat()
    except (KeyError, OSError, TypeError):
        return False
    return (stat.st_size == snapshot.get("source_size")
            and stat.st_mtime_ns == snapshot.get("source_mtime_ns"))


def catalog_matches_sample(requested_sample: str, current_sample: str) -> bool:
    """Guard asynchronous catalog results and row selection against sample edits."""
    return str(requested_sample) == str(current_sample).strip()


def catalog_selection_id(sample_id: str, current_sample: str, snapshot: dict,
                         row: dict) -> str | None:
    """Return the exact SWC ID only for a current row from an unchanged snapshot."""
    if not catalog_matches_sample(sample_id, current_sample):
        return None
    if (row.get("sample_id") != str(sample_id)
            or not catalog_snapshot_unchanged(snapshot)
            or (snapshot.get("source_kind") == "live-iondata"
                and (row.get("snapshot_id") != snapshot.get("snapshot_id")
                     or row not in snapshot.get("rows", [])))):
        return None
    neuron_id = row.get("neuron_id")
    return neuron_id if isinstance(neuron_id, str) and neuron_id else None


def read_swc(path: str | Path) -> SWCTree:
    """Read a checked SWC and expose the root/edge protocol used by renderers."""
    path = Path(path)
    nodes: dict[int, SWCNode] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 7:
            raise ValueError(f"{path}:{line_no}: SWC row must have 7 fields")
        try:
            node_id, kind = int(fields[0]), int(fields[1])
            xyzr = tuple(float(v) for v in fields[2:6])
            parent_id = int(fields[6])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_no}: invalid numeric SWC field") from exc
        import math
        if node_id in nodes or not all(math.isfinite(v) for v in xyzr) or xyzr[3] < 0:
            raise ValueError(f"{path}:{line_no}: duplicate id or invalid coordinate/radius")
        nodes[node_id] = SWCNode(node_id, kind, *xyzr, parent_id)
    if not nodes:
        raise ValueError(f"{path}: no SWC nodes")
    roots = [node for node in nodes.values() if node.parent_id == -1]
    if len(roots) != 1:
        raise ValueError(f"{path}: expected exactly one root, found {len(roots)}")
    children: dict[int, list[int]] = {node_id: [] for node_id in nodes}
    for node in nodes.values():
        if node.parent_id != -1:
            if node.parent_id not in nodes:
                raise ValueError(f"{path}: node {node.id} has missing parent {node.parent_id}")
            children[node.parent_id].append(node.id)
    reached = set()
    pending = [roots[0].id]
    while pending:
        node_id = pending.pop()
        if node_id in reached:
            raise ValueError(f"{path}: cycle or repeated parent path at node {node_id}")
        reached.add(node_id)
        pending.extend(children[node_id])
    if len(reached) != len(nodes):
        raise ValueError(f"{path}: {len(nodes) - len(reached)} node(s) are disconnected from the root")
    edges = [SWCEdge([node, nodes[child_id]]) for node in nodes.values()
             for child_id in children[node.id]]
    return SWCTree(roots[0], edges, list(nodes.values()))


class LocalSWCProvider:
    def __init__(self, config=None):
        self.config = config if config is not None else load()

    def getRawNeuronTreeByID(self, sample_id: str, neuron_id: str):
        sample_id = str(sample_id)
        if not sample_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in sample_id):
            raise ValueError("sample_id must be a simple identifier")
        sample = self.config.get("samples", {}).get(str(sample_id), {})
        name = str(neuron_id)
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("neuron_id must be a filename, not a path")
        if not name.lower().endswith(".swc"):
            name += ".swc"
        roots = []
        managed_root = (self.config.get("defaults") or {}).get("cache_root")
        if managed_root:
            roots.append(Path(managed_root) / "swc_raw" / sample_id)
        if sample.get("swc_cache") is not None:
            roots.append(Path(sample["swc_cache"]))
        legacy_root = self.config.get("sources", {}).get("legacy_raw_swc_root")
        if legacy_root:
            roots.append(Path(legacy_root) / sample_id)
        visited = set()
        for root in roots:
            root = root.resolve()
            if root in visited:
                continue
            visited.add(root)
            path = root / name
            if path.is_file():
                return read_swc(path)
        return None


class PortalSWCProvider:
    """Fetch a missing raw SWC from the configured portal and cache it locally.

    ``sources.http_host`` serves the sample metadata and
    ``sources.raw_swc_base`` serves ``<project>/<sample>/swc_raw/<neuron>``.
    A fetched file is written to ``sources.legacy_raw_swc_root/<sample>/`` so
    later loads reuse it without another request.
    """

    def __init__(self, config=None, timeout: float = 30.0, cache_root=None):
        self.config = config if config is not None else load()
        sources = self.config.get("sources") or {}
        self.host = str(sources.get("http_host") or sources.get("http_base_url") or "").rstrip("/")
        self.raw_base = str(sources.get("raw_swc_base") or "").rstrip("/")
        root = sources.get("legacy_raw_swc_root")
        self.cache_root = Path(cache_root) if cache_root else (Path(root) if root else None)
        if cache_root is not None:
            _guard_managed_cache(self.cache_root, sources, allow_equal_raw=True)
        self.timeout = float(timeout)
        self._projects: dict[str, str] = {}

    def _read(self, url: str) -> bytes:
        return _read_bounded_swc(url, self.timeout, 64 * 1024 * 1024)

    def getRawNeuronTreeByID(self, sample_id: str, neuron_id: str, *, refresh=False):
        if not self.host or not self.raw_base:
            return None
        sample = str(sample_id)
        if not sample or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                             for c in sample):
            raise ValueError("sample_id must be a simple identifier")
        name = str(neuron_id)
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("neuron_id must be a filename, not a path")
        if not name.lower().endswith(".swc"):
            name += ".swc"
        cache = (self.cache_root / sample / name) if self.cache_root else None
        if cache and cache.is_file() and not refresh:
            return read_swc(cache)
        project = self._projects.get(sample)
        if project is None:
            query = urllib.parse.urlencode({"project_id": "", "fMOST_id": sample})
            info_url = f"{self.host}/neuronbrowser/api/user/getSampleInfo?{query}"
            info = json.loads(self._read(info_url).decode("utf-8"))
            project = str((info or [{}])[0].get("project_id") or "")
            self._projects[sample] = project
        if not project:
            raise RuntimeError(
                f"Portal metadata for {sample} did not declare a project_id")
        raw_url = (f"{self.raw_base}/{urllib.parse.quote(project)}/{sample}/swc_raw/"
                   f"{urllib.parse.quote(name)}")
        payload = self._read(raw_url)
        text = payload.decode("utf-8-sig")
        if not text.strip():
            raise RuntimeError(f"Portal returned an empty SWC for {sample}/{name}")
        if cache:
            _publish_swc_versioned(cache, payload, raw_url, role="raw",
                                   sample_id=sample, neuron_id=name)
            return read_swc(cache)
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".swc", delete=False, encoding="utf-8")
        try:
            handle.write(text)
            handle.close()
            return read_swc(handle.name)
        finally:
            try:
                os.remove(handle.name)
            except OSError:
                pass


class IONData:
    """Compatibility-shaped provider with explicit live and cached-only modes."""
    def __init__(self, *args, **kwargs):
        self._local = LocalSWCProvider()
        self._provider_args = args
        self._provider_kwargs = kwargs
        self._provider = None
        self._provider_checked = False
        self._portal = None

    def getRawNeuronTreeByID(self, sample_id: str, neuron_id: str, *, refresh=True):
        if refresh:
            if _provider_factory is not None:
                if not self._provider_checked:
                    self._provider = _provider_factory(*self._provider_args, **self._provider_kwargs)
                    self._provider_checked = True
                return self._provider.getRawNeuronTreeByID(sample_id, neuron_id)
            if self._portal is None:
                config = load()
                managed = Path(config["defaults"]["cache_root"]) / "swc_raw"
                self._portal = PortalSWCProvider(config, cache_root=managed)
            return self._portal.getRawNeuronTreeByID(sample_id, neuron_id, refresh=True)
        tree = self._local.getRawNeuronTreeByID(sample_id, neuron_id)
        if tree is not None:
            return tree
        raise FileNotFoundError(f"raw SWC is not cached for {sample_id}/{neuron_id}")

    def getNeuronByID(self, sample_id: str, neuron_id: str, *,
                      config=None, cache_root=None, refresh=True) -> str:
        """Return the supplied processed SWC, with portal access explicitly opted in."""
        resolved = config if config is not None else load()
        if cache_root is None:
            cache_root = Path(resolved["defaults"]["cache_root"]) / "swc_processed"
        return load_processed_neuron(resolved,
                                     sample_id, neuron_id, cache_root=cache_root,
                                     allow_download=refresh, refresh=refresh)

    def getNeuronTreeByID(self, sample_id: str, neuron_id: str, **kwargs):
        text = self.getNeuronByID(sample_id, neuron_id, **kwargs)
        with tempfile.NamedTemporaryFile("w", suffix=".swc", delete=False,
                                         encoding="utf-8") as stream:
            stream.write(text)
            path = stream.name
        try:
            return read_swc(path)
        finally:
            os.unlink(path)


def processed_neuron_plan(config: dict, sample_id: str, neuron_id: str, *,
                          cache_root=None) -> dict:
    """Resolve one exact processed source without network access or writes."""
    _validate_sample_id(sample_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id):
        raise ValueError("sample_id must be a simple identifier")
    _safe_neuron_id(neuron_id, "processed SWC", sample_id)
    if not neuron_id.lower().endswith(".swc"):
        raise ValueError("processed neuron_id must include .swc")
    sources = config.get("sources") or {}
    if cache_root is not None:
        _guard_managed_cache(Path(cache_root), sources)
    brain = sources.get("brain_view") or {}
    roots = [Path(cache_root)] if cache_root else []
    if brain.get("processed_swc_root"):
        roots.append(Path(brain["processed_swc_root"]))
    paths = [resolve_declared_raw_swc(root, sample_id, neuron_id) for root in roots]
    existing = next((path for path in paths if path.is_file()), None)
    host = str(sources.get("http_host") or sources.get("http_base_url") or "").rstrip("/")
    if host and not re.fullmatch(r"https?://[^/?#]+", host):
        raise ValueError("sources.http_host must be an HTTP(S) origin")
    query = urllib.parse.urlencode({"sampleid": sample_id, "neuronid": neuron_id})
    return {"sample_id": sample_id, "neuron_id": neuron_id,
            "local_path": str(existing) if existing else None,
            "cache_path": str(paths[0]) if cache_root else None,
            "url": f"{host}/neuronbrowser/api/user/getSWC?{query}" if host else None}


def _guard_managed_cache(cache_root: Path, sources: dict, *, allow_equal_raw=False) -> None:
    """Keep an active managed cache away from declared scientific source roots."""
    cache = cache_root.expanduser().resolve()
    brain = sources.get("brain_view") or {}
    for index, value in enumerate((sources.get("legacy_raw_swc_root"), brain.get("processed_swc_root"))):
        if value:
            declared = Path(value).expanduser().resolve()
            if index == 0 and allow_equal_raw and cache == declared:
                continue
            if cache == declared or cache.is_relative_to(declared):
                raise ValueError("managed SWC cache must be outside declared source roots")


def load_processed_neuron(config: dict, sample_id: str, neuron_id: str, *,
                          cache_root=None, allow_download=False,
                          refresh=False,
                          timeout_seconds=30, max_response_bytes=64 * 1024 * 1024) -> str:
    """Load a validated supplied processed SWC; never write a shared source root."""
    plan = processed_neuron_plan(config, sample_id, neuron_id, cache_root=cache_root)
    if plan["local_path"] and not refresh:
        path = Path(plan["local_path"])
        read_swc(path)
        return path.read_text(encoding="utf-8-sig")
    if not allow_download:
        raise FileNotFoundError(f"processed SWC is not cached for {sample_id}/{neuron_id}")
    if not cache_root or not plan["cache_path"] or not plan["url"]:
        raise ValueError("processed portal fetch requires an explicit writable cache_root and sources.http_host")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 60
            or isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int)
            or not 1024 <= max_response_bytes <= 64 * 1024 * 1024):
        raise ValueError("processed fetch timeout or byte limit is invalid")
    payload = _read_bounded_swc(plan["url"], float(timeout_seconds), max_response_bytes)
    text = payload.decode("utf-8-sig")
    target = Path(plan["cache_path"])
    _publish_swc_versioned(target, payload, plan["url"],
                           role="processed", sample_id=sample_id, neuron_id=neuron_id,
                           freshness="live-check")
    return target.read_text(encoding="utf-8-sig")


def _publish_swc_versioned(target: Path, payload: bytes, url: str, *, role="raw",
                           sample_id=None, neuron_id=None, freshness="live-check") -> None:
    """Validate first, serialize updates, and retain earlier managed bytes by hash."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", suffix=".swc", dir=target.parent,
                                     delete=False) as stream:
        stream.write(payload)
        temporary = Path(stream.name)
    lock = target.with_name(target.name + ".lock")
    acquired = False
    try:
        read_swc(temporary)
        incoming_hash = hashlib.sha256(temporary.read_bytes()).hexdigest()
        lock.mkdir()
        acquired = True
        previous_hash = None
        prior_path = None
        if target.exists():
            read_swc(target)
            previous_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if previous_hash != incoming_hash:
                history = target.parent / ".history" / target.name
                history.mkdir(parents=True, exist_ok=True)
                prior_path = history / f"{previous_hash}.swc"
                if not prior_path.exists():
                    prior_path.write_bytes(target.read_bytes())
                if hashlib.sha256(prior_path.read_bytes()).hexdigest() != previous_hash:
                    raise RuntimeError("prior cached SWC history hash mismatch")
        changed = previous_hash != incoming_hash
        if changed:
            os.replace(temporary, target)
        prior_receipt = target.with_name(target.name + ".source.json")
        last_change = None
        previous_version = None
        if prior_receipt.is_file():
            try:
                prior = json.loads(prior_receipt.read_text(encoding="utf-8"))
                last_change = prior.get("last_changed_at_utc")
                previous_version = prior.get("previous_version_path")
            except (OSError, ValueError):
                pass
        now = datetime.now(timezone.utc).isoformat()
        receipt = {"role": role, "sample_id": sample_id, "neuron_id": neuron_id,
                   "origin_url": url, "retrieved_at_utc": now,
                   "last_changed_at_utc": now if changed else last_change,
                   "freshness": freshness, "sha256": incoming_hash,
                   "response_sha256": hashlib.sha256(payload).hexdigest(),
                   "previous_sha256": previous_hash,
                   "previous_version_path": str(prior_path) if prior_path else previous_version,
                   "changed": changed, "active_path": str(target)}
        receipt_path = target.with_name(target.name + ".source.json")
        with tempfile.NamedTemporaryFile("w", suffix=".json", dir=target.parent,
                                         delete=False, encoding="utf-8") as record:
            json.dump(receipt, record, indent=2)
            record_path = Path(record.name)
        os.replace(record_path, receipt_path)
    finally:
        temporary.unlink(missing_ok=True)
        if acquired:
            lock.rmdir()


def _read_bounded_swc(url: str, timeout: float, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "VisPa"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        payload = response.read(limit + 1)
    if len(payload) > limit or not payload:
        raise ValueError("HTTP response is empty or exceeds byte limit")
    return payload


# Read-only workbook/resource planning. No ReMAP code is imported or executed.
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_WORKBOOK_NAME = re.compile(r"^(?P<sample>[A-Za-z0-9_-]+)_results(?:_[0-9]{8}_[0-9]{6})?\.xlsx$", re.I)


def _file_record(path: Path, *, inspect: bool = False, frame=None, units=None,
                 acquisition_date=None, processing_date=None, source_date=None) -> dict:
    record = {"path": str(path.resolve()), "exists": path.is_file(),
              "frame": frame or "unknown", "units": units or "unknown",
              "acquisition_date": acquisition_date or "unknown",
              "processing_date": processing_date or "unknown", "source_date": source_date or "unknown",
              "sha256": None, "size": None, "mtime_ns": None}
    if record["exists"]:
        before = path.stat()
        record.update(size=before.st_size, mtime_ns=before.st_mtime_ns)
        if inspect:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f"source changed during checksum: {path}")
            record["sha256"] = digest.hexdigest()
    return record


def locate_sample_table(sample_id: str, config: dict, *, selected: str | Path | None = None,
                        inspect: bool = False) -> dict:
    """Select exactly one declared workbook; multiple candidates require a choice."""
    _validate_sample_id(sample_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id):
        raise ValueError("sample_id must be a simple folder identifier")
    source = (config.get("sources") or {}).get("neuron_tables") or {}
    root_value = source.get("root")
    plan = {"sample_id": sample_id, "root": str(root_value) if root_value else None,
            "layout": source.get("layout", "per_sample"), "status": "not_configured",
            "candidates": [], "selected": None, "source": None}
    if not root_value:
        return plan
    if plan["layout"] != "per_sample":
        raise ValueError("only neuron_tables.layout='per_sample' is supported")
    folder = Path(root_value).expanduser().resolve() / sample_id
    if not folder.is_dir():
        plan["status"] = "missing"
        return plan
    candidates = sorted(p for p in folder.iterdir() if p.is_file() and
                        (match := _WORKBOOK_NAME.fullmatch(p.name)) and match.group("sample") == sample_id)
    plan["candidates"] = [str(p) for p in candidates]
    mapping = source.get("selected_workbooks") or {}
    declared = selected if selected is not None else mapping.get(sample_id)
    if declared is not None:
        choice = Path(declared)
        choice = choice if choice.is_absolute() else folder / choice
        if choice.resolve() not in {p.resolve() for p in candidates}:
            raise ValueError(f"selected workbook is not an exact candidate for {sample_id}: {declared}")
    elif len(candidates) == 1:
        choice = candidates[0]
    elif len(candidates) > 1:
        plan["status"] = "ambiguous"
        return plan
    else:
        plan["status"] = "missing"
        return plan
    plan.update(status="resolved", selected=str(choice.resolve()),
                source=_file_record(choice, inspect=inspect,
                                    frame=source.get("frame"), units=source.get("units")))
    return plan


def _workbook_rows(path: Path, sheet: str = "Summary") -> list[dict[str, str]]:
    """Read a bounded xlsx sheet as text, retaining stored string identifiers."""
    with zipfile.ZipFile(path) as book:
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        matches = [s for s in workbook.findall("m:sheets/m:sheet", _NS) if s.get("name") == sheet]
        if len(matches) != 1:
            raise ValueError(f"{path}: expected one {sheet} sheet")
        rel_id = matches[0].get("{" + _NS["r"] + "}id")
        rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next((r.get("Target") for r in rels if r.get("Id") == rel_id), None)
        if not target:
            raise ValueError(f"{path}: sheet relationship is missing")
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in Path(member).parts:
            raise ValueError("unsafe workbook member path")
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            strings = ET.fromstring(book.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter("{" + _NS["m"] + "}t")) for si in strings]
        xml = ET.fromstring(book.read(member))
        rows = []
        for row in xml.findall("m:sheetData/m:row", _NS):
            cells = {}
            for cell in row.findall("m:c", _NS):
                ref = cell.get("r", "")
                column = re.match(r"[A-Z]+", ref)
                if not column:
                    continue
                value = cell.find("m:v", _NS)
                if cell.get("t") == "inlineStr":
                    content = "".join(t.text or "" for t in cell.iter("{" + _NS["m"] + "}t"))
                elif value is None:
                    content = ""
                elif cell.get("t") == "s":
                    content = shared[int(value.text)]
                else:
                    content = value.text or ""
                cells[column.group()] = content
            rows.append(cells)
            if len(rows) > 100000:
                raise ValueError("Summary sheet exceeds 100000 rows")
    if not rows:
        raise ValueError("Summary sheet is empty")
    columns = rows[0]
    if len(set(columns.values())) != len(columns):
        raise ValueError("Summary sheet has duplicate headers")
    return [{name: row.get(letter, "") for letter, name in columns.items()} for row in rows[1:]]


def load_summary_neuron(sample_id: str, neuron_id: str, config: dict, *,
                        selected: str | Path | None = None, inspect: bool = False) -> dict:
    """Find one exact SampleID/NeuronID row without numeric ID coercion."""
    _validate_sample_id(sample_id)
    _safe_neuron_id(neuron_id, "Summary", sample_id)
    plan = locate_sample_table(sample_id, config, selected=selected, inspect=inspect)
    if plan["status"] != "resolved":
        raise ValueError(f"neuron table is {plan['status']}; select one workbook explicitly")
    rows = _workbook_rows(Path(plan["selected"]))
    if not rows or not {"SampleID", "NeuronID"}.issubset(rows[0]):
        raise ValueError("Summary requires SampleID and NeuronID columns")
    matching = []
    seen = set()
    for row in rows:
        identity = (row["SampleID"], row["NeuronID"])
        if identity in seen:
            raise ValueError(f"duplicate Summary identity {identity!r}")
        seen.add(identity)
        if row["SampleID"] == sample_id and row["NeuronID"] == neuron_id:
            matching.append(row)
        elif row["NeuronID"] == neuron_id and row["SampleID"] != sample_id:
            raise ValueError(f"Summary neuron {neuron_id!r} has mismatched SampleID")
    if len(matching) != 1:
        raise ValueError(f"no exact Summary row for {sample_id!r}/{neuron_id!r}")
    return {"sample_id": sample_id, "neuron_id": neuron_id, "row": matching[0], "workbook": plan}


def plan_neuron_resources(sample_id: str, neuron_id: str, config: dict, *,
                          selected_workbook: str | Path | None = None,
                          inspect: bool = False) -> dict:
    """Plan declared resources without loading volumes, fetching data, or transforming SWCs."""
    _validate_sample_id(sample_id)
    _safe_neuron_id(neuron_id, "resource plan", sample_id)
    sample = (config.get("samples") or {}).get(sample_id) or {}
    sources = config.get("sources") or {}
    name = neuron_id if neuron_id.lower().endswith(".swc") else neuron_id + ".swc"
    brain = sources.get("brain_view") or {}
    atlas = sources.get("atlas") or {}
    if isinstance(atlas, (str, Path)):
        atlas = {"path": atlas}
    raw_root = sources.get("legacy_raw_swc_root")
    brain_frame = brain.get("coordinate_frame")
    brain_units = brain.get("coordinate_units")
    plan = {"sample_id": sample_id, "neuron_id": neuron_id, "resources": {},
            "coordinate_relation": "unknown", "transform": None}
    for label, path, metadata in (
        ("raw_swc", Path(raw_root) / sample_id / name if raw_root else None,
         {"frame": sources.get("raw_swc_coordinate_frame"), "units": sources.get("raw_swc_coordinate_units"),
          "source_date": sources.get("raw_swc_source_date")}),
        ("processed_swc", Path(brain["processed_swc_root"]) / sample_id / name
         if brain.get("processed_swc_root") else None,
         {"frame": brain_frame, "units": brain_units, "processing_date": brain.get("processing_date"),
          "source_date": brain.get("source_date")}),
        ("mesh", brain.get("mesh_path"),
         {"frame": brain_frame, "units": brain_units, "processing_date": brain.get("processing_date"),
          "source_date": brain.get("source_date")}),
        ("ds00_processed", sample.get("ds00_processed"),
         {"frame": sample.get("ds00_coordinate_frame"), "units": sample.get("ds00_coordinate_units"),
          "acquisition_date": sample.get("ds00_acquisition_date"),
          "processing_date": sample.get("ds00_processing_date")}),
        ("resample_5um", sample.get("resample_5um"),
         {"frame": sample.get("resample_5um_coordinate_frame"), "units": sample.get("resample_5um_coordinate_units"),
          "acquisition_date": sample.get("resample_5um_acquisition_date"),
          "processing_date": sample.get("resample_5um_processing_date")}),
        ("atlas", atlas.get("path"),
         {"frame": atlas.get("coordinate_frame"), "units": atlas.get("coordinate_units"),
          "acquisition_date": atlas.get("acquisition_date"), "processing_date": atlas.get("processing_date")}),
    ):
        plan["resources"][label] = _file_record(Path(path), inspect=inspect, **metadata) if path else None
    plan["workbook"] = locate_sample_table(sample_id, config, selected=selected_workbook, inspect=inspect)
    return plan


def load_raw_neuron(config: dict, sample_id: str, neuron_id: str, *,
                    allow_download: bool = False) -> SWCTree:
    """Load a declared native raw SWC; portal retrieval requires explicit opt-in."""
    _validate_sample_id(sample_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id):
        raise ValueError("sample_id must be a simple folder identifier")
    _safe_neuron_id(neuron_id, "raw SWC", sample_id)
    name = neuron_id if neuron_id.lower().endswith(".swc") else neuron_id + ".swc"
    sources = config.get("sources") or {}
    raw_root = sources.get("legacy_raw_swc_root")
    managed_root = (config.get("defaults") or {}).get("cache_root")
    managed_path = (resolve_declared_raw_swc(Path(managed_root) / "swc_raw", sample_id, name)
                    if managed_root else None)
    if managed_path and managed_path.is_file():
        return read_swc(managed_path)
    path = None
    if raw_root:
        path = resolve_declared_raw_swc(raw_root, sample_id, name)
        if path.is_file():
            return read_swc(path)
    if not allow_download:
        raise FileNotFoundError(f"native raw SWC is not cached for {sample_id}/{name}")
    if not raw_root:
        raise ValueError("portal download requires sources.legacy_raw_swc_root")
    portal = PortalSWCProvider(config, cache_root=Path(managed_root) / "swc_raw" if managed_root else None)
    tree = portal.getRawNeuronTreeByID(sample_id, name)
    if tree is None:
        raise FileNotFoundError(f"portal raw SWC source is not configured for {sample_id}/{name}")
    fetched_path = managed_path or path
    if fetched_path is None or not fetched_path.is_file():
        raise RuntimeError("portal did not cache native raw SWC at its declared path")
    return read_swc(fetched_path)


def resolve_declared_raw_swc(raw_root: str | Path, sample_id: str, name: str) -> Path:
    """Resolve one declared raw SWC, allowing a verified Windows MSIX root alias."""
    _validate_sample_id(sample_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id):
        raise ValueError("sample_id must be a simple folder identifier")
    _safe_neuron_id(name, "raw SWC", sample_id)
    root = Path(raw_root).expanduser().resolve()
    path = (root / sample_id / name).resolve()
    if path.is_relative_to(root):
        return path
    # Windows MSIX may resolve a child through LocalCache although resolving
    # the root alone retains AppData. Only accept the alternate spelling when
    # its existing root is the very same filesystem directory.
    if path.name == name and path.parent.name == sample_id:
        try:
            if path.parent.parent.samefile(root):
                return path
        except OSError:
            pass
    raise ValueError("native raw SWC path escapes declared raw root")


def _manifest_selection(sample_id: str, manifest_path: str | Path,
                        ds00_root: str | Path, expected_path: str | Path | None):
    """Select one declared DS00 path using manifest bytes stable during the read."""
    _validate_sample_id(sample_id)
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest_before = manifest_file.stat()
    manifest_bytes = manifest_file.read_bytes()
    manifest_after = manifest_file.stat()
    if (manifest_before.st_size, manifest_before.st_mtime_ns) != (manifest_after.st_size, manifest_after.st_mtime_ns):
        raise RuntimeError("dataset manifest changed while being read")
    manifest = json.loads(manifest_bytes)
    rows = [r for r in manifest.get("selected_preprocessed_outputs", [])
            if isinstance(r, dict) and str(r.get("sample")) == sample_id]
    if len(rows) != 1:
        raise ValueError(f"Live dataset manifest does not uniquely select a processed DS00 for {sample_id}")
    row = rows[0]
    relative = row.get("relative_path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("manifest selected relative_path must remain inside ds00_root")
    relative = relative.replace("\\", "/")
    root = Path(ds00_root).expanduser().resolve()
    source_path = (root / relative).resolve()
    if not source_path.is_relative_to(root):
        raise ValueError("manifest selected source escapes ds00_root")
    if expected_path is not None:
        expected = Path(expected_path)
        expected = (root / expected) if not expected.is_absolute() else expected
        if expected.resolve() != source_path:
            raise ValueError("configured DS00 path differs from manifest selection")
    return manifest_file, manifest_bytes, manifest, row, relative, source_path


def plan_manifest_selected_ds00(sample_id: str, manifest_path: str | Path,
                                ds00_root: str | Path, *,
                                expected_path: str | Path | None = None,
                                inspect: bool = False) -> dict:
    """Read-only selection; default checks metadata, inspect verifies image checksum."""
    if inspect:
        return resolve_manifest_selected_ds00(sample_id, manifest_path, ds00_root,
                                              expected_path=expected_path)
    manifest_file, manifest_bytes, manifest, row, relative, source_path = _manifest_selection(
        sample_id, manifest_path, ds00_root, expected_path)
    record = _file_record(source_path, frame=row.get("space"), units=row.get("units"))
    if not record["exists"]:
        raise FileNotFoundError(f"Live manifest-selected preprocessed DS volume is unavailable: {source_path}")
    expected_hash = row.get("sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
        raise ValueError("manifest selected DS00 checksum declaration is missing or invalid")
    return {"sample_id": sample_id, "relative_path": relative, "source": record,
            "manifest_path": str(manifest_file),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "manifest_run_id": manifest.get("run_id"), "manifest_time": manifest.get("time"),
            "declared_sha256": expected_hash.lower(), "checksum_verified": False}


def resolve_manifest_selected_ds00(sample_id: str, manifest_path: str | Path,
                                   ds00_root: str | Path, *,
                                   expected_path: str | Path | None = None,
                                   expected_relative_path: str | None = None) -> dict:
    """Verify one manifest-selected processed DS00 source and its stable checksum."""
    if expected_relative_path is not None:
        if expected_path is not None:
            raise ValueError("provide one expected DS00 path")
        expected_path = expected_relative_path
    manifest_file, manifest_bytes, manifest, row, relative, source_path = _manifest_selection(
        sample_id, manifest_path, ds00_root, expected_path)
    record = _file_record(source_path, inspect=True, frame=row.get("space"), units=row.get("units"))
    if not record["exists"]:
        raise FileNotFoundError(source_path)
    expected_hash = row.get("sha256")
    if not isinstance(expected_hash, str) or record["sha256"] != expected_hash.lower():
        raise RuntimeError("Selected preprocessed DS SHA256 differs from the live manifest")
    return {"sample_id": sample_id, "relative_path": relative, "source": record,
            "manifest_path": str(manifest_file),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "manifest_run_id": manifest.get("run_id"), "manifest_time": manifest.get("time"),
            "repository_candidate_path": row.get("repository_candidate_path"),
            "processed_at": row.get("processed_at"),
            "source_historical_path": row.get("source_historical_path"),
            "source_sha256": row.get("source_sha256"),
            "processing_parameters": row.get("processing_parameters"),
            "software_versions": row.get("software_versions"),
            "declared_space": row.get("space"),
            "scientific_status": row.get("status"), "source_acquisition_date": "unknown"}


def processed_ds00_record(sample_id: str, manifest_path: str | Path,
                          ds00_root: str | Path,
                          expected_geometry: dict | None = None) -> dict:
    """Return the historical flat processed-DS00 receipt from one verified source."""
    selected = resolve_manifest_selected_ds00(sample_id, manifest_path, ds00_root)
    source = selected["source"]
    result = {
        "path": source["path"], "server_path": source["path"],
        "repository_candidate_path": selected["repository_candidate_path"],
        "relative_path": selected["relative_path"], "sha256": source["sha256"],
        "bytes": source["size"], "mtime_ns_before_after_equal": True,
        "server_file_present": True, "manifest_path": selected["manifest_path"],
        "manifest_sha256": selected["manifest_sha256"],
        "manifest_run_id": selected["manifest_run_id"], "manifest_time": selected["manifest_time"],
        "processed_at": selected["processed_at"],
        "source_historical_path": selected["source_historical_path"],
        "source_sha256": selected["source_sha256"],
        "processing_parameters": selected["processing_parameters"],
        "software_versions": selected["software_versions"],
        "declared_space": selected["declared_space"],
        "scientific_status": selected["scientific_status"],
        "source_acquisition_date": selected["source_acquisition_date"],
    }
    if expected_geometry is not None:
        result["expected_geometry"] = expected_geometry
    return result
