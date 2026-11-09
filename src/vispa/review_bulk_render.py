"""Render one VisPa review set per published region/FNT job.

Version: 1.21.6 (local/unreleased)
Last updated: 2026-11-09
Change history: ../CHANGELOG.md
Status: candidate

Jobs come from ``vispa_bulk_jobs.json`` written by ``batch.remap_stepwise``.
Each rendered neuron uses the same Soma, Context, Sagittal and TrioPlot calls
as the VisPa GUI. The command does not discover cohorts or rewrite SWCs.

Operator:
  python -m vispa.review_bulk_render --jobs PATH --output-root PATH --limit 1 --dry-run
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


_NEURON = re.compile(r"[A-Za-z0-9_-]+\.swc\Z", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\Z")
_RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


def validate_run_name(name: str) -> str:
    """Accept one portable path component; never normalize an unsafe name."""
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if (not isinstance(name, str) or not _RUN_NAME.fullmatch(name)
            or name.upper() in reserved):
        raise ValueError("run_name must be one path-safe name (1-80 letters, digits, hyphens or underscores)")
    return name


def run_folder_name(payload: dict, jobs_sha256: str) -> str:
    """Keep historical hash-named jobs in their original locations."""
    name = payload.get("run_name")
    return validate_run_name(name) if name is not None else f"bulk_{jobs_sha256[:12]}"


def neuron_folder_name(sample_id: str, neuron_id: str, region: str | None,
                       *, side: str | None = None) -> str:
    """Freeze one short, portable neuron/region folder for new jobs."""
    if not isinstance(sample_id, str) or not _TOKEN.fullmatch(sample_id):
        raise ValueError("sample_id must be a short path-safe name")
    if not isinstance(neuron_id, str) or not _NEURON.fullmatch(neuron_id):
        raise ValueError("neuron_id must be a simple SWC filename")
    label = region.strip() if isinstance(region, str) and region.strip() else "Unassigned"
    # Atlas labels commonly append a numeric atlas ID; keep intrinsic digits.
    label = re.sub(r"_[0-9]+\Z", "", label)
    label = label or "Unassigned"
    if side not in (None, "Left", "Right"):
        raise ValueError("side must be verified Left, Right, or unknown")
    side_token = {"Left": "L", "Right": "R", None: None}[side]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", neuron_id[:-4]).strip("_")[:20] or "neuron"
    readable_label = label.replace("/", "-").replace("\\", "-")
    readable_label = re.sub(r"[^A-Za-z0-9_-]+", "-", readable_label)
    readable_label = re.sub(r"-+", "-", readable_label).strip("-_") or "region"
    readable = "_".join(
        part for part in (neuron_id[:-4], side_token, readable_label) if part)
    if _RUN_NAME.fullmatch(readable) and readable_label == label:
        return readable
    if _RUN_NAME.fullmatch(readable) and len(readable_label) <= 48:
        return readable
    original = "_".join(part for part in (neuron_id[:-4], side_token, label) if part)
    suffix = hashlib.sha256(original.encode("utf-8")).hexdigest()[:8]
    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_")[:24] or "region"
    return "_".join(part for part in (stem, side_token, safe_label, suffix) if part)


def _complete_existing_outputs(plan: dict) -> dict[str, str]:
    """Map neuron IDs to existing folders that contain every required product."""
    sample_root = Path(plan["output_root"]) / plan["sample_id"] / "neurons"
    if not sample_root.is_dir():
        return {}
    by_stem = {}
    for folder in sample_root.iterdir():
        if folder.is_dir():
            by_stem.setdefault(folder.name.split("_", 1)[0], []).append(folder)
    patterns = ("*_TriPlot.png", "*_Soma_Plot.png", "*_Context_Plot.png",
                "*_Sagittal_Plot.png", "*_Soma.nii.gz")
    complete = {}
    for job in plan["jobs"]:
        stem = job["neuron_id"][:-4]
        for folder in by_stem.get(stem, []):
            if all(any(path.is_file() and path.stat().st_size > 0
                       for path in folder.rglob(pattern))
                   for pattern in patterns):
                for sidecar in folder.glob("*_Soma.nii.gz.json"):
                    try:
                        repair_nifti_sidecar(sidecar)
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
                complete[job["neuron_id"]] = str(folder)
                break
    return complete


def skip_complete_existing_outputs(plan: dict) -> dict:
    """Keep only jobs whose complete output set is absent."""
    complete = _complete_existing_outputs(plan)
    receipt_path = (Path(plan["output_root"]) / plan["sample_id"] / "process_log.json")
    receipt = (json.loads(receipt_path.read_text(encoding="utf-8"))
               if receipt_path.is_file() else {})
    source_blocked = {}
    for job in plan["jobs"]:
        if job["neuron_id"] in complete:
            continue
        record = (((receipt.get("neurons") or {}).get(job["neuron_id"]) or {})
                  .get("current") or {})
        errors = " ".join(str(item) for item in record.get("errors") or [])
        outputs = set((record.get("outputs") or {}).keys())
        if ("Soma's central high-resolution cube" in errors
                and {"Context", "Sagittal"}.issubset(outputs)):
            source_blocked[job["neuron_id"]] = {
                "neuron_id": job["neuron_id"],
                "path": str(Path(plan["output_root"]) / plan["sample_id"] / "neurons"
                            / record.get("neuron_folder", "")),
                "error": next((item for item in record.get("errors") or []
                               if "Soma's central high-resolution cube" in item), errors),
            }
    remaining = [job for job in plan["jobs"]
                 if job["neuron_id"] not in complete
                 and job["neuron_id"] not in source_blocked]
    return {
        **plan,
        "jobs": remaining,
        "requested": len(remaining),
        "total_requested": len(plan["jobs"]),
        "skipped_existing": [
            {"neuron_id": neuron_id, "path": complete[neuron_id]}
            for neuron_id in sorted(complete)
        ],
        "skipped_source_blocked": [
            source_blocked[neuron_id] for neuron_id in sorted(source_blocked)
        ],
    }


def _replace_path_strings(value, replacements: dict[str, str]):
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [_replace_path_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_path_strings(item, replacements)
                for key, item in value.items()}
    return value


def build_folder_migrations(output_root: Path, sample: str,
                            jobs_path: Path) -> list[dict]:
    """Plan readable renames for legacy hash-suffixed neuron folders."""
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    neurons_root = output_root / sample / "neurons"
    if not neurons_root.is_dir():
        return []
    jobs_by_id = {job["neuron_id"]: job for job in payload.get("jobs", [])}
    receipt_path = output_root / sample / "process_log.json"
    receipt = (json.loads(receipt_path.read_text(encoding="utf-8"))
               if receipt_path.is_file() else {})
    migrations = []
    seen_old_names = set()

    def add_migration(neuron_id, old_name):
        if old_name in seen_old_names or neuron_id not in jobs_by_id:
            return
        job = jobs_by_id[neuron_id]
        side = (job.get("vispa_region") or {}).get("side")
        new_name = neuron_folder_name(
            sample, neuron_id, job.get("soma_region"), side=side)
        old_path = neurons_root / old_name
        new_path = neurons_root / new_name
        if old_name == new_name or not old_path.is_dir():
            return
        seen_old_names.add(old_name)
        migrations.append({
            "sample": sample, "neuron_id": neuron_id,
            "old_name": old_name, "new_name": new_name,
            "old_path": str(old_path), "new_path": str(new_path),
            "destination_exists": new_path.exists(),
        })

    for job in payload.get("jobs", []):
        old_name = job.get("neuron_folder")
        if isinstance(old_name, str) and re.search(r"_[0-9a-f]{8}$", old_name):
            add_migration(job["neuron_id"], old_name)
    for neuron_id, slot in (receipt.get("neurons") or {}).items():
        old_name = ((slot or {}).get("current") or {}).get("neuron_folder")
        if isinstance(old_name, str) and re.search(r"_[0-9a-f]{8}$", old_name):
            add_migration(neuron_id, old_name)
    return migrations


def apply_folder_migrations(output_root: Path, sample: str,
                            migrations: list[dict]) -> dict:
    """Apply planned renames and rewrite animal receipt path strings."""
    applicable = [item for item in migrations if not item["destination_exists"]]
    conflicts = [item for item in migrations if item["destination_exists"]]
    for item in applicable:
        old_path = Path(item["old_path"])
        new_path = Path(item["new_path"])
        if not old_path.is_dir() or new_path.exists():
            raise FileExistsError(f"Rename target changed during migration: {new_path}")
        old_path.rename(new_path)
    receipt_path = output_root / sample / "process_log.json"
    if applicable and receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt = _replace_path_strings(
            receipt, {item["old_name"]: item["new_name"] for item in applicable})
        receipt["folder_name_migrations"] = [
            *receipt.get("folder_name_migrations", []),
            {
                "applied_at_utc": datetime.now(timezone.utc).isoformat(),
                "policy": "readable punctuation; no hash for unsafe-character substitution",
                "mappings": applicable,
            },
        ]
        _atomic_json(receipt_path, receipt)
    return {"sample": sample, "renamed": len(applicable),
            "conflicts": conflicts, "mappings": applicable}


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


def repair_nifti_sidecar(sidecar_path: Path, image_path: Path | None = None) -> bool:
    """Point one moved NIfTI sidecar at its final image and preserve the stage path."""
    sidecar_path = Path(sidecar_path)
    if not sidecar_path.name.endswith(".nii.gz.json"):
        raise ValueError("Expected a NIfTI sidecar ending in .nii.gz.json")
    image_path = Path(image_path) if image_path else sidecar_path.with_name(
        sidecar_path.name[:-5])
    if not image_path.is_file() or image_path.stat().st_size <= 0:
        raise FileNotFoundError(f"Final NIfTI image is unavailable: {image_path}")
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    final_path = str(image_path.resolve())
    old_path = payload.get("output_file")
    if old_path == final_path:
        return False
    if old_path and old_path != final_path:
        payload.setdefault("staged_output_file", old_path)
    payload["output_file"] = final_path
    payload["output_path_status"] = "final path verified after staged-file move"
    payload["metadata_repaired_at_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(sidecar_path, payload)
    return True


def _finite_xyz(value, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} must contain three coordinates")
    coords = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError(f"{label} must be numeric")
        number = float(item)
        if number != number or abs(number) == float("inf"):
            raise ValueError(f"{label} must be finite")
        coords.append(number)
    return coords


def load_review_jobs(jobs_path: Path, output_root: Path, limit: int | None, all_jobs: bool) -> dict:
    jobs_path = Path(jobs_path).resolve(strict=True)
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "vispa.review_bulk.v1":
        raise ValueError("Expected vispa.review_bulk.v1 jobs")
    sample = payload.get("sample_id")
    if not isinstance(sample, str) or not _TOKEN.fullmatch(sample):
        raise ValueError("sample_id must be a short token")
    config = payload.get("vispa_config")
    if not isinstance(config, str) or not config.strip():
        raise ValueError("vispa_config must name the VisPa profile used for review rendering")
    config_path = Path(config)
    if not config_path.is_absolute():
        config_path = jobs_path.parent / config_path
    config_path = config_path.resolve(strict=True)
    if not config_path.is_file():
        raise ValueError("vispa_config must be a file")
    layout = payload.get("output_layout", "legacy")
    if layout not in {"legacy", "sample_neurons", "sample_neurons_flat"}:
        raise ValueError("output_layout must be legacy, sample_neurons or sample_neurons_flat")
    config_hash = _sha256(config_path)
    if payload.get("vispa_config_sha256") and payload["vispa_config_sha256"] != config_hash:
        raise ValueError("Prepared VisPa config hash differs from current config")
    output_root = Path(output_root).expanduser().resolve()
    if output_root == jobs_path.parent or jobs_path.parent in output_root.parents:
        raise ValueError("Output root must be separate from the jobs file")
    ready, skipped = [], []
    region_filter = payload.get("region_filter")
    if region_filter is not None:
        if (not isinstance(region_filter, dict) or
                region_filter.get("field") != "portal_region" or
                not isinstance(region_filter.get("labels"), list) or
                any(not isinstance(label, str) or not label for label in region_filter["labels"])):
            raise ValueError("region_filter must contain exact portal_region labels")
        selected_regions = set(region_filter["labels"])
    else:
        selected_regions = set()
    seen = set()
    for entry in payload.get("jobs", []):
        if not isinstance(entry, dict):
            raise ValueError("Each review job must be an object")
        neuron = entry.get("neuron_id")
        if not isinstance(neuron, str) or not _NEURON.fullmatch(neuron):
            raise ValueError("Each neuron_id must be an explicit .swc filename")
        if entry.get("sample_id") != sample:
            raise ValueError("Every job must use the file sample_id")
        if selected_regions:
            entries = entry.get("soma_region_entries")
            if not isinstance(entries, dict) or entries.get("portal_region") not in selected_regions:
                raise ValueError(f"{neuron} differs from frozen region_filter")
        identity = (sample.casefold(), neuron.casefold())
        if identity in seen:
            raise ValueError("Review jobs must have unique neurons including case-insensitive names")
        seen.add(identity)
        if entry.get("render_ready") is True:
            ready_job = {
                "sample_id": sample,
                "neuron_id": neuron,
                "soma_region": entry.get("soma_region"),
                "soma_xyz": _finite_xyz(entry.get("soma_xyz"), f"{neuron} soma_xyz"),
                "soma_units": entry.get("soma_units"),
                "soma_coordinate_source": entry.get("soma_coordinate_source"),
                "raw_swc_sha256": entry.get("raw_swc_sha256"),
                "raw_swc_path": entry.get("raw_swc_path"),
                "raw_source_path": entry.get("raw_source_path"),
                "fnt_marker": entry.get("fnt_marker"),
                "fnt_cluster": entry.get("fnt_cluster"),
            }
            if "soma_region_source" in entry:
                ready_job["soma_region_source"] = entry["soma_region_source"]
            if "soma_region_entries" in entry:
                ready_job["soma_region_entries"] = entry["soma_region_entries"]
            if "neuron_folder" in entry:
                ready_job["neuron_folder"] = entry["neuron_folder"]
            if "vispa_region" in entry:
                ready_job["vispa_region"] = entry["vispa_region"]
            if "context_source_status" in entry:
                ready_job["context_source_status"] = entry["context_source_status"]
            for key in ("source_acquisition_date", "source_acquisition_date_status",
                        "source_observed_at_utc", "raw_source_file_mtime_utc",
                        "raw_source_file_mtime_role", "raw_source_receipt"):
                if key in entry:
                    ready_job[key] = entry[key]
            ready.append(ready_job)
        else:
            skipped.append({"sample_id": sample, "neuron_id": neuron,
                            "soma_error": entry.get("soma_error")})
    ready.sort(key=lambda item: item["neuron_id"])
    skipped.sort(key=lambda item: item["neuron_id"])
    allow_all = payload.get("allow_all")
    if all_jobs:
        if limit is not None or allow_all is not True:
            raise ValueError("--all requires allow_all=true in the jobs file and cannot use --limit")
        selected = ready
    elif limit is None or isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Use a positive --limit for bounded work, or explicitly opt in to --all")
    else:
        selected = ready[:limit]
    if not selected:
        raise ValueError("No render-ready neurons are available for this limit")
    jobs_hash = _sha256(jobs_path)
    run_name = run_folder_name(payload, jobs_hash)
    for entry in selected:
        if layout in {"sample_neurons", "sample_neurons_flat"}:
            neuron_folder = entry.get("neuron_folder", entry["neuron_id"][:-4])
            if not isinstance(neuron_folder, str) or not _RUN_NAME.fullmatch(neuron_folder):
                raise ValueError("neuron_folder must be one short path-safe name")
            folder = output_root / sample / "neurons" / neuron_folder
            if layout == "sample_neurons":
                folder = folder / run_name
        else:
            folder = output_root / sample / entry["neuron_id"][:-4]
        entry["output_dir"] = str(folder)
    from vispa import __version__
    review_settings, figure_output_root = {}, None
    if layout in {"sample_neurons", "sample_neurons_flat"}:
        from vispa.config import load, resolve_settings
        resolved_config = load(config_path)
        review_settings = resolve_settings("review", config=resolved_config)
        figure_output_root = str(resolved_config["visual_toolkit"]["figure_output_root"])
        if (layout == "sample_neurons_flat" and
                resolved_config["visual_toolkit"].get("enforce_render_config") and
                output_root != Path(figure_output_root).expanduser().resolve()):
            raise ValueError("Flat review output root must match the saved figure_output_root")
    return {
        "schema": payload["schema"],
        "jobs_path": str(jobs_path),
        "jobs_sha256": jobs_hash,
        "run_name": run_name,
        "vispa_config": str(config_path),
        "vispa_config_sha256": config_hash,
        "output_root": str(output_root),
        "sample_id": sample,
        "requested": len(selected),
        "all_jobs": all_jobs,
        "output_layout": layout,
        "vispa_version": __version__,
        "review_settings": review_settings,
        "figure_output_root": figure_output_root,
        "vispa_region_lookup": payload.get("vispa_region_lookup"),
        "region_filter": region_filter,
        "skipped_not_ready": skipped,
        "jobs": selected,
        "anatomical_acceptance": "not established",
    }


def _verified_raw_path(config: dict, job: dict) -> Path | None:
    expected = job.get("raw_swc_sha256")
    if expected is None:
        return None
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Invalid expected raw SWC hash")
    from vispa.data_input_adaptor import resolve_declared_raw_swc
    explicit = job.get("raw_swc_path")
    if explicit:
        path = Path(explicit).resolve(strict=True)
        if path.name != job["neuron_id"]:
            raise ValueError("Explicit raw SWC path has a different neuron filename")
        candidates = [path]
    else:
        roots = []
        managed = (config.get("defaults") or {}).get("cache_root")
        if managed:
            roots.append(Path(managed) / "swc_raw")
        declared = (config.get("sources") or {}).get("legacy_raw_swc_root")
        if declared:
            roots.append(Path(declared))
        candidates = []
        for root in roots:
            try:
                candidates.append(resolve_declared_raw_swc(
                    root, job["sample_id"], job["neuron_id"]))
            except (OSError, ValueError):
                continue
    for path in candidates:
        if path.is_file() and _sha256(path).lower() == expected.lower():
            return path
    raise ValueError("Configured raw SWC differs from job's frozen source hash or is missing")


def _region_display_value(job: dict) -> str | None:
    """Compatibility wrapper around the shared pure GUI/bulk formatter."""
    from vispa.data_input_adaptor import region_display_label
    source = job.get("soma_region_source")
    field = source.get("field") if isinstance(source, dict) else None
    entries = job.get("soma_region_entries") or {}
    portal = entries.get("portal_region") if isinstance(entries, dict) else None
    return region_display_label(portal, job.get("vispa_region"),
                                selected_region=job.get("soma_region"),
                                selected_source=field)


def render_review_neuron(job: dict, output_dir: Path, config_path: Path) -> dict:
    """Render one neuron with the GUI's toolkit calls."""
    import matplotlib
    matplotlib.use("Agg", force=False)
    from vispa.config import load, context_unavailable_authorized
    from vispa.reviewer import make_processing_request
    from vispa.data_input_adaptor import load_raw_neuron, read_swc
    from vispa.toolkit import BLOCK_SIZE_PIXELS, REVIEW_SETTINGS, VisPa, configure_data_sources

    config = load(config_path)
    raw_path = _verified_raw_path(config, job)
    configure_data_sources(config=config)
    context = REVIEW_SETTINGS["context"]
    output_dir.mkdir(parents=True, exist_ok=True)
    request = make_processing_request(
        job["sample_id"], job["neuron_id"], job["soma_xyz"], 1,
        context["width_um"], context["height_um"], context["depth_um"],
        str(output_dir), save_outputs=True, save_soma_nifti=True,
        make_review_figure=True)
    side = int(round(float(request.soma_cubes) * BLOCK_SIZE_PIXELS[0]))
    region = _region_display_value(job)
    tool = VisPa(job["sample_id"])
    panels, errors = {}, []
    context_availability = {"status": "source_expected"}
    try:
        volume = origin = resolution = None
        try:
            volume, origin, resolution = tool.get_high_res_soma_window(
                request.soma_xyz, window_px=(side, side))
        except Exception as exc:
            errors.append(f"Soma: {exc}")
        if volume is not None:
            try:
                tool.export_data(volume, origin, resolution, job["neuron_id"],
                                 suffix="SomaBlock", soma_region=region,
                                 soma_coords=request.soma_xyz, output_dir=str(output_dir))
            except Exception as exc:
                errors.append(f"Soma NIfTI: {exc}")
            try:
                panels["Soma"] = tool.plot_soma_block(
                    volume, origin, resolution, request.soma_xyz, job["neuron_id"],
                    soma_region=region, output_dir=str(output_dir))
            except Exception as exc:
                errors.append(f"Soma plot: {exc}")
        try:
            tree = (read_swc(raw_path) if raw_path is not None else
                    load_raw_neuron(config, job["sample_id"], job["neuron_id"], allow_download=False))
            if tree is None:
                raise ValueError("raw SWC was not found")
            if context_unavailable_authorized(config, job["sample_id"]):
                if job.get("context_source_status") != "missing_declared_5um_source":
                    raise ValueError("Frozen Context availability differs from saved config")
                panels["Context"] = tool.plot_unavailable_context(
                    job["neuron_id"], soma_region=region, soma_coords=request.soma_xyz,
                    output_dir=str(output_dir), reason="5 µm source missing")
                context_availability = {"status": "intentionally_unavailable",
                                        "source_status": "missing_declared_5um_source",
                                        "reason": "No declared 5 µm Context source for this sample"}
            else:
                wide, wide_origin, wide_resolution = tool.get_low_res_widefield(
                    request.soma_xyz, width_um=request.width_um,
                    height_um=request.height_um, depth_um=request.depth_um)
                panels["Context"] = tool.plot_widefield_context(
                    wide, wide_origin, wide_resolution, request.soma_xyz, job["neuron_id"],
                    swc_tree=tree, soma_region=region, output_dir=str(output_dir))
                context_availability = {"status": "source_rendered"}
        except Exception as exc:
            errors.append(f"Context: {exc}")
        try:
            sagittal_raw_path = raw_path
            if sagittal_raw_path is None:
                from vispa.data_input_adaptor import resolve_declared_raw_swc
                declared_root = (config.get("sources") or {}).get("legacy_raw_swc_root")
                if declared_root:
                    sagittal_raw_path = resolve_declared_raw_swc(
                        declared_root, job["sample_id"], job["neuron_id"])
            panels["Sagittal"] = tool.render_sagittal_context_from_ds(
                job["neuron_id"], request.soma_xyz, output_dir=str(output_dir),
                soma_region=region, swc_path=sagittal_raw_path)["panel"]
        except Exception as exc:
            errors.append(f"Sagittal: {exc}")
        if all(isinstance(panels.get(role), dict) for role in ("Soma", "Context", "Sagittal")):
            try:
                panels["TrioPlot"] = tool.plot_tri_plot(
                    [panels["Soma"], panels["Context"], panels["Sagittal"]],
                    job["neuron_id"], output_dir=str(output_dir), soma_region=region,
                    soma_coords=list(request.soma_xyz), legend=False)
            except Exception as exc:
                errors.append(f"TrioPlot: {exc}")
        elif "TrioPlot" not in errors:
            missing = [role for role in ("Soma", "Context", "Sagittal") if role not in panels]
            errors.append("TrioPlot: requires Soma, Context and Sagittal; missing " + ", ".join(missing))
    finally:
        tool.close()
    outputs = {}
    for role, panel in panels.items():
        if isinstance(panel, dict):
            outputs[role] = panel.get("output_png")
        elif isinstance(panel, str):
            outputs[role] = panel
    if raw_path is not None and _sha256(raw_path).lower() != job["raw_swc_sha256"].lower():
        raise ValueError("Configured raw SWC changed during rendering")
    return {"outputs": outputs, "errors": errors,
            "role_availability": {"Context": context_availability},
            "raw_swc_source_equivalence": "verified by hash" if raw_path is not None else "unknown"}


