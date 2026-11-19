"""Render a validated FNT score matrix and its hierarchical ordering.

Version: 0.2.2.dev1 (local/unreleased)
Last updated: 2026-11-17
Change history: ../../../CHANGELOG.md
- 2026-11-17: Add headless, identity-bound dendrogram and matrix plot.
Status: candidate
"""
import argparse
import hashlib
import json
from pathlib import Path

from scipy.cluster.hierarchy import dendrogram

from .. import __version__

from .clustering_validation import read_fnt_distances, safe_linkage


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distance", type=Path, required=True)
    parser.add_argument("--joined-fnt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--linkage", choices=("average", "complete", "single"), default="average")
    parser.add_argument("--title", default="Historical FNT score matrix")
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".png" or args.output.exists():
        parser.error("Output must be a new PNG")
    if not 72 <= args.dpi <= 600:
        parser.error("DPI must be between 72 and 600")
    matrix, metadata = read_fnt_distances(args.distance, args.joined_fnt)
    tree = safe_linkage(matrix, method=args.linkage)
    plan = {"version": __version__, "distance": str(args.distance), "distance_sha256": sha256(args.distance),
            "joined_fnt": str(args.joined_fnt), "joined_fnt_sha256": sha256(args.joined_fnt),
            "output": str(args.output), "linkage": args.linkage, "dpi": args.dpi,
            "title": args.title, "n_neurons": len(matrix), "input": metadata}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    fig = plt.figure(figsize=(9, 10))
    ax = fig.add_axes([.13, .76, .72, .17])
    heat = fig.add_axes([.13, .1, .72, .64])
    cb = fig.add_axes([.88, .1, .025, .64])
    ordering = dendrogram(tree, no_labels=True, ax=ax, color_threshold=0,
                          above_threshold_color="#334c5a")["leaves"]
    ax.set_ylabel("Linkage height")
    ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
    values = matrix.to_numpy()[np.ix_(ordering, ordering)]
    image = heat.imshow(values, cmap="viridis", aspect="auto", interpolation="nearest")
    heat.set(xlabel="Neuron order in dendrogram", ylabel="Neuron order in dendrogram")
    fig.colorbar(image, cax=cb, label="FNT Score (units unspecified)")
    fig.suptitle(args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        fig.savefig(stream, format="png", dpi=args.dpi,
                    metadata={"Description": json.dumps(plan, ensure_ascii=True)})
    plt.close(fig)
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()