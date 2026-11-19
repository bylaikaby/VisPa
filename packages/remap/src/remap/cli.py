"""ReMAP bounded local operator.

Version: 0.2.2.dev3 (local/unreleased)
Last updated: 2026-11-18
Change history:
- 2026-11-18: Add progress for saved Projectome snapshots and matching regional receipts.
- 2026-11-09: one, population, FNT, table, and DS00 selection commands.
- 2026-11-10: one and population use designated atlas defaults. run starts from animal and neuron IDs.
- 2026-11-10: Imports follow ds_normalisation/, morph_clustering/, and run_analysis.py.
- 2026-11-17: Expose clustered workbook evolution with explicit candidate CSVs.
Status: candidate
"""
import argparse
import json
import os
import math
from pathlib import Path
import tempfile
from scipy.cluster.hierarchy import fcluster

from . import __version__
from .cohort_progress import configure_progress_parser, run_progress
from .run_analysis import analyze_one, parse_cases, run_analysis, sha256
from .morph_clustering.clustering_validation import read_fnt_distances, safe_linkage
from .table import plan_table, write_table
from .config import as_population, load as load_config
from .population_operator import plan_population, run_population
from .ds_normalisation.ds00_selection import resolve_selection
from .morph_clustering.fnt_pipeline import validate_settings, run_pipeline, run_saved_analysis, TRANSFORMS, REPRESENTATIONS, LINKAGES
from .atlas_profile import designated_atlas_version, designated_population_paths


def _fnt_output_allowed(workspace_root, output_root) -> bool:
    """Allow a run folder under the checkout work directory or the server remap_outputs tree."""
    output = Path(output_root)
    work = Path(workspace_root).resolve() / "work"
    server = Path(r"\\10.102.8.200\microscopy_data\fMOST\remap_outputs")
    return str(output).startswith(str(work)) or str(output).lower().startswith(str(server).lower())


