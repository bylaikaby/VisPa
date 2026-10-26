"""Render one VisPa review set per published region/FNT job.

Version: 1.11.0.dev18 (local/unreleased)
Last updated: 2026-10-27
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
    output_root = Path(output_root).expanduser().resolve()
    if output_root == jobs_path.parent or jobs_path.parent in output_root.parents:
        raise ValueError("Output root must be separate from the jobs file")
    ready, skipped = [], []
    seen = set()
    for entry in payload.get("jobs", []):
        if not isinstance(entry, dict):
            raise ValueError("Each review job must be an object")
        neuron = entry.get("neuron_id")
        if not isinstance(neuron, str) or not _NEURON.fullmatch(neuron):
            raise ValueError("Each neuron_id must be an explicit .swc filename")
        if entry.get("sample_id") != sample:
            raise ValueError("Every job must use the file sample_id")
        if (sample, neuron) in seen:
            raise ValueError("Review jobs must have unique neurons")
        seen.add((sample, neuron))
        if entry.get("render_ready") is True:
            ready.append({
                "sample_id": sample,
                "neuron_id": neuron,
                "soma_region": entry.get("soma_region"),
                "soma_xyz": _finite_xyz(entry.get("soma_xyz"), f"{neuron} soma_xyz"),
                "soma_units": entry.get("soma_units"),
                "soma_coordinate_source": entry.get("soma_coordinate_source"),
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
    for entry in selected:
        entry["output_dir"] = str(output_root / sample / entry["neuron_id"][:-4])
    return {
        "schema": payload["schema"],
        "jobs_path": str(jobs_path),
        "jobs_sha256": _sha256(jobs_path),
        "vispa_config": str(config_path),
        "vispa_config_sha256": _sha256(config_path),
        "output_root": str(output_root),
        "sample_id": sample,
        "requested": len(selected),
        "skipped_not_ready": skipped,
        "jobs": selected,
        "anatomical_acceptance": "not established",
    }


def render_review_neuron(job: dict, output_dir: Path, config_path: Path) -> dict:
    """Render one neuron with the GUI's toolkit calls."""
    import matplotlib
    matplotlib.use("Agg", force=False)
    from vispa.dataset_config import load
    from vispa.gui import make_processing_request
    from vispa.sources import IONData
    from vispa.toolkit import BLOCK_SIZE_PIXELS, REVIEW_SETTINGS, VisPa, configure_data_sources

    configure_data_sources(config=load(config_path))
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
            tree = IONData().getRawNeuronTreeByID(job["sample_id"], job["neuron_id"])
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
            panels["Sagittal"] = tool.render_sagittal_context_from_ds(
                job["neuron_id"], request.soma_xyz, output_dir=str(output_dir),
                soma_region=region)["panel"]
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
    return {"outputs": outputs, "errors": errors}


def _status_for(result: dict) -> str:
    outputs = [path for path in result.get("outputs", {}).values() if path]
    if result.get("errors") and outputs:
        return "partial"
    if result.get("errors") or not outputs:
        return "failed"
    return "rendered_candidate"


def run_review_bulk(plan: dict, *, dry_run: bool, renderer=None) -> dict:
    result = {
        **plan,
        "status": "dry_run" if dry_run else "in_progress",
        "completed": [],
        "error": None,
    }
    if dry_run:
        return result
    output_root = Path(plan["output_root"])
    if output_root.exists():
        raise FileExistsError("Fresh output root required; existing plots are not overwritten")
    output_root.mkdir(parents=True)
    render = renderer or render_review_neuron
    try:
        for job in plan["jobs"]:
            folder = Path(job["output_dir"])
            folder.mkdir(parents=True, exist_ok=True)
            try:
                rendered = render(job, folder, Path(plan["vispa_config"]))
                status = _status_for(rendered)
            except Exception as exc:
                rendered = {"outputs": {}, "errors": [str(exc)]}
                status = "failed"
            outputs = {}
            for role, path in rendered.get("outputs", {}).items():
                if path and Path(path).is_file():
                    outputs[role] = {"path": str(path), "sha256": _sha256(Path(path))}
            record = {
                "sample_id": job["sample_id"],
                "neuron_id": job["neuron_id"],
                "soma_region": job.get("soma_region"),
                "soma_xyz": job["soma_xyz"],
                "soma_units": job.get("soma_units"),
                "soma_coordinate_source": job.get("soma_coordinate_source"),
                "fnt_marker": job.get("fnt_marker"),
                "fnt_cluster": job.get("fnt_cluster"),
                "status": status,
                "outputs": outputs,
                "errors": rendered.get("errors", []),
                "anatomical_acceptance": "not established",
            }
            _atomic_json(folder / "review_receipt.json", record)
            result["completed"].append(record)
        result["status"] = (
            "pass" if result["completed"] and all(
                item["status"] == "rendered_candidate" for item in result["completed"])
            else "partial_or_failed")
    except Exception as exc:
        result["status"] = "partial_or_failed"
        result["error"] = str(exc)
    finally:
        _atomic_json(output_root / "batch_receipt.json", result)
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
        plan = load_review_jobs(args.jobs, args.output_root, args.limit, args.all)
        result = run_review_bulk(plan, dry_run=args.dry_run)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
        result = {"status": "failed", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"dry_run", "pass"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
