"""Read and illustrate an exported Projectome Progress Manager snapshot.

Version: 0.2.2.dev3 (local/unreleased)
Last updated: 2026-11-18
Change history: ../../CHANGELOG.md
2026-11-18: join saved atlas counts to a ReMAP cohort and share the report
through the ReMAP CLI and downstream VisPa preview.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

from ._version import __version__


_COLUMNS = {
    "generated_at", "monkey_id", "fmost_id", "neurons_screened", "selected_n",
    "ARM_insula_n", "arm_regions", "insula_8_cohort",
}
_PARCEL = re.compile(r"(.+?)\s+L\s+(\d+)\s*/\s*R\s+(\d+)")
_SIDE_COLORS = ("#cb781d", "#286a81")


def _source(path):
    path = Path(path).expanduser().resolve(strict=True)
    with path.open("rb") as stream:
        contents = stream.read(16 * 1024**2 + 1)
    if len(contents) > 16 * 1024**2:
        raise ValueError(f"Cohort progress input exceeds 16 MiB: {path}")
    return contents.decode("utf-8-sig"), {
        "path": str(path), "sha256": hashlib.sha256(contents).hexdigest(),
    }


def _count(value, column):
    if not re.fullmatch(r"[0-9]+(?:\.0+)?", value.strip()):
        raise ValueError(f"Expected a nonnegative count for {column}: {value!r}")
    return int(value.split(".", 1)[0])


def _progress_rows(text):
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not _COLUMNS.issubset(reader.fieldnames or ()) or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("Select a Progress Manager export with the required, unique columns")
    samples = {}
    totals = []
    dates = set()
    for row in reader:
        if None in row or any(row[col] is None for col in _COLUMNS):
            raise ValueError("Malformed Progress Manager row")
        date = row["generated_at"].strip()
        if date:
            dates.add(date)
        animal, sample = row["monkey_id"].strip(), row["fmost_id"].strip()
        selected = row["selected_n"].strip()
        counts = dict(
            screened=_count(row["neurons_screened"], "neurons_screened"),
            selected=None if selected in ("", "—") else _count(selected, "selected_n"),
            atlas_insula=_count(row["ARM_insula_n"], "ARM_insula_n"),
        )
        if animal == "TOTAL":
            totals.append(counts)
            continue
        if not animal or not sample or sample in samples:
            raise ValueError(f"Invalid or duplicate sample in Progress Manager: {sample!r}")
        parcels = {}
        for line in row["arm_regions"].splitlines():
            line = line.strip()
            if line in ("", "—"):
                continue
            match = _PARCEL.fullmatch(line)
            if not match or match[1] in parcels:
                raise ValueError(f"Malformed or duplicate ARM parcel for {sample}: {line!r}")
            parcels[match[1]] = [int(match[2]), int(match[3])]
        if sum(sum(pair) for pair in parcels.values()) != counts["atlas_insula"]:
            raise ValueError(f"ARM parcel counts do not reconcile for {sample}")
        samples[sample] = dict(animal=animal, sample=sample, group=row["insula_8_cohort"],
                               source_row_date=date or None, parcels=parcels, **counts)
    summed = {key: sum(row[key] or 0 for row in samples.values())
              for key in ("screened", "selected", "atlas_insula")}
    if not samples or totals != [summed] or len(dates) != 1:
        raise ValueError("Progress Manager totals or export date do not reconcile")
    return samples, dates.pop()


def _match_cohort(text, samples):
    receipt = json.loads(text)
    entries = receipt.get("neurons") if isinstance(receipt, dict) else None
    if not isinstance(entries, list) or receipt.get("selected_size") != len(entries):
        raise ValueError("Select a ReMAP regional measurement receipt with per-neuron rows")
    by_animal = {}
    for sample, row in samples.items():
        by_animal.setdefault(row["animal"], []).append(sample)
    observed = Counter()
    seen = set()
    types = {sample: Counter() for sample in samples}
    for cell in entries:
        animal, identity = cell["animal"], cell["neuron"]
        candidates = [s for s in by_animal.get(animal, ()) if identity.startswith(s + "_")]
        side = cell["soma_side"]
        prefix = f"C{side}_"
        region = cell["soma_region"]
        label = cell["neuron_type"]
        if (identity in seen or len(candidates) != 1 or side not in ("L", "R")
                or not region.startswith(prefix) or not isinstance(label, str) or not label.strip()):
            raise ValueError(f"Invalid, duplicate or unmatched cohort identity: {identity}")
        seen.add(identity)
        sample = candidates[0]
        observed[sample, region[len(prefix):], side] += 1
        types[sample][label] += 1
    expected = Counter({
        (sample, parcel, side): n
        for sample, row in samples.items() for parcel, pair in row["parcels"].items()
        for side, n in zip(("L", "R"), pair) if n
    })
    if observed != expected:
        difference = (observed - expected) or (expected - observed)
        key = next(iter(difference))
        raise ValueError(f"ReMAP and Progress Manager differ for {' / '.join(key)}: "
                         f"ReMAP {observed[key]}, Progress Manager {expected[key]}")
    return types


def build_report(snapshot, cohort=None, *, sample=None):
    """Validate a saved Progress Manager CSV and optional exact ReMAP cohort."""
    text, snapshot_ref = _source(snapshot)
    samples, generated_at = _progress_rows(text)
    inputs = {"progress_manager": snapshot_ref}
    types = None
    if cohort is not None:
        text, inputs["remap_cohort"] = _source(cohort)
        types = _match_cohort(text, samples)
    if sample is not None and sample not in samples:
        raise ValueError(f"Sample {sample!r} is absent from the Progress Manager export")
    rows = [row for ident, row in samples.items() if sample is None or ident == sample]
    rows.sort(key=lambda row: (-row["atlas_insula"], row["animal"], row["sample"]))
    parcels = {}
    type_totals = Counter()
    for row in rows:
        row["left"] = sum(pair[0] for pair in row["parcels"].values())
        row["right"] = sum(pair[1] for pair in row["parcels"].values())
        for parcel, (left, right) in row["parcels"].items():
            pair = parcels.setdefault(parcel, [0, 0])
            pair[0] += left
            pair[1] += right
        if types is not None:
            row["types"] = dict(types[row["sample"]])
            type_totals.update(row["types"])
    selected = [r for r in rows if r["selected"] is not None]
    totals = {key: sum(r[key] for r in rows)
              for key in ("left", "right", "screened", "atlas_insula")}
    totals["selected"] = sum(r["selected"] for r in selected) if selected else None
    return {
        "schema": "remap.cohort_progress.v1", "remap_version": __version__,
        "inputs": inputs, "snapshot_generated_at": generated_at, "sample": sample,
        "rows": rows, "parcels": parcels, "types": dict(type_totals) if types is not None else None,
        "totals": totals, "selected_animals": len({r["animal"] for r in selected}),
    }


def _side_bars(ax, names, pairs):
    y = list(range(len(names)))
    lvals, rvals = zip(*pairs) if pairs else ([], [])
    ax.barh(y, lvals, height=.63, color=_SIDE_COLORS[0])
    ax.barh(y, rvals, left=lvals, height=.63, color=_SIDE_COLORS[1])
    for i, (left, right) in enumerate(pairs):
        ax.annotate(str(left + right), (left + right, i), xytext=(5, 0),
                    textcoords="offset points", va="center", color="#263745", fontsize=9)
    largest = max((l + r for l, r in pairs), default=0)
    ax.set(xlim=(0, max(largest * 1.14, 1)), ylim=(len(names) - .45, -.55),
           yticks=y, yticklabels=names, xlabel="Neurons")
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#e6eaee", linewidth=.7)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)


def make_figure(report):
    """Create the same Matplotlib figure for desktop and export."""
    try:
        from matplotlib.figure import Figure
        from matplotlib.patches import Patch
    except ImportError as exc:
        raise RuntimeError("Progress PNG export requires the ReMAP plots extra") from exc

    rows, totals = report["rows"], report["totals"]
    fig = Figure(figsize=(12, 4.9 + max(len(rows), 4) * .34), facecolor="white")
    grid = fig.add_gridspec(2, 2, left=.137, right=.95, top=.77, bottom=.155,
                            wspace=.47, hspace=.68, width_ratios=(1.28, 1),
                            height_ratios=(max(len(rows), 4), 6))
    fig.text(.065, .935, "Macaque insula cohort composition",
             fontsize=22, weight="bold", color="#172d3b")
    animal_count = len({row["animal"] for row in rows})
    fig.text(.065, .887, f"{totals['atlas_insula']:,} atlas-labeled neurons  ·  "
             f"{animal_count} {'animal' if animal_count == 1 else 'animals'}  ·  "
             f"{totals['left']:,} left / {totals['right']:,} right",
             fontsize=11, color="#455867")
    fig.legend(handles=[Patch(facecolor=color, label=f"{side} soma")
                        for color, side in zip(_SIDE_COLORS, ("Left", "Right"))],
               loc="upper right", bbox_to_anchor=(.95, .89), frameon=False, ncols=2)

    ax = fig.add_subplot(grid[0, 0])
    names = [f"{r['animal']} / {r['sample']}" for r in rows]
    _side_bars(ax, names, [(r["left"], r["right"]) for r in rows])
    ax.set_title("Atlas-insula neurons by animal / sample", loc="left", fontsize=11, pad=11)

    data = fig.add_subplot(grid[0, 1])
    data.set(xlim=(0, 1), ylim=ax.get_ylim())
    data.set_title("Progress Manager snapshot", loc="left", fontsize=11, pad=24)
    data.axis("off")
    for x, label in zip((.16, .50, .84), ("Screened", "Selected*", "ARM insula")):
        data.text(x, 1.01, label, transform=data.transAxes, ha="center",
                  weight="bold", color="#344959", fontsize=9)
    for y, row in enumerate(rows):
        if y % 2 == 0:
            data.axhspan(y - .46, y + .46, color="#edf2f5", zorder=0)
        for x, key in zip((.16, .50, .84), ("screened", "selected", "atlas_insula")):
            value = row[key]
            data.text(x, y, f"{value:,}" if value is not None else "—",
                      ha="center", va="center", color="#253947", fontsize=9)

    regions = sorted(report["parcels"], key=lambda p: (-sum(report["parcels"][p]), p))
    projection = report["types"]
    ax = fig.add_subplot(grid[1, 0] if projection else grid[1, :])
    _side_bars(ax, regions, [report["parcels"][p] for p in regions])
    ax.set_title("ARM level-6 soma parcels", loc="left", fontsize=11, pad=9)
    if projection:
        types = sorted(projection, key=lambda label: (-projection[label], label))
        ax = fig.add_subplot(grid[1, 1])
        _side_bars(ax, types, [(0, projection[label]) for label in types])
        for bar in ax.containers[1]:
            bar.set_facecolor("#56707f")
        ax.set_title("Recorded projection types", loc="left", fontsize=11, pad=9)
    historical = f"{totals['screened']:,} screened in this snapshot"
    if totals["selected"] is not None:
        n = report["selected_animals"]
        historical += f"  ·  {totals['selected']:,} historically selected across {n} {'animal' if n == 1 else 'animals'}"
    fig.text(.065, .089, historical, fontsize=9, weight="bold", color="#263745")
    fig.text(.065, .060, "*Selected is the historical selection column. A dash marks a blank entry.",
             fontsize=9, color="#455867")
    fig.text(.065, .034, f"Saved snapshot  {report['snapshot_generated_at']}",
             fontsize=9, color="#455867")
    return fig


def export_report(report, output, *, dpi=168):
    """Write a new PNG and its count and source receipt without clobbering output."""
    if not isinstance(dpi, int) or not 100 <= dpi <= 300:
        raise ValueError("DPI must be an integer from 100 to 300")
    path = Path(output).expanduser().resolve()
    if path.suffix.lower() != ".png":
        raise ValueError("Cohort progress output must end in .png")
    receipt = path.with_name(path.stem + "_receipt.json")
    if path.exists() or receipt.exists():
        raise FileExistsError(f"Choose a new output name: {path}")
    buffer = io.BytesIO()
    make_figure(report).savefig(buffer, format="png", dpi=dpi)
    image = buffer.getvalue()
    payload = dict(report, output=str(path), dpi=dpi, png_sha256=hashlib.sha256(image).hexdigest(),
                   renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with path.open("xb") as file:
            created.append(path)
            file.write(image)
        with receipt.open("x", encoding="utf-8") as file:
            created.append(receipt)
            file.write(text)
    except OSError:
        for item in created:
            item.unlink(missing_ok=True)
        raise
    return {"output": str(path), "receipt": str(receipt), "png_sha256": payload["png_sha256"]}



def configure_progress_parser(parser):
    """Register the saved Progress Manager command options."""
    parser.add_argument("--snapshot", required=True, type=Path, help="exported data_progress_table.csv")
    parser.add_argument("--cohort", type=Path, help="matching ReMAP regional measurement receipt JSON")
    parser.add_argument("--sample", help="show one exact fMOST sample after validating the snapshot")
    parser.add_argument("--output", type=Path, help="new PNG path, with an adjacent receipt")
    parser.add_argument("--dpi", type=int, default=168, help="PNG resolution from 100 to 300")
    parser.add_argument("--dry-run", action="store_true", help="validate the saved inputs and report counts")


def run_progress(args, *, build=build_report):
    """Validate a CLI request and return a plan or export result."""
    if args.output is None and not args.dry_run:
        raise ValueError("progress requires --output or --dry-run")
    if not 100 <= args.dpi <= 300:
        raise ValueError("--dpi must be from 100 to 300")
    if args.output is not None and args.output.suffix.lower() != ".png":
        raise ValueError("--output must end in .png")
    report = build(args.snapshot, args.cohort, sample=args.sample)
    if args.dry_run:
        return dict(report, output=str(args.output.resolve()) if args.output else None, dpi=args.dpi)
    return export_report(report, args.output, dpi=args.dpi)