def build_parser():
    """Build the ReMAP CLI. Atlas defaults come from the designated DEB share profile."""
    parser = argparse.ArgumentParser(prog="remap", description=f"ReMAP {__version__} local candidate")
    atlas_paths = designated_population_paths()
    atlas_version = designated_atlas_version()
    parser.add_argument("--version", action="version", version=f"ReMAP {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    progress = sub.add_parser("progress", help="validate and illustrate a saved Progress Manager export")
    configure_progress_parser(progress)
    ds00 = sub.add_parser("ds00-selection", help="read shared DS00 selections; region binding remains unverified")
    ds00.add_argument("--registry", type=Path, required=True)
    ds00.add_argument("--sample-id", required=True)
    ds00.add_argument("--swc-frame", help="request processed-SWC binding; fails until verified")
    one = sub.add_parser(
        "one", help="one local SWC and atlas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Designated fMOST share defaults (VisPa sources.atlas):\n"
               f"  --atlas {atlas_paths['atlas']}\n"
               f"  --atlas-key {atlas_paths['atlas_key']}")
    one.add_argument("--swc", type=Path, required=True)
    one.add_argument("--atlas", type=Path, default=Path(atlas_paths["atlas"]),
                     help="atlas volume; omit to use the designated fMOST share profile")
    one.add_argument("--atlas-key", type=Path, default=Path(atlas_paths["atlas_key"]),
                     help="atlas key; omit to use the designated fMOST share profile")
    one.add_argument("--sample-id", required=True)
    one.add_argument("--neuron-id", required=True)
    one.add_argument("--declared-space", required=True,
                     help=f"caller-declared mapping space; the designated atlas version is {atlas_version}")
    one.add_argument("--coordinate-scale", type=float, required=True,
                     help="source µm per atlas voxel; the designated NMT profile uses 250")
    one.add_argument("--coordinate-offset", type=float, nargs=3, default=(0, 0, 0))
    one.add_argument("--atlas-level", type=int, default=6)
    one.add_argument("--output", type=Path, required=True)
    one.add_argument("--dry-run", action="store_true")
    fnt = sub.add_parser("fnt", help="validate joined FNT distance and average linkage")
    fnt.add_argument("--distance", type=Path, required=True)
    fnt.add_argument("--joined-fnt", type=Path, required=True)
    fnt.add_argument("--output", type=Path, required=True)
    fnt.add_argument("--k", type=int, help="exploratory maximum cluster count; no automatic K selection")
    fnt.add_argument("--dry-run", action="store_true")
    pipeline = sub.add_parser("fnt-pipeline", help="bounded legacy FNT production with optional exploratory paper parameters")
    pipeline.add_argument("--version", action="version", version=f"ReMAP {__version__}")
    pipeline.add_argument("--config", type=Path, required=True, help="JSON with exact cases or cohort_table + selected_uids")
    pipeline.add_argument("--max-cases", type=int, required=True, help="explicit bound, 1..32")
    pipeline.add_argument("--dry-run", action="store_true")
    pipeline.add_argument("--transform-mode", choices=TRANSFORMS)
    pipeline.add_argument("--midline-x", type=float)
    pipeline.add_argument("--decimate-distance", type=float)
    pipeline.add_argument("--decimate-area", type=float)
    pipeline.add_argument("--decimation", choices=("on", "off"),
                          help="default on: legacy simplification; off: explicit undecimated reference control")
    pipeline.add_argument("--score-mode", choices=("raw", "ratio"))
    pipeline.add_argument("--representation", choices=REPRESENTATIONS)
    pipeline.add_argument("--penalty-factor", type=float)
    pipeline.add_argument("--penalty-absolute", type=float)
    pipeline.add_argument("--linkage", choices=LINKAGES)
    pipeline.add_argument("--candidate-k", type=int, action="append")
    pipeline.add_argument("--cluster", action="store_true", help="enable configured exploratory clustering; never chooses final k")
    saved = sub.add_parser("fnt-analyze", help="analyze hash-bound saved FNT scores with optional settings; no producer rerun")
    saved.add_argument("--version", action="version", version=f"ReMAP {__version__}")
    saved.add_argument("--producer-receipt", type=Path, required=True)
    saved.add_argument("--config", type=Path, required=True, help="JSON with workspace_root, output_root, clustering settings")
    saved.add_argument("--max-cases", type=int, required=True, help="explicit bound, 3..32")
    saved.add_argument("--dry-run", action="store_true")
    clustered = sub.add_parser("clustered-table", help="add exploratory cluster candidates to a neuron workbook")
    clustered.add_argument("--source", type=Path, required=True)
    clustered.add_argument("--output", type=Path, required=True)
    clustered.add_argument("--sample", required=True)
    clustered.add_argument("--assignment", nargs=2, action="append", metavar=("NAME", "CSV"), required=True)
    clustered.add_argument("--dry-run", action="store_true")
    table = sub.add_parser("table", help="export explicit one-neuron JSON inputs for legacy PA analysis-source registration")
    table.add_argument("--input", type=Path, action="append", required=True)
    table.add_argument("--output", type=Path, required=True)
    table.add_argument("--source-date", help="declared source version YYYYMMDD; omitted means unknown")
    table.add_argument("--source-id", default="remap_neurons", help="unique registry source ID, e.g. remap_neurons_251637")
    table.add_argument("--registry-path", type=Path, help="legacy PA registry anchor for relative registration path; never modified")
    table.add_argument("--dry-run", action="store_true")
    population = sub.add_parser(
        "population", help="full local Step1 population workbook and manager registration receipt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Omitted atlas inputs use the designated fMOST share profile:\n"
               f"  atlas {atlas_paths['atlas']}\n"
               f"  atlas_key {atlas_paths['atlas_key']}\n"
               f"  hemisphere_mask {atlas_paths['hemisphere_mask']}\n"
               "template, cortex_hierarchy_csv, and subcortical_hierarchy_csv stay in the JSON.")
    population.add_argument("--config", type=Path, help="package YAML or a JSON override; default is the packaged profile")
    population.add_argument("--sample-id", help="sample id when using the packaged resources/cache/output profile")
    population.add_argument("--neuron-id", action="append", help="exact SWC basename; required for the packaged profile")
    population.add_argument("--generate-plots", action="store_true", help="write this run's summary report plots; off unless set")
    population.add_argument("--swc-plots", choices=["off", "montage", "each"], default=None)
    population.add_argument("--refresh", action="store_true", help="fetch each selected SWC from IONData even when the cache file exists")
    population.add_argument("--dry-run", action="store_true")
    started = sub.add_parser("run", help="start region analysis from animal_id/neuron.swc; several animals stay grouped")
    started.add_argument("--case", action="append", required=True, help="animal_id/neuron.swc; repeat for more neurons or animals")
    started.add_argument("--config", type=Path, help="package YAML or a JSON override")
    started.add_argument("--refresh", action="store_true", help="replace cached SWCs from IONData")
    started.add_argument("--generate-plots", action="store_true")
    started.add_argument("--swc-plots", choices=["off", "montage", "each"], default=None)
    started.add_argument("--dry-run", action="store_true")
    return parser


def run(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "progress":
        try:
            result = run_progress(args)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result
    if args.command == "ds00-selection":
        result = resolve_selection(args.registry, args.sample_id, swc_frame=args.swc_frame)
        print(json.dumps(result, indent=2))
        return result
    if args.command == "fnt-analyze":
        if not 3 <= args.max_cases <= 32:
            parser.error("--max-cases must be 3..32")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if set(config) != {"workspace_root", "output_root", "clustering"}:
            parser.error("FNT analysis config requires exactly workspace_root, output_root and clustering")
        original = json.loads(args.producer_receipt.read_text(encoding="utf-8"))
        source = original["plan"]
        for case in source["cases"]:
            if case["uid"] != f"{case['sample_id']}|{case['neuron_id']}":
                parser.error("Producer case UID does not match sample and neuron")
        cases = [{k: case[k] for k in ("sample_id", "neuron_id", "swc_path", "swc_sha256")} for case in source["cases"]]
        combined = {"cases": cases, "binary_dir": source["binary_dir"],
                    "output_root": config["output_root"], "clustering": config["clustering"]}
        plan = validate_settings(combined, offline=True)
        if len(plan["cases"]) > args.max_cases:
            parser.error(f"Resolved {len(plan['cases'])} cases exceeds --max-cases")
        if "workspace_root" not in config or not _fnt_output_allowed(config["workspace_root"], plan["output_root"]):
            parser.error("FNT analysis output must stay under explicit workspace_root/work or the server remap_outputs folder")
        result = run_saved_analysis(args.producer_receipt, plan, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, allow_nan=False))
        return result
    if args.command == "fnt-pipeline":
        if not 1 <= args.max_cases <= 32:
            parser.error("--max-cases must be 1..32")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if args.cluster:
            config["clustering"] = {**config.get("clustering", {}), "enabled": True}
        plan = validate_settings(config, {
            "mode": args.transform_mode, "midline_x": args.midline_x,
            "distance": args.decimate_distance, "area": args.decimate_area,
            "decimation_enabled": None if args.decimation is None else args.decimation == "on",
            "score_mode": args.score_mode, "representation": args.representation,
            "penalty_factor": args.penalty_factor, "penalty_absolute": args.penalty_absolute,
            "linkage": args.linkage,
            "candidate_k": args.candidate_k})
        if len(plan["cases"]) > args.max_cases:
            parser.error(f"Resolved {len(plan['cases'])} cases exceeds --max-cases")
        if "workspace_root" not in config:
            parser.error("FNT config requires explicit workspace_root")
        if not _fnt_output_allowed(config["workspace_root"], plan["output_root"]):
            parser.error("FNT outputs must stay under workspace_root/work or the server remap_outputs folder")
        plan["operator_version"] = __version__
        if args.dry_run:
            print(json.dumps(plan, indent=2, allow_nan=False))
            return plan
        result = run_pipeline(plan)
        print(json.dumps({"receipt": str(Path(plan["output_root"]) / "receipt.json"),
                          "distance": result["distance"], "n": len(plan["cases"]),
                          "final_k": None}, indent=2))
        return result
    if args.command == "clustered-table":
        from .morph_clustering.clustered_table import evolve
        result = evolve(args.source, args.output, args.sample, args.assignment, args.dry_run)
        print(json.dumps(result, indent=2))
        return result
    if args.command == "run":
        parse_cases(args.case)
        loaded = load_config(args.config)
        result = run_analysis(
            cases=args.case, config=loaded, refresh=args.refresh,
            generate_plots=True if args.generate_plots else None,
            swc_plots=args.swc_plots, dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, default=str))
        return result
    if args.command == "population":
        loaded = load_config(args.config)
        config = as_population(loaded, sample_id=args.sample_id or loaded.get("sample_id"),
                               neuron_ids=args.neuron_id or loaded.get("neuron_ids") or [])
        if args.generate_plots:
            config["generate_plots"] = True
        if args.swc_plots:
            config["swc_plots"] = args.swc_plots
        if args.refresh:
            config["refresh_swc"] = True
        plan = plan_population(config, neuron_ids=args.neuron_id)
        if args.dry_run:
            print(json.dumps(plan, indent=2, allow_nan=False))
            return plan
        result = run_population(plan)
        print(json.dumps({"workbook": result["workbook"], "rows": result["rows"],
                          "sheets": result["sheets"], "receipt": result["receipt"]}, indent=2))
        return result
    if args.command == "table":
        rows, report = plan_table(args.input, args.output, args.source_date, args.registry_path, args.source_id)
        if args.dry_run:
            print(json.dumps(report, indent=2, allow_nan=False))
            return report
        saved = write_table(rows, report)
        print(json.dumps({"output": saved["output"], "receipt": saved["receipt"],
                          "rows": saved["rows"], "table_sha256": saved["table_sha256"]}, indent=2))
        return saved
    if args.command == "one":
        if (not math.isfinite(args.coordinate_scale) or args.coordinate_scale <= 0
                or len(args.coordinate_offset) != 3
                or not all(math.isfinite(value) for value in args.coordinate_offset)
                or not 1 <= args.atlas_level <= 6
                or not args.sample_id.strip() or args.sample_id != args.sample_id.strip()
                or not args.neuron_id.strip() or args.neuron_id != args.neuron_id.strip()
                or Path(args.neuron_id).name != args.neuron_id
                or args.swc.name != args.neuron_id or not args.declared_space.strip()):
            parser.error("Invalid identity, declared space, atlas level, or coordinate mapping")
        inputs = {"swc": args.swc, "atlas": args.atlas, "atlas_key": args.atlas_key}
        settings = {"sample_id": args.sample_id, "neuron_id": args.neuron_id,
                    "declared_space": args.declared_space, "coordinate_scale": args.coordinate_scale,
                    "coordinate_offset": args.coordinate_offset, "atlas_level": args.atlas_level}
    else:
        inputs = {"distance": args.distance, "joined_fnt": args.joined_fnt}
        if args.k is not None and args.k < 2:
            parser.error("FNT k must be at least 2")
        settings = {"linkage": "average", "symmetrization": "max", "k": args.k}
    resolved = {"version": __version__, "command": args.command,
                "inputs": {key: {"path": str(path.resolve()),
                                 "sha256": sha256(path) if path.is_file() else None}
                           for key, path in inputs.items()},
                "parameters": settings, "output": str(args.output.resolve())}
    if args.output.exists():
        raise FileExistsError(args.output)
    if any(not path.is_file() for path in inputs.values()):
        raise FileNotFoundError("One or more declared inputs do not exist")
    if args.dry_run:
        print(json.dumps(resolved, indent=2, default=str))
        return resolved
    if args.command == "one":
        result = analyze_one(**inputs, **settings)
    else:
        matrix, metadata = read_fnt_distances(args.distance, args.joined_fnt)
        if args.k is not None and args.k >= len(matrix):
            parser.error("FNT k must be below the neuron count")
        linkage = safe_linkage(matrix, method="average")
        result = {"schema": "remap.fnt_validation.v1", "neuron_ids": matrix.index.tolist(),
                  "source_metadata": metadata, "linkage_rows": linkage.tolist(),
                  "requested_k": args.k,
                  "cluster_labels": fcluster(linkage, args.k, criterion="maxclust").tolist() if args.k else None,
                  "method": "raw FNT distance; average linkage; exploratory cut only"}
    result["run"] = resolved
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".remap-", suffix=".json", dir=args.output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        if os.name == "nt":
            os.rename(temp_name, args.output)  # Windows refuses an existing destination
        else:
            os.link(temp_name, args.output)  # exclusive creation on POSIX
    finally:
        Path(temp_name).unlink(missing_ok=True)
    print(args.output.resolve())
    return result


def main(argv=None):
    """Return a process status for the generated console launcher."""
    run(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
