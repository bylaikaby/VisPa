"""Compare exploratory hierarchical cuts from saved FNT scores.

Version: 0.2.2.dev1 (local/unreleased)
Last updated: 2026-11-17
Change history: ../../../CHANGELOG.md
- 2026-11-17: Add identity-bound comparison, optional ratio normalization and hash-bound completion metadata.
Status: candidate
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from .. import __version__

from .clustering_validation import evaluate_k, file_sha256, read_fnt_distances
from .fnt_pipeline import analysis_matrix, ratio_matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distance", type=Path, required=True)
    parser.add_argument("--joined-fnt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--score-mode", choices=("raw", "ratio"), default="raw")
    parser.add_argument("--representation", choices=("raw", "log1p", "spearman_profile"), default="raw")
    parser.add_argument("--linkage", choices=("average", "complete", "single"), default="average")
    parser.add_argument("--min-k", type=int, default=2)
    parser.add_argument("--max-k", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--fraction", type=float, default=.8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output directory must be new")
    matrix, provenance = read_fnt_distances(args.distance, args.joined_fnt)
    if not 0 < args.fraction < 1 or args.repeats < 1:
        parser.error("Fraction must be between 0 and 1 and repeats must be positive")
    if not 2 <= args.min_k <= args.max_k < int(len(matrix) * args.fraction):
        parser.error("Candidate k must fit the subsample")
    values = matrix.to_numpy()
    if args.score_mode == "ratio":
        values = ratio_matrix(args.distance, values)
    transformed = analysis_matrix(values, args.representation, 0)
    plan = {"version": __version__, "distance": str(args.distance), "joined_fnt": str(args.joined_fnt),
            "provenance": provenance, "n_neurons": len(matrix), "output": str(args.output),
            "score_mode": args.score_mode, "representation": args.representation, "linkage": args.linkage,
            "min_k": args.min_k, "max_k": args.max_k, "repeats": args.repeats,
            "fraction": args.fraction, "seed": args.seed, "final_k": None,
            "status": "exploratory; stability of fixed score matrix"}
    if args.dry_run:
        print(json.dumps(plan, indent=2, allow_nan=False))
        return
    diagnostics, labels, stability, _ = evaluate_k(
        transformed, list(range(args.min_k, args.max_k + 1)),
        repeats=args.repeats, fraction=args.fraction, seed=args.seed, method=args.linkage)
    args.output.mkdir(parents=True, exist_ok=False)
    assignments = pd.DataFrame({"FNT_NeuronID": matrix.index})
    for k, values in labels.items():
        assignments[f"k_{k}"] = values
        stability[k].to_csv(args.output / f"cluster_stability_k{k}.csv", index=False)
    assignments.to_csv(args.output / "candidate_cluster_assignments.csv", index=False)
    diagnostics.to_csv(args.output / "clustering_diagnostics.csv", index=False)
    result_paths = [args.output / "candidate_cluster_assignments.csv",
                    args.output / "clustering_diagnostics.csv"] + [
        args.output / f"cluster_stability_k{k}.csv" for k in labels]
    plan["result_sha256"] = {path.name: file_sha256(path) for path in result_paths}
    temporary_metadata = args.output / "metadata.json.pending"
    temporary_metadata.write_text(json.dumps(plan, indent=2, allow_nan=False), encoding="utf-8")
    temporary_metadata.replace(args.output / "metadata.json")
    print(json.dumps(plan, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()