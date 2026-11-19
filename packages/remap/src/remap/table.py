"""Export validated ReMAP neuron JSON as a legacy PA analysis source.

Version: 0.1.0.dev4 (local/unreleased)
Last updated: 2026-10-25
Change history:
- 2026-10-25: Export one-neuron JSON records for legacy PA registration.
- 2026-11-09: Registration path uses registration_path.legacy_registration_path so a cross-drive pair keeps the finished output path.
Status: candidate
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import re
import tempfile

from .registration_path import legacy_registration_path


COLUMNS = ("SampleID", "NeuronID", "NeuronUID", "Soma_Region",
           "Terminal_Count_Distinct_Regions", "Graph_Leaves_All_Types",
           "Total_Length_Atlas_Voxels", "Region_Projection_Length_Atlas_Voxels_JSON",
           "Declared_Space", "Atlas_Level", "Coordinate_Scale",
           "Coordinate_Offset_JSON", "QC_Status", "Result_Record_SHA256",
           "SWC_SHA256", "Atlas_SHA256", "Atlas_Key_SHA256")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(value, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty normalized string")
    if re.fullmatch(r"\d+\.0+", value):
        raise ValueError(f"{name} uses Excel decimal form; supply normalized identity")
    return value


def _finite_number(value, name: str, *, positive=False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    if (positive and value <= 0) or (not positive and value < 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return float(value)


def _validated_record(result: dict, provenance: dict) -> tuple[dict, dict]:
    source_ref = provenance["path"]
    if not isinstance(result, dict) or result.get("schema") != "remap.one_neuron.v1":
        raise ValueError(f"{source_ref}: unsupported one-neuron schema")
    sample = _identity(result.get("sample_id"), "SampleID")
    neuron = _identity(result.get("neuron_id"), "NeuronID")
    if Path(neuron).name != neuron or result.get("uid") != f"{sample}::{neuron}":
        raise ValueError(f"{source_ref}: NeuronUID conflicts with exact composite identity")
    source_hashes = result.get("source_sha256")
    if not isinstance(source_hashes, dict) or any(
        not isinstance(source_hashes.get(name), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source_hashes[name])
        for name in ("swc", "atlas", "atlas_key")
    ):
        raise ValueError(f"{source_ref}: source hashes missing or malformed")
    source_paths = result.get("paths")
    if not isinstance(source_paths, dict) or any(
        not isinstance(source_paths.get(name), str) or not source_paths[name]
        for name in ("swc", "atlas", "atlas_key")
    ):
        raise ValueError(f"{source_ref}: source paths missing or malformed")
    mapping = result.get("coordinate_mapping")
    if not isinstance(mapping, dict):
        raise ValueError(f"{source_ref}: coordinate mapping missing")
    scale = _finite_number(mapping.get("source_xyz_divided_by"), "Coordinate_Scale", positive=True)
    offset = mapping.get("then_voxel_offset")
    if not isinstance(offset, list) or len(offset) != 3 or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in offset
    ):
        raise ValueError(f"{source_ref}: coordinate offset requires three finite numbers")
    space = _identity(result.get("declared_space"), "Declared_Space")
    level = result.get("atlas_level")
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 6:
        raise ValueError(f"{source_ref}: atlas level must be 1..6")
    soma = _identity(result.get("soma_region"), "Soma_Region")
    qc = _identity(result.get("qc_status"), "QC_Status")
    count = result.get("terminal_count_distinct_regions")
    leaves = result.get("graph_leaves_all_types")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (count, leaves)):
        raise ValueError(f"{source_ref}: terminal counts must be nonnegative integers")
    nodes = result.get("nodes")
    regions = result.get("terminal_regions")
    sites = result.get("terminal_sites")
    if (isinstance(nodes, bool) or not isinstance(nodes, int) or nodes < 1 or nodes < leaves
            or not isinstance(regions, list) or len(regions) != count
            or any(not isinstance(region, str) or not region for region in regions)
            or len(set(regions)) != len(regions)
            or not isinstance(sites, list) or len(sites) != leaves
            or any(not isinstance(site, dict) or site.get("region") not in regions
                   or not isinstance(site.get("voxel"), list) or len(site["voxel"]) != 3
                   or any(isinstance(v, bool) or not isinstance(v, int) for v in site["voxel"])
                   for site in sites)):
        raise ValueError(f"{source_ref}: graph/terminal fields conflict with declared counts")
    total = _finite_number(result.get("total_length_atlas_voxels"), "Total_Length_Atlas_Voxels")
    lengths = result.get("region_projection_length_atlas_voxels")
    if not isinstance(lengths, dict) or any(
        not isinstance(k, str) or not k or _finite_number(v, f"regional length {k}") < 0
        for k, v in lengths.items()
    ):
        raise ValueError(f"{source_ref}: regional length dictionary invalid")
    row = dict(zip(COLUMNS, (sample, neuron, f"{sample}::{neuron}", soma, count, leaves,
                             total, json.dumps(lengths, sort_keys=True, allow_nan=False),
                             space, level, scale, json.dumps(offset, allow_nan=False),
                             qc, provenance["sha256"], source_hashes["swc"], source_hashes["atlas"],
                             source_hashes["atlas_key"])))
    return row, {"path": source_ref, "sha256": provenance["sha256"],
                 "source_sha256": source_hashes}


def plan_table(inputs: list[Path], output: Path, source_date: str | None,
               registry_path: Path | None = None,
               source_id: str = "remap_neurons") -> tuple[list[dict], dict]:
    if not inputs:
        raise ValueError("At least one explicit --input is required")
    records, provenance = [], []
    for raw in inputs:
        path = Path(raw).resolve(strict=True)
        data = path.read_bytes()
        records.append(json.loads(data.decode("utf-8-sig")))
        provenance.append({"path": str(path), "sha256": _hash(data)})
    return plan_records(records, output, source_date, registry_path, provenance, source_id)


def plan_records(records: list[dict], output: Path, source_date: str | None = None,
                 registry_path: Path | None = None,
                 provenance_inputs: list[dict] | None = None,
                 source_id: str = "remap_neurons") -> tuple[list[dict], dict]:
    """Prepare one table from in-memory analyze_one records, without JSON files."""
    if not records:
        raise ValueError("At least one one-neuron record is required")
    if provenance_inputs is not None and len(provenance_inputs) != len(records):
        raise ValueError("Provenance list must match record count")
    if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", source_id):
        raise ValueError("source_id must use letters, digits and underscores and start with a letter")
    if source_date is not None:
        if not re.fullmatch(r"\d{8}", source_date):
            raise ValueError("source_date must be YYYYMMDD or omitted")
        try:
            datetime.strptime(source_date, "%Y%m%d")
        except ValueError as exc:
            raise ValueError("source_date must be a valid calendar date YYYYMMDD") from exc
    output = Path(output).resolve()
    if output.suffix.lower() != ".csv":
        raise ValueError("Neuron table output must be .csv")
    receipt_path = output.with_suffix(".receipt.json")
    if output.exists() or receipt_path.exists():
        raise FileExistsError("Neuron table or adjacent receipt already exists")
    rows, lineage = [], []
    identities = set()
    semantics = None
    for index, record in enumerate(records):
        provenance = (provenance_inputs[index] if provenance_inputs is not None else
                      {"path": f"in-memory:{index}",
                       "sha256": _hash(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                                    allow_nan=False).encode("utf-8"))})
        if not isinstance(provenance, dict) or not isinstance(provenance.get("path"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", str(provenance.get("sha256"))):
            raise ValueError("Each provenance input requires path and SHA256")
        row, source = _validated_record(record, provenance)
        key = (row["SampleID"], row["NeuronID"])
        if key in identities:
            raise ValueError(f"Duplicate composite identity: {key}")
        identities.add(key)
        this_semantics = (row["Declared_Space"], row["Atlas_Level"],
                          row["Coordinate_Scale"], row["Coordinate_Offset_JSON"])
        if semantics is None:
            semantics = this_semantics
        elif semantics != this_semantics:
            raise ValueError("Inputs have incompatible space/level/coordinate mapping")
        rows.append(row)
        lineage.append(source)
    anchor = Path(registry_path).resolve() if registry_path else None
    source_entry = {"id": source_id, "role": "analysis", "producer": "remap",
                    "path": legacy_registration_path(output, anchor.parent).replace("\\", "/") if anchor else output.name,
                    "source_date": source_date, "format": "csv", "sample_column": "SampleID",
                    "neuron_column": "NeuronID", "columns": list(COLUMNS[3:])}
    receipt = {"schema": "remap.neuron_table.v1", "version": "0.1.0.dev3",
               "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "export_updated_date": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d"),
               "source_date": source_date, "source_date_is_acquisition_date": False,
               "output": str(output), "receipt": str(receipt_path), "rows": len(rows),
               "identities": [{"SampleID": r["SampleID"], "NeuronID": r["NeuronID"]} for r in rows],
               "metric_units": "atlas voxels; source physical units and registration unverified",
               "mapping": {"declared_space": semantics[0], "atlas_level": semantics[1],
                           "source_xyz_divided_by": semantics[2],
                           "then_voxel_offset": json.loads(semantics[3])},
               "inputs": lineage, "registry_anchor": str(anchor) if anchor else None,
               "registration": source_entry,
               "registration_status": "snippet only; legacy PA registry not modified"}
    return rows, receipt


def write_table(rows: list[dict], receipt: dict) -> dict:
    output, receipt_path = Path(receipt["output"]), Path(receipt["receipt"])
    if output.exists() or receipt_path.exists():
        raise FileExistsError("Neuron table or receipt exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_files = []
    published = []
    try:
        for destination in (output, receipt_path):
            fd, name = tempfile.mkstemp(prefix=".remap-", suffix=destination.suffix, dir=output.parent)
            temp_files.append(Path(name))
            os.close(fd)
        with temp_files[0].open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        receipt["table_sha256"] = _hash(temp_files[0].read_bytes())
        temp_files[1].write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        for source, destination in zip(temp_files, (output, receipt_path)):
            if os.name == "nt":
                os.rename(source, destination)
            else:
                os.link(source, destination)
            published.append(destination)
    except Exception:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temp_files:
            path.unlink(missing_ok=True)
    return receipt
