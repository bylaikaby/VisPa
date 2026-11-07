"""Render one VisPa review set per published region/FNT job.

Version: 1.20.2 (local/unreleased)
Last updated: 2026-11-07
Change history: ../CHANGELOG.md
Status: candidate

Jobs come from ``vispa_bulk_jobs.json`` written by ``batch.remap_stepwise``.
Each rendered neuron uses the same Soma, Context, Sagittal and TrioPlot calls
as the VisPa GUI. The command does not discover cohorts or rewrite SWCs.

Operator:
  python -m batch.render_review_bulk --jobs PATH --output-root PATH --limit 1 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


_NEURON = re.compile(r"[A-Za-z0-9_-]+\.swc\Z", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}\Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


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
    config_hash = _sha256(config_path)
    if payload.get("vispa_config_sha256") and payload["vispa_config_sha256"] != config_hash:
        raise ValueError("Prepared VisPa config hash differs from current config")
    output_root = Path(output_root).expanduser().resolve()
    if output_root == jobs_path.parent or jobs_path.parent in output_root.parents:
        raise ValueError("Output root must be separate from the jobs file")
    ready, skipped = [], []
    layout = payload.get("output_layout", "legacy")
    if layout not in {"legacy", "sample_neurons"}:
        raise ValueError("output_layout must be legacy or sample_neurons")
    seen = set()
    for entry in payload.get("jobs", []):
        if not isinstance(entry, dict):
            raise ValueError("Each review job must be an object")
        neuron = entry.get("neuron_id")
        if not isinstance(neuron, str) or not _NEURON.fullmatch(neuron):
            raise ValueError("Each neuron_id must be an explicit .swc filename")
        if entry.get("sample_id") != sample:
            raise ValueError("Every job must use the file sample_id")
        identity = (sample.casefold(), neuron.casefold())
        if identity in seen:
            raise ValueError("Review jobs must have unique neurons including case-insensitive names")
        seen.add(identity)
        if entry.get("render_ready") is True:
            ready.append({
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
            })
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
    for entry in selected:
        if layout == "sample_neurons":
            folder = output_root / sample / "neurons" / entry["neuron_id"][:-4] / f"bulk_{jobs_hash[:12]}"
        else:
            folder = output_root / sample / entry["neuron_id"][:-4]
        entry["output_dir"] = str(folder)
    from vispa import __version__
    review_settings, figure_output_root = {}, None
    if layout == "sample_neurons":
        from vispa.config import load, resolve_settings
        resolved_config = load(config_path)
        review_settings = resolve_settings("review", config=resolved_config)
        figure_output_root = str(resolved_config["visual_toolkit"]["figure_output_root"])
    return {
        "schema": payload["schema"],
        "jobs_path": str(jobs_path),
        "jobs_sha256": jobs_hash,
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


def render_review_neuron(job: dict, output_dir: Path, config_path: Path) -> dict:
    """Render one neuron with the GUI's toolkit calls."""
    import matplotlib
    matplotlib.use("Agg", force=False)
    from vispa.config import load
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
    region = job.get("soma_region")
    tool = VisPa(job["sample_id"])
    panels, errors = {}, []
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
            wide, wide_origin, wide_resolution = tool.get_low_res_widefield(
                request.soma_xyz, width_um=request.width_um,
                height_um=request.height_um, depth_um=request.depth_um)
            panels["Context"] = tool.plot_widefield_context(
                wide, wide_origin, wide_resolution, request.soma_xyz, job["neuron_id"],
                swc_tree=tree, soma_region=region, output_dir=str(output_dir))
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


def run_review_bulk(plan: dict, *, dry_run: bool, renderer=None, resume: bool = False) -> dict:
    if dry_run:
        return _run_review_bulk(plan, dry_run=True, renderer=renderer, resume=resume)
    from vispa.batch_run_lock import exclusive_batch
    root = Path(plan["output_root"])
    lock = root.parent / f".{root.name}.review_bulk.lock"
    with exclusive_batch(lock):
        return _run_review_bulk(plan, dry_run=False, renderer=renderer, resume=resume)


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
        receipt_root = output_root / plan["sample_id"] / "bulk_runs" / f"bulk_{plan['jobs_sha256'][:12]}"
    else:
        receipt_root = output_root
    if not resume and (receipt_root / "batch_receipt.json").exists():
        raise FileExistsError("This job set already has a batch receipt; use --resume")
    receipt_root.mkdir(parents=True, exist_ok=True)
    previous_path = receipt_root / "batch_receipt.json"
    if resume and previous_path.is_file():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        for key in ("jobs_sha256", "vispa_config_sha256", "vispa_version", "output_layout"):
            if previous.get(key) != plan[key]:
                raise ValueError(f"Cannot resume: {key} differs from prior batch")
        if _settings_sha256(previous) != _settings_sha256(plan):
            raise ValueError("Cannot resume: resolved review settings differ")
    render = renderer or render_review_neuron
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
                "soma_xyz": job["soma_xyz"],
                "soma_units": job.get("soma_units"),
                "soma_coordinate_source": job.get("soma_coordinate_source"),
                "raw_swc_sha256": job.get("raw_swc_sha256"),
                "raw_swc_source_equivalence": rendered.get("raw_swc_source_equivalence", "unknown"),
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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--limit", type=int)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="verify and skip complete neuron receipts, retry incomplete neurons")
    args = parser.parse_args(argv)
    try:
        plan = load_review_jobs(args.jobs, args.output_root, args.limit, args.all)
        result = run_review_bulk(plan, dry_run=args.dry_run, resume=args.resume)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"dry_run", "pass"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
