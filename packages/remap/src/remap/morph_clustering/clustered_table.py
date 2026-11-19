"""Evolve a neuron workbook with explicitly named exploratory cluster assignments.

Version: 0.2.2.dev2 (local/unreleased)
Last updated: 2026-11-18
Change history: ../../../CHANGELOG.md
- 2026-11-18: Assemble cohort Summary rows with per-row source hashes, original row numbers and inclusion.
- 2026-11-18: Explicit all-samples composite identity mode; single-sample behavior preserved.
- 2026-11-17: Add bounded, identity-checked candidate workbook export and readable candidate/provenance sheets; reject malformed and empty candidate columns.
Status: candidate
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from .. import __version__

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def evolve(source, output, sample, assignments, dry_run=False):
    """Join exact neuron stems in named assignment CSVs to one sample workbook."""
    source, output = Path(source), Path(output)
    if output.exists() or output.resolve() == source.resolve():
        raise ValueError("Output must be a new file distinct from the source")
    if not assignments:
        raise ValueError("At least one named assignment file is required")
    book = load_workbook(source)
    if "FNT candidates" in book or "FNT provenance" in book:
        raise ValueError("Source already has FNT candidate sheets")
    sheet = book["Summary"]
    headers = [c.value for c in sheet[1]]
    if headers.count("SampleID") != 1 or headers.count("NeuronID") != 1:
        raise ValueError("Summary requires unique SampleID and NeuronID columns")
    sample_col = headers.index("SampleID") + 1
    neuron_col = headers.index("NeuronID") + 1
    ids, source_identities = [], []
    for row in range(2, sheet.max_row + 1):
        s, n = sheet.cell(row, sample_col).value, sheet.cell(row, neuron_col).value
        if (sample is not None and str(s) != sample) or s is None or not isinstance(n, str) or not n.endswith(".swc"):
            raise ValueError(f"Unexpected identity at Summary row {row}")
        ids.append(n[:-4] if sample is not None else str(s) + "_" + n[:-4])
        source_identities.append((str(s), n))
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate neuron identities in Summary")
    parsed = []
    for name, path in assignments:
        if not name or any(name == old[0] for old in parsed):
            raise ValueError("Assignment names must be nonempty and unique")
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)):
                raise ValueError("Assignment CSV contains duplicate column names")
            columns = [c for c in fields if c.startswith("k_")]
            if not columns or "FNT_NeuronID" not in fields:
                raise ValueError("Assignment CSV requires FNT_NeuronID and k_ columns")
            if any(not re.fullmatch(r"k_[2-9][0-9]*|k_1[0-9]+", c) for c in columns):
                raise ValueError("Candidate columns must use k_<integer> with k >= 2")
            mapping = {}
            for record in reader:
                identity = record["FNT_NeuronID"]
                if identity in mapping or identity not in ids:
                    raise ValueError(f"Duplicate or unknown assignment identity {identity}")
                labels = [int(record[c]) for c in columns]
                if any(label < 1 or label > int(column[2:])
                       for label, column in zip(labels, columns)):
                    raise ValueError("Cluster labels must be between 1 and requested k")
                mapping[identity] = labels
        if not mapping:
            raise ValueError("Assignment CSV must contain scored neurons")
        parsed.append((name, Path(path), columns, mapping))
    identities = set(parsed[0][3])
    if any(set(item[3]) != identities for item in parsed):
        raise ValueError("Assignment files must have identical identity sets")
    plan = {"version": __version__, "source": str(source), "source_sha256": digest(source), "sample": sample,
            "rows": len(ids), "scored": len(identities), "unscored": len(ids)-len(identities),
            "assignments": [{"name": n, "path": str(p), "sha256": digest(p), "columns": c}
                            for n, p, c, _ in parsed],
            "output": str(output), "status": "exploratory candidate"}
    if dry_run:
        book.close()
        return plan
    candidate = book.create_sheet("FNT candidates")
    candidate.append((["NeuronID", "FNT coverage"] if sample is not None else ["SampleID", "NeuronID", "FNT coverage"]) +
                     [f"{name} {column}" for name, _, columns, _ in parsed for column in columns])
    for identity, (source_sample, source_neuron) in zip(ids, source_identities):
        prefix = [source_neuron] if sample is not None else [source_sample, source_neuron]
        candidate.append(prefix + ["scored" if identity in identities else "unscored"] +
                         [value for _, _, columns, mapping in parsed
                          for value in mapping.get(identity, [None] * len(columns))])
    candidate.column_dimensions["A"].width = 16
    candidate.column_dimensions["B"].width = 18
    for column in range(3, candidate.max_column + 1):
        candidate.column_dimensions[get_column_letter(column)].width = 30
    for cell in candidate[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="24566C")
    candidate.freeze_panes = "C2"
    candidate.auto_filter.ref = candidate.dimensions
    provenance = book.create_sheet("FNT provenance", 0)
    for key in ("version", "status", "sample", "source", "source_sha256", "rows", "scored", "unscored"):
        provenance.append([key, plan[key]])
    for assignment in plan["assignments"]:
        provenance.append([assignment["name"] + " path", assignment["path"]])
        provenance.append([assignment["name"] + " SHA-256", assignment["sha256"]])
        provenance.append([assignment["name"] + " columns", ", ".join(assignment["columns"])])
    provenance.column_dimensions["A"].width = 25
    provenance.column_dimensions["B"].width = 110
    output.parent.mkdir(parents=True, exist_ok=True)
    stream = output.open("xb")
    try:
        with stream:
            book.save(stream)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        book.close()
    return plan


def assemble_cohort(spec, output, inclusion_by_id):
    """Assemble source Summary rows without rewriting source workbooks.

    Keep source paths, hashes and original row numbers on every row. Original
    workbooks remain the authority for their other worksheets and formatting.
    """
    import pandas as pd
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    frames, sources = [], []
    for entry in spec:
        source = Path(entry["path"])
        fingerprint = digest(source)
        frame = pd.read_excel(source, sheet_name="Summary", dtype={"NeuronID": str, "SampleID": str})
        if not frame.SampleID.eq(str(entry["sample"])).all():
            raise ValueError("Source SampleID contradicts table binding")
        if frame.NeuronID.isna().any() or not frame.NeuronID.str.endswith(".swc").all():
            raise ValueError("Invalid source neuron ID")
        identities = frame.SampleID + "_" + frame.NeuronID.str.removesuffix(".swc")
        frame["Cohort_FNT_ID"] = identities
        frame["Cohort_AnimalID"] = str(entry["animal"])
        frame["Cohort_Inclusion"] = identities.map(inclusion_by_id).fillna("outside_selected_cohort")
        frame["Source_Workbook"] = str(source)
        frame["Source_SHA256"] = fingerprint
        frame["Source_Summary_Row"] = range(2, len(frame)+2)
        frames.append(frame)
        sources.append({**entry, "sha256": fingerprint, "rows": len(frame)})
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if combined.Cohort_FNT_ID.duplicated().any():
        raise ValueError("Overlapping composite source identities")
    if not set(inclusion_by_id).issubset(combined.Cohort_FNT_ID):
        raise ValueError("Cohort ledger identity absent from source Summary rows")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            combined.to_excel(writer, sheet_name="Summary", index=False)
            pd.DataFrame(sources).to_excel(writer, sheet_name="Source workbooks", index=False)
    for source in sources:
        if digest(Path(source["path"])) != source["sha256"]:
            raise ValueError("Source workbook changed during assembly")
    return {"version": __version__, "output": str(output), "sha256": digest(output),
            "rows": len(combined), "sources": sources,
            "status": "source-derived cohort table; original workbooks preserved externally"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--sample")
    scope.add_argument("--all-samples", action="store_true")
    parser.add_argument("--assignment", nargs=2, action="append", metavar=("NAME", "CSV"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(evolve(args.source, args.output, args.sample, args.assignment, args.dry_run), indent=2))


if __name__ == "__main__":
    main()