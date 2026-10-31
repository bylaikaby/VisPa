"""Render one VisPa review set per published region/FNT job.

Version: 1.12.0.dev2 (local/unreleased)
Last updated: 2026-10-31
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


def _verified_raw_path(config: dict, job: dict) -> Path | None:
    expected = job.get("raw_swc_sha256")
    if expected is None:
        return None
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Invalid expected raw SWC hash")
    from vispa.data_input_adaptor import resolve_declared_raw_swc
    root = (config.get("sources") or {}).get("legacy_raw_swc_root")
    if not root:
        raise ValueError("VisPa config lacks declared raw SWC root")
    path = resolve_declared_raw_swc(root, job["sample_id"], job["neuron_id"])
    if _sha256(path).lower() != expected.lower():
        raise ValueError("Configured raw SWC differs from stepwise soma source")
    return path


def render_review_neuron(job: dict, output_dir: Path, config_path: Path) -> dict:
    """Render one neuron with the GUI's toolkit calls."""
    import matplotlib
    matplotlib.use("Agg", force=False)
    from vispa.config import load
    from vispa.reviewer import make_processing_request
    from vispa.data_input_adaptor import load_raw_neuron
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
            tree = load_raw_neuron(config, job["sample_id"], job["neuron_id"], allow_download=False)
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


def run_review_bulk(plan: dict, *, dry_run: bool, renderer=None) -> dict:
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
    if output_root.exists():
        raise FileExistsError("Fresh output root required; existing plots are not overwritten")
    output_root.mkdir(parents=True)
    render = renderer or render_review_neuron
    try:
        for job in plan["jobs"]:
            folder = Path(job["output_dir"])
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
                "outputs": outputs,
                "errors": errors,
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
    from vispa import __version__
    parser.add_argument("--version", action="version", version=__version__)
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
