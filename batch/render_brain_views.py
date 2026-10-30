"""Render explicit one-mesh/one-neuron VisPa snapshots in deterministic order.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
Status: candidate

Operator: python -m batch.render_brain_views --jobs batch/local_pilot_20261025.json
          --output-root work/brain-view-batch-new-run --limit 1 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from vispa.renderers.swc_brain_view import plan_configured_view, render_configured_snapshot


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"{label} must contain only letters, digits, underscore or hyphen")
    return value


def load_jobs(jobs_path: Path, output_root: Path, limit: int | None, all_jobs: bool) -> dict:
    jobs_path = jobs_path.resolve(strict=True)
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "vispa.brain_view_batch.v1":
        raise ValueError("Expected vispa.brain_view_batch.v1 jobs settings")
    config = Path(payload["vispa_config"])
    if not config.is_absolute():
        config = jobs_path.parent / config
    config = config.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root == jobs_path.parent or jobs_path.parent in output_root.parents:
        raise ValueError("Output root must be separate from jobs settings")
    entries = []
    for group in payload.get("jobs", []):
        sample = _safe(group["sample_id"], "sample_id")
        region = _safe(group["region_id"], "region_id")
        mesh = Path(group["mesh_path"])
        if not mesh.is_absolute():
            mesh = jobs_path.parent / mesh
        mesh = mesh.resolve(strict=True)
        label = group.get("mesh_label", region)
        if (not isinstance(label, str) or not label.strip() or len(label) > 18 or
            any(not 32 <= ord(character) <= 126 for character in label)):
            raise ValueError(
                "mesh_label must be 1-18 printable ASCII characters; "
                "set it explicitly when region_id is longer than 18 characters")
        region_selection = group.get("region")
        if (region_selection is not None and
                (not isinstance(region_selection, str) or not region_selection.strip() or
                 len(region_selection) > 160 or any(ord(character) < 32 for character in region_selection))):
            raise ValueError("region must be a non-empty exact filename, display name or acronym")
        if not isinstance(group.get("coordinate_frame"), str) or not group["coordinate_frame"].strip():
            raise ValueError("coordinate_frame must be declared per group")
        if not isinstance(group.get("coordinate_units"), str) or not group["coordinate_units"].strip():
            raise ValueError("coordinate_units must be declared per group")
        names = group.get("neuron_ids")
        if not isinstance(names, list) or not names:
            raise ValueError("Each group needs explicit neuron_ids")
        for neuron in names:
            if not isinstance(neuron, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.swc", neuron):
                raise ValueError("Each neuron_id must be an explicit safe .swc filename")
            entries.append({"sample_id": sample, "region_id": region, "mesh_path": str(mesh),
                            "mesh_label": label.strip(), "neuron_id": neuron,
                            "coordinate_frame": group["coordinate_frame"].strip(),
                            "coordinate_units": group["coordinate_units"].strip(),
                            "region": region_selection.strip() if region_selection is not None else None,
                            "portal_region": group.get("portal_region", ""),
                            "camera_overrides": group.get("camera_overrides", {})})
    entries.sort(key=lambda e: (e["sample_id"], e["region_id"], e["neuron_id"]))
    identities = [(e["sample_id"], e["region_id"], e["neuron_id"]) for e in entries]
    if not entries or len(identities) != len(set(identities)):
        raise ValueError("Jobs must be nonempty with unique sample/region/neuron identities")
    if all_jobs:
        if limit is not None or payload.get("allow_all") is not True:
            raise ValueError("--all requires allow_all=true and cannot use --limit")
    elif limit is None or limit < 1:
        raise ValueError("Use a positive --limit for bounded work, or explicitly opt in to --all")
    if limit is not None:
        entries = entries[:limit]
    for entry in entries:
        output = output_root / entry["sample_id"] / entry["region_id"] / f'{Path(entry["neuron_id"]).stem}.png'
        entry["snapshot_png"] = str(output)
        plan = plan_configured_view(entry["sample_id"], entry["neuron_id"],
                                    entry["portal_region"], config,
                                    overrides=entry["camera_overrides"], snapshot=output,
                                    mesh_path=entry["mesh_path"], mesh_label=entry["mesh_label"],
                                    region=entry["region"])
        if (plan["coordinate_frame"] != entry["coordinate_frame"] or
            plan["coordinate_units"] != entry["coordinate_units"]):
            raise ValueError("Job mesh/SWC frame and units must exactly match configured processed SWC")
        entry["preflight"] = plan
    return {"schema": payload["schema"], "jobs_path": str(jobs_path),
            "jobs_sha256": _sha256(jobs_path), "vispa_config": str(config),
            "vispa_config_sha256": _sha256(config), "output_root": str(output_root),
            "requested": len(entries), "jobs": entries}


def run_batch(plan: dict, *, dry_run: bool) -> dict:
    result = {**plan, "status": "dry_run" if dry_run else "in_progress", "completed": []}
    if dry_run:
        return result
    output_root = Path(plan["output_root"])
    if output_root.exists():
        raise FileExistsError("Fresh output root required; existing outputs will not be clobbered")
    output_root.mkdir(parents=True)
    try:
        for entry in plan["jobs"]:
            snapshot = Path(entry["snapshot_png"])
            receipt = render_configured_snapshot(
                entry["sample_id"], entry["neuron_id"], snapshot,
                entry["portal_region"], plan["vispa_config"],
                mesh_path=entry["mesh_path"], mesh_label=entry["mesh_label"],
                region=entry["region"],
                overrides=entry["camera_overrides"])
            if (receipt.get("status") != "rendered_candidate" or
                receipt.get("output_png_sha256") != _sha256(snapshot) or
                receipt.get("settings") != entry["preflight"]["settings"] or
                receipt.get("mesh", {}).get("sha256") != entry["preflight"]["mesh"]["sha256"] or
                (receipt.get("region_mesh") or {}).get("sha256") !=
                    (entry["preflight"].get("region_mesh") or {}).get("sha256") or
                receipt.get("processed_swc", {}).get("sha256") != entry["preflight"]["processed_swc"]["sha256"]):
                raise RuntimeError(f"Snapshot receipt/hash mismatch: {snapshot}")
            result["completed"].append({"sample_id": entry["sample_id"],
                                        "region_id": entry["region_id"],
                                        "neuron_id": entry["neuron_id"],
                                        "snapshot_png": str(snapshot),
                                        "snapshot_sha256": _sha256(snapshot),
                                        "snapshot_receipt": str(snapshot.with_suffix(".json")),
                                        "status": "rendered_candidate"})
        result["status"] = "pass"
    except Exception as exc:
        result["status"] = "partial_or_failed"
        result["error"] = str(exc)
    finally:
        (output_root / "batch_receipt.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--limit", type=int)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = load_jobs(args.jobs, args.output_root, args.limit, args.all)
        result = run_batch(plan, dry_run=args.dry_run)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"dry_run", "pass"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