def _status_for(outputs: dict, errors: list) -> str:
    required = {"Soma", "Context", "Sagittal", "TrioPlot"}
    if not outputs:
        return "failed"
    if errors or not required.issubset(outputs):
        return "partial"
    return "rendered_candidate"


def _settings_sha256(plan: dict) -> str:
    encoded = json.dumps(plan["review_settings"], sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _job_sha256(job: dict) -> str:
    encoded = json.dumps(job, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _current_receipt(job: dict, plan: dict) -> dict | None:
    """Reuse only a complete receipt whose frozen inputs and PNG bytes still match."""
    if not job.get("raw_swc_sha256"):
        return None
    from vispa.config import load
    try:
        _verified_raw_path(load(plan["vispa_config"]), job)
        folder = Path(job["output_dir"]).resolve()
        record = json.loads((folder / "review_receipt.json").read_text(encoding="utf-8"))
        if (record.get("status") != "rendered_candidate" or record.get("errors") or
            record.get("job_sha256") != _job_sha256(job) or
            record.get("config_sha256") != plan["vispa_config_sha256"] or
            record.get("vispa_version") != plan["vispa_version"] or
            record.get("settings_sha256") != _settings_sha256(plan) or
            set(record.get("outputs") or {}) != {"Soma", "Context", "Sagittal", "TrioPlot"}):
            return None
        from PIL import Image
        seen_paths = set()
        for output in record["outputs"].values():
            path = Path(output["path"]).resolve(strict=True)
            if (not path.is_relative_to(folder) or not path.stat().st_size or
                _sha256(path) != output["sha256"]):
                return None
            if path in seen_paths:
                return None
            seen_paths.add(path)
            with Image.open(path) as image:
                if image.format != "PNG":
                    return None
                image.verify()
            with Image.open(path) as image:
                image.load()
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def run_review_bulk(plan: dict, *, dry_run: bool, renderer=None, resume: bool = False,
                    skip_existing: bool = False) -> dict:
    if skip_existing:
        plan = skip_complete_existing_outputs(plan)
        if not plan["jobs"]:
            blocked = bool(plan.get("skipped_source_blocked"))
            status = "partial_or_failed" if blocked else (
                "dry_run" if dry_run else "pass")
            return {**plan, "status": status,
                    "completed": [], "error": None}
    if dry_run:
        return _run_review_bulk(plan, dry_run=True, renderer=renderer, resume=resume)
    from vispa.batch_run_lock import exclusive_batch
    root = Path(plan["output_root"])
    lock = root.parent / f".{root.name}.review_bulk.lock"
    with exclusive_batch(lock):
        return _run_review_bulk(plan, dry_run=False, renderer=renderer, resume=resume)


def _run_review_bulk_flat(plan: dict, *, dry_run: bool, renderer=None,
                          resume: bool = False) -> dict:
    """Render into direct neuron folders and keep one animal process log."""
    from uuid import uuid4
    from vispa.config import load
    from vispa.render_records import (animal_receipt_path, record_neuron_output,
                                      separate_plot_output_dir, update_animal_batch,
                                      verified_neuron_record)

    result = {**plan, "status": "dry_run" if dry_run else "in_progress",
              "completed": [], "error": None}
    if dry_run:
        return result
    sample = plan["sample_id"]
    sample_root = Path(plan["output_root"]) / sample
    sample_root.mkdir(parents=True, exist_ok=True)
    receipt_path = animal_receipt_path(plan["output_root"], sample)
    batch = {"attempt_id": uuid4().hex, "run_name": plan["run_name"],
             "jobs_path": plan["jobs_path"], "jobs_sha256": plan["jobs_sha256"],
             "vispa_config": plan["vispa_config"],
             "vispa_config_sha256": plan["vispa_config_sha256"],
             "vispa_version": plan["vispa_version"], "output_layout": plan["output_layout"],
             "review_settings": plan["review_settings"],
             "settings_sha256": _settings_sha256(plan),
             "requested": plan["requested"], "completed": 0,
             "source_jobs": [{"neuron_id": job["neuron_id"],
                              "job_sha256": _job_sha256(job),
                              "raw_swc_path": job.get("raw_swc_path"),
                              "raw_swc_sha256": job.get("raw_swc_sha256"),
                              "raw_source_receipt": job.get("raw_source_receipt"),
                              "source_acquisition_date": job.get("source_acquisition_date"),
                              "source_acquisition_date_status": job.get("source_acquisition_date_status"),
                              "source_observed_at_utc": job.get("source_observed_at_utc"),
                              "raw_source_file_mtime_utc": job.get("raw_source_file_mtime_utc"),
                              "raw_source_file_mtime_role": job.get("raw_source_file_mtime_role"),
                              "context_source_status": job.get("context_source_status"),
                              "neuron_folder": job.get("neuron_folder")}
                             for job in plan["jobs"]],
             "status": "in_progress", "started_at_utc": datetime.now(timezone.utc).isoformat()}
    update_animal_batch(receipt_path, sample, batch)
    render = renderer or render_review_neuron
    roles = {"Soma", "Context", "Sagittal", "TrioPlot"}
    try:
        for job in plan["jobs"]:
            folder = Path(job["output_dir"])
            if not folder.resolve().is_relative_to((sample_root / "neurons").resolve()):
                raise ValueError("Neuron output escapes the animal folder")
            config = load(Path(plan["vispa_config"]))
            _verified_raw_path(config, job)
            expected = {"job_sha256": _job_sha256(job),
                        "config_sha256": plan["vispa_config_sha256"],
                        "settings_sha256": _settings_sha256(plan),
                        "vispa_version": plan["vispa_version"],
                        "raw_swc_sha256": job.get("raw_swc_sha256"),
                        "output_dir": str(folder)}
            if resume:
                prior = verified_neuron_record(receipt_path, sample, job["neuron_id"], expected)
                if prior is not None:
                    result["completed"].append({**prior, "resume_action": "verified_skip"})
                    batch["completed"] = len(result["completed"])
                    update_animal_batch(receipt_path, sample, batch)
                    continue
            errors, outputs, other_outputs = [], {}, {}
            rendered = {}
            with tempfile.TemporaryDirectory(prefix=".stage-neuron-", dir=sample_root) as temporary:
                stage = Path(temporary)
                try:
                    if _sha256(Path(plan["vispa_config"])) != plan["vispa_config_sha256"]:
                        raise ValueError("VisPa config changed during rendering")
                    rendered = render(job, stage, Path(plan["vispa_config"]))
                    errors.extend(rendered.get("errors", []))
                    from PIL import Image
                    seen = set()
                    for role, value in rendered.get("outputs", {}).items():
                        if role not in roles:
                            continue
                        source = Path(value).resolve(strict=True)
                        if (not source.is_file() or not source.stat().st_size or
                                not source.is_relative_to(stage.resolve()) or source in seen):
                            raise ValueError(f"{role}: invalid or duplicate staged path")
                        seen.add(source)
                        with Image.open(source) as image:
                            if image.format != "PNG":
                                raise ValueError(f"{role}: output is not PNG")
                            image.verify()
                        with Image.open(source) as image:
                            image.load()
                    missing = sorted(roles - set(rendered.get("outputs", {})))
                    if missing:
                        errors.append("Missing verified output roles: " + ", ".join(missing))
                    folder.mkdir(parents=True, exist_ok=True)
                    plot_folder = separate_plot_output_dir(folder, config)
                    role_by_source = {Path(value).resolve(): key
                                      for key, value in rendered.get("outputs", {}).items()
                                      if key in roles}
                    for source in stage.rglob("*"):
                        if not source.is_file():
                            continue
                        # Keep every scientific derivative, including Soma NIfTI.
                        if source.parent != stage:
                            raise ValueError("Renderer created a nested output")
                        role = role_by_source.get(source.resolve())
                        destination = (plot_folder if role in {"Soma", "Context", "Sagittal"}
                                       else folder)
                        destination.mkdir(parents=True, exist_ok=True)
                        target = destination / source.name
                        if target.exists():
                            base = source.name[:-7] if source.name.endswith(".nii.gz") else source.stem
                            suffix = ".nii.gz" if source.name.endswith(".nii.gz") else source.suffix
                            target = destination / f"{base}_{uuid4().hex[:8]}{suffix}"
                        source.replace(target)
                        item = {"path": str(target), "sha256": _sha256(target)}
                        if role is None:
                            other_outputs[target.name] = item
                        else:
                            outputs[role] = item
                    for item in other_outputs.values():
                        sidecar = Path(item["path"])
                        if sidecar.name.endswith(".nii.gz.json"):
                            if repair_nifti_sidecar(sidecar):
                                item["sha256"] = _sha256(sidecar)
                except Exception as exc:
                    errors.append(str(exc))
            missing = sorted(roles - set(outputs))
            if missing:
                errors.append("Missing verified output roles: " + ", ".join(missing))
            record = {**expected, "sample_id": sample, "neuron_id": job["neuron_id"],
                      "neuron_folder": job.get("neuron_folder"),
                      "soma_region": job.get("soma_region"),
                      "soma_region_source": job.get("soma_region_source"),
                      "soma_region_entries": job.get("soma_region_entries"),
                      "vispa_region": job.get("vispa_region"),
                      "soma_xyz": job.get("soma_xyz"),
                      "raw_swc_path": job.get("raw_swc_path"),
                      "raw_source_receipt": job.get("raw_source_receipt"),
                      "source_acquisition_date": job.get("source_acquisition_date"),
                      "source_acquisition_date_status": job.get("source_acquisition_date_status"),
                      "source_observed_at_utc": job.get("source_observed_at_utc"),
                      "raw_source_file_mtime_utc": job.get("raw_source_file_mtime_utc"),
                      "raw_source_file_mtime_role": job.get("raw_source_file_mtime_role"),
                      "raw_swc_source_equivalence": rendered.get("raw_swc_source_equivalence", "unknown"),
                      "context_source_status": job.get("context_source_status"),
                      "role_availability": rendered.get("role_availability"),
                      "outputs": outputs, "other_outputs": other_outputs,
                      "errors": errors, "status": _status_for(outputs, errors),
                      "rendered_at_utc": datetime.now(timezone.utc).isoformat(),
                      "resume_action": "rendered", "anatomical_acceptance": "not established"}
            record_neuron_output(receipt_path, sample, job["neuron_id"], record, batch=batch)
            result["completed"].append(record)
            batch["completed"] = len(result["completed"])
            update_animal_batch(receipt_path, sample, batch)
        result["status"] = ("pass" if result["completed"] and all(
            item["status"] == "rendered_candidate" for item in result["completed"])
            and not (plan["all_jobs"] and plan["skipped_not_ready"])
            and not plan.get("skipped_source_blocked") else "partial_or_failed")
    except Exception as exc:
        result["status"], result["error"] = "partial_or_failed", str(exc)
    batch["status"] = result["status"]
    batch["error"] = result["error"]
    batch["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    update_animal_batch(receipt_path, sample, batch)
    return result


def _run_review_bulk(plan: dict, *, dry_run: bool, renderer=None, resume: bool = False) -> dict:
    result = {
        **plan,
        "status": "dry_run" if dry_run else "in_progress",
        "completed": [],
        "error": None,
    }
    if _sha256(Path(plan["vispa_config"])) != plan["vispa_config_sha256"]:
        raise ValueError("VisPa config changed after job planning")
    if _sha256(Path(plan["jobs_path"])) != plan["jobs_sha256"]:
        raise ValueError("Review jobs changed after planning")
    if plan["output_layout"] == "sample_neurons_flat":
        return _run_review_bulk_flat(plan, dry_run=dry_run, renderer=renderer,
                                     resume=resume)
    if dry_run:
        return result
    output_root = Path(plan["output_root"])
    if output_root.exists() and not resume and plan["output_layout"] == "legacy":
        raise FileExistsError("Fresh output root required; existing plots are not overwritten")
    if output_root.exists() and not resume and any(
        Path(job["output_dir"]).exists() for job in plan["jobs"]):
        raise FileExistsError("A selected neuron run folder already exists; use --resume")
    output_root.mkdir(parents=True, exist_ok=True)
    if plan["output_layout"] == "sample_neurons":
        receipt_root = output_root / plan["sample_id"] / "bulk_runs" / plan["run_name"]
    else:
        receipt_root = output_root
    if not resume and (receipt_root / "batch_receipt.json").exists():
        raise FileExistsError("This job set already has a batch receipt; use --resume")
    if receipt_root.exists() and any(receipt_root.iterdir()) and not (receipt_root / "batch_receipt.json").is_file():
        raise FileExistsError("Run folder contains unrelated files without a batch receipt")
    receipt_root.mkdir(parents=True, exist_ok=True)
    previous_path = receipt_root / "batch_receipt.json"
    if resume and previous_path.is_file():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        for key in ("jobs_sha256", "vispa_config_sha256", "vispa_version", "output_layout"):
            if previous.get(key) != plan[key]:
                raise ValueError(f"Cannot resume: {key} differs from prior batch")
        if previous.get("run_name", plan["run_name"]) != plan["run_name"]:
            raise ValueError("Cannot resume: run_name differs from prior batch")
        if _settings_sha256(previous) != _settings_sha256(plan):
            raise ValueError("Cannot resume: resolved review settings differ")
    render = renderer or render_review_neuron
    if plan["output_layout"] == "sample_neurons":
        for job in plan["jobs"]:
            folder = Path(job["output_dir"])
            if folder.exists() and any(folder.iterdir()):
                receipt = folder / "review_receipt.json"
                if not resume or not receipt.is_file():
                    raise FileExistsError(f"Neuron run folder contains unrelated files: {folder}")
                old = json.loads(receipt.read_text(encoding="utf-8"))
                if old.get("job_sha256") != _job_sha256(job):
                    raise ValueError(f"Neuron run folder belongs to a different job: {folder}")
    try:
        for job in plan["jobs"]:
            folder = Path(job["output_dir"])
            if resume:
                existing = _current_receipt(job, plan)
                if existing is not None:
                    result["completed"].append({**existing, "resume_action": "verified_skip"})
                    _atomic_json(previous_path, result)
                    continue
            folder.mkdir(parents=True, exist_ok=True)
            try:
                if _sha256(Path(plan["vispa_config"])) != plan["vispa_config_sha256"]:
                    raise ValueError("VisPa config changed during rendering")
                rendered = render(job, folder, Path(plan["vispa_config"]))
            except Exception as exc:
                rendered = {"outputs": {}, "errors": [str(exc)]}
            outputs = {}
            errors = list(rendered.get("errors", []))
            seen_paths = set()
            from PIL import Image
            for role, path in rendered.get("outputs", {}).items():
                if role not in {"Soma", "Context", "Sagittal", "TrioPlot"}:
                    continue
                try:
                    candidate = Path(path).resolve(strict=True)
                    if not candidate.is_file() or not candidate.stat().st_size:
                        raise ValueError("not a nonempty file")
                    if plan["output_layout"] == "sample_neurons" and not candidate.is_relative_to(folder.resolve()):
                        raise ValueError("panel path escapes neuron run folder")
                    if candidate in seen_paths:
                        raise ValueError("duplicate panel path")
                    with Image.open(candidate) as image:
                        if image.format != "PNG":
                            raise ValueError("not PNG format")
                        image.verify()
                    with Image.open(candidate) as image:
                        image.load()
                    seen_paths.add(candidate)
                    outputs[role] = {"path": str(candidate), "sha256": _sha256(candidate)}
                except (OSError, TypeError, ValueError) as exc:
                    errors.append(f"{role}: invalid output: {exc}")
            missing = sorted({"Soma", "Context", "Sagittal", "TrioPlot"} - set(outputs))
            if missing:
                errors.append("Missing verified output roles: " + ", ".join(missing))
            status = _status_for(outputs, errors)
            record = {
                "sample_id": job["sample_id"],
                "neuron_id": job["neuron_id"],
                "soma_region": job.get("soma_region"),
                "soma_region_source": job.get("soma_region_source"),
                "soma_region_entries": job.get("soma_region_entries"),
                "vispa_region": job.get("vispa_region"),
                "soma_xyz": job["soma_xyz"],
                "soma_units": job.get("soma_units"),
                "soma_coordinate_source": job.get("soma_coordinate_source"),
                "raw_swc_sha256": job.get("raw_swc_sha256"),
                "raw_swc_source_equivalence": rendered.get("raw_swc_source_equivalence", "unknown"),
                "context_source_status": job.get("context_source_status"),
                "role_availability": rendered.get("role_availability"),
                "fnt_marker": job.get("fnt_marker"),
                "fnt_cluster": job.get("fnt_cluster"),
                "status": status,
                "job_sha256": _job_sha256(job),
                "config_sha256": plan["vispa_config_sha256"],
                "vispa_version": plan["vispa_version"],
                "settings_sha256": _settings_sha256(plan),
                "resume_action": "rendered",
                "outputs": outputs,
                "errors": errors,
                "anatomical_acceptance": "not established",
            }
            _atomic_json(folder / "review_receipt.json", record)
            result["completed"].append(record)
            _atomic_json(previous_path, result)
        result["status"] = (
            "pass" if result["completed"] and all(
                item["status"] == "rendered_candidate" for item in result["completed"])
                and not (plan["all_jobs"] and plan["skipped_not_ready"])
                and not plan.get("skipped_source_blocked")
            else "partial_or_failed")
    except Exception as exc:
        result["status"] = "partial_or_failed"
        result["error"] = str(exc)
    finally:
        _atomic_json(previous_path, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    from vispa import __version__
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--limit", type=int)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="verify and skip complete neuron receipts, retry incomplete neurons")
    parser.add_argument("--skip-existing", action="store_true",
                        help="skip neurons whose required products already exist in output")
    parser.add_argument("--repair-folder-names", action="store_true",
                        help="plan readable names for legacy hash-suffixed neuron folders")
    parser.add_argument("--apply-folder-renames", action="store_true",
                        help="apply folder renames and update the animal receipt")
    parser.add_argument("--migration-report", type=Path,
                        help="write the folder-migration plan/result JSON here")
    args = parser.parse_args(argv)
    try:
        if args.apply_folder_renames and not args.repair_folder_names:
            raise ValueError("--apply-folder-renames requires --repair-folder-names")
        if args.repair_folder_names:
            payload = json.loads(args.jobs.read_text(encoding="utf-8"))
            sample = payload.get("sample_id")
            if not isinstance(sample, str):
                raise ValueError("Jobs file has no sample_id")
            migrations = build_folder_migrations(args.output_root, sample, args.jobs)
            if args.apply_folder_renames:
                result = apply_folder_migrations(args.output_root, sample, migrations)
            else:
                result = {"sample": sample, "renamed": 0,
                          "planned": len(migrations), "mappings": migrations}
            if args.migration_report:
                _atomic_json(args.migration_report, {
                    "schema": "vispa.folder_name_migration.v1",
                    "applied": bool(args.apply_folder_renames),
                    "output_root": str(args.output_root),
                    "results": [result],
                })
            print(json.dumps({"folder_name_migration": result},
                             indent=2, sort_keys=True, default=str))
            return 0 if not result.get("conflicts") else 2
        if not args.limit and not args.all:
            raise ValueError("Use --limit for bounded work, or explicitly opt in to --all")
        plan = load_review_jobs(args.jobs, args.output_root, args.limit, args.all)
        result = run_review_bulk(plan, dry_run=args.dry_run, resume=args.resume,
                                 skip_existing=args.skip_existing)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"dry_run", "pass"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
