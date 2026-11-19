"""Neuron table for one sample.

This module measures one loaded neuron and writes the sample workbook.
``NeuronTracer`` in ``neuron_swc.py`` is the single-neuron load and shape-plot
unit. Hierarchy stays beside this module. Laterality is applied here before
the workbook is written.

Version: 0.1.0.dev42 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-09: Folded the small region workers into one workbook module.
- 2026-11-10: Laterality is applied before save. Soma side columns are prefix_derived and location_derived.
- 2026-11-10: SWC shape plots are off unless montage or each. Hierarchy fallback can use the designated atlas key.
Status: candidate
"""
from __future__ import annotations

import ast
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import math
from numbers import Real
import os
from pathlib import Path
import re
from typing import List, Optional, Union

import nibabel as nib
import numpy as np
import pandas as pd

from .hierarchy import (
    RegionHierarchy,
    DualHierarchyTable,
    add_soma_hierarchy_column,
    add_projection_length_hierarchy,
    add_projection_hierarchy,
    resolve_to_level,
)
from .neuron_swc import NeuronTracer


# These are the cortical/manual soma prefixes used by the insula pipeline.
# Keep SL_/SR_ explicit: cortical Pi and subcortical pineal Pi are distinct.
# ARM-insula membership is broader than Ial; see INSULA_NOTE.md.
SOMA_REGION_PREFIXES = ("CL_", "CR_", "L-", "R-", "L_", "R_")
EXPLICIT_UNKNOWN_LABELS = frozenset({"UNKNOWN", "_UNMAPPED", "UNMAPPED", "INSULAUNKNOWN"})


def strip_region_prefix(value):
    """Drop one declared side prefix; preserve the remaining anatomical token."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    for prefix in SOMA_REGION_PREFIXES:
        if text.upper().startswith(prefix):
            return text[len(prefix):]
    return text


def normalize_region_label(value):
    """Canonical historical/manual label; numeric anatomy is unchanged."""
    return strip_region_prefix(value).upper().strip()


def is_explicit_unknown_label(value):
    """Recognize explicit Unknown sentinels, including the atlas ``Unknown_0``.

    Blank/absent metadata is not an explicit atlas Unknown assignment.
    """
    label = normalize_region_label(value)
    return label in EXPLICIT_UNKNOWN_LABELS or bool(re.fullmatch(r"UNKNOWN_\d+", label))


class OutputManager:
    """One animal folder: neuron_table, report/report_plots, and swc_plots."""

    def __init__(
        self,
        base_path: str = None,
        sample_id: str = None,
        create_timestamp: bool = True,
    ):
        self.base_path = Path(base_path or "./output")
        self.sample_id = sample_id or "analysis"
        self.output_dir = self.base_path / self.sample_id
        self.tables_dir = self.output_dir / "neuron_table"
        self.reports_dir = self.output_dir / "report"
        self.plots_dir = self.reports_dir / "report_plots"
        self.swc_plots_dir = self.output_dir / "swc_plots"
        self.debug_dir = self.reports_dir / "debug"
        self._created = False

    def create_dirs(self):
        if self._created:
            return
        for d in (
            self.tables_dir,
            self.reports_dir,
            self.plots_dir,
            self.swc_plots_dir,
            self.debug_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        self._created = True
        print(f"[OUTPUT] Created: {self.output_dir}")

    def get_plot_path(self, name: str, ext: str = "png") -> Path:
        self.create_dirs()
        return self.plots_dir / f"{name}.{ext}"

    def get_swc_plot_path(self, name: str, ext: str = "png") -> Path:
        self.create_dirs()
        return self.swc_plots_dir / f"{name}.{ext}"

    def get_table_path(self, name: str, ext: str = "xlsx") -> Path:
        self.create_dirs()
        return self.tables_dir / f"{name}.{ext}"

    def get_report_path(self, name: str, ext: str = "txt") -> Path:
        self.create_dirs()
        return self.reports_dir / f"{name}.{ext}"

    def get_debug_path(self, name: str, ext: str = "png") -> Path:
        self.create_dirs()
        return self.debug_dir / f"{name}.{ext}"

    def print_summary(self):
        print("\n" + "=" * 60)
        print("OUTPUT SUMMARY")
        print("=" * 60)
        print(f"Location: {self.output_dir}")
        print(f"  Neuron table: {self.tables_dir}")
        print(f"  Report:       {self.reports_dir}")
        print(f"  Report plots: {self.plots_dir}")
        print(f"  SWC plots:    {self.swc_plots_dir}")
        print("=" * 60)


def terminal_target_status(value) -> str:
    """Reporting status of one target, without accepting/rejecting atlas anatomy.

    ``known`` means a nonempty literal label without an explicit sentinel. It
    does not verify atlas membership or biological terminal identity. Exact
    control tokens avoid rejecting anatomical names containing ``Unknown``.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return "absent"
    if not isinstance(value, str):
        if isinstance(value, (float, np.floating)) and np.isnan(value):
            return "absent"
        return "invalid"
    token = normalize_region_label(value)
    # Subcortical prefixes are stripped only to recognize control tokens;
    # literal anatomical labels (including SL_Pi versus CL_Pi) are unchanged.
    if token.startswith(("SL_", "SR_")):
        token = token[3:]
    if token in {"", "NONE", "NULL", "NAN"}:
        return "absent"
    if token == "OUT_OF_BOUNDS":
        return "outside"
    if token in {"_UNMAPPED", "UNMAPPED"}:
        return "unmapped"
    if is_explicit_unknown_label(token):
        return "unknown"
    return "known"


def is_known_terminal_target(value) -> bool:
    """True for a usable literal target label under the reporting contract."""
    return terminal_target_status(value) == "known"


def terminal_target_region_counts(region_lists, include_unresolved=False):
    """Count parsed entries without explode's phantom entry for empty lists.

    Retain literal string labels. Absent/invalid values receive display-only
    placeholders when all entries are requested; they never become anatomy.
    """
    entries = []
    for regions in region_lists:
        for value in regions:
            status = terminal_target_status(value)
            if status == "known" or include_unresolved:
                label = value if isinstance(value, str) and value.strip() else f"<{status} target>"
                entries.append(label)
    return pd.Series(entries, dtype=object).value_counts()


def parse_terminal_regions(x) -> list:
    """Parse Terminal_Regions from various formats to unique-order list."""
    if isinstance(x, (list, tuple)):
        return _dedupe(x)
    if isinstance(x, str):
        try:
            if x.startswith("[") and x.endswith("]"):
                return _dedupe(ast.literal_eval(x))
            if "," in x:
                parts = [p.strip().strip("'\"") for p in x.split(",")]
                return _dedupe(parts)
            return [x.strip().strip("'\"")]
        except Exception:
            return [x]
    return []


def _dedupe(seq) -> list:
    seen, out = set(), []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_projection_lengths(value) -> dict:
    """Read a literal length mapping; missing/invalid values are not zeros."""
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError("Projection lengths must be a literal dictionary") from exc
    if not isinstance(value, dict):
        raise ValueError("Missing or invalid projection-length dictionary")
    for region, length in value.items():
        if not isinstance(region, str) or not region.strip():
            raise ValueError("Projection targets must be nonempty literal labels")
        if isinstance(length, (bool, np.bool_)) or not isinstance(length, Real) or not np.isfinite(length) or length < 0:
            raise ValueError(f"Projection length must be finite and nonnegative: {region}")
    return value.copy()


def normalize_region_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Decode saved cells before numeric consumers can silently discard them."""
    df = df.copy()
    for column in df.columns:
        if column in {"Region_projection_length", "Ipsilateral_Projection_Length",
                      "Contralateral_Projection_Length", "Unknown_Laterality_Projection_Length"} or column.startswith("Region_Projection_Length_"):
            df[column] = df[column].apply(parse_projection_lengths)
        elif column == "Terminal_Regions" or column.startswith("Proj_"):
            df[column] = df[column].apply(parse_terminal_regions)
    return df


def projection_column_names(regions, atlas_regions=()) -> dict:
    """Remove hemisphere while preserving colliding cortical/subcortical names.

    For example, cortical parainsula and subcortical pineal gland cannot both
    become ``Pi``. Use all declared atlas labels when available so naming is
    stable even when only one homonym occurs in the selected cohort.
    """
    regions = list(regions)
    domains = {}
    for region in regions + list(atlas_regions):
        if isinstance(region, str) and region.startswith(("CL_", "CR_", "SL_", "SR_")):
            domains.setdefault(region[3:], set()).add(region[0])
    names = {}
    for region in regions:
        if region.startswith(("CL_", "CR_", "SL_", "SR_")):
            base = region[3:]
            names[region] = f"{region[0]}_{base}" if len(domains[base]) > 1 else base
        else:
            names[region] = region
    reverse = {}
    for region, column in names.items():
        # Opposite hemispheres of one anatomical region intentionally share a
        # column. Generated names must not collide with a literal input name.
        identity = (region[0], region[3:]) if region.startswith(("CL_", "CR_", "SL_", "SR_")) else (None, region)
        if column in reverse and reverse[column] != identity:
            raise ValueError(f"Ambiguous projection column name: {column}")
        reverse[column] = identity
    return names


def _validate_neuron_identity(frame, allow_repeated_records=False):
    keys = (["SampleID", "NeuronID"] if "SampleID" in frame else
            ["NeuronUID"] if "NeuronUID" in frame else ["NeuronID"])
    if any(key not in frame for key in keys) or frame[keys].isna().any().any():
        raise ValueError("Missing neuron identity")
    if "NeuronID" not in frame or not frame.NeuronID.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError("NeuronID must be present literal text")
    if any(frame[key].astype(str).str.strip().eq("").any() for key in keys) or (not allow_repeated_records and frame.duplicated(keys).any()):
        raise ValueError("Missing or duplicate exact neuron identity")
    if "NeuronUID" in frame:
        if not frame.NeuronUID.map(lambda value: isinstance(value, str) and "::" in value and bool(value.split("::", 1)[0].strip())).all():
            raise ValueError("NeuronUID must encode SampleID::NeuronID")
        if not frame.NeuronUID.str.split("::", n=1).str[1].eq(frame.NeuronID).all():
            raise ValueError("NeuronUID disagrees with NeuronID")
        if "SampleID" in frame:
            tokens = frame.SampleID.map(lambda value: str(int(value)) if isinstance(value, Real) and not isinstance(value, (bool, np.bool_)) and np.isfinite(value) and float(value).is_integer() else str(value).strip())
            if not frame.NeuronUID.eq(tokens + "::" + frame.NeuronID).all():
                raise ValueError("NeuronUID disagrees with SampleID/NeuronID")
        if not allow_repeated_records and frame.NeuronUID.duplicated().any():
            raise ValueError("Duplicate NeuronUID")
    return keys


def neuron_metadata(frame):
    """Preserve exact subject identity when bare neuron IDs are not unique."""
    _validate_neuron_identity(frame)
    columns = ["NeuronID", "Neuron_Type"]
    if "SampleID" in frame and (frame.SampleID.nunique() > 1 or "NeuronUID" in frame):
        columns.insert(0, "SampleID")
    if "NeuronUID" in frame:
        columns.insert(0, "NeuronUID")
    result = frame.reindex(columns=columns).reset_index(drop=True)
    if "Neuron_Type" not in frame:
        result["Neuron_Type"] = ""
    return result


def _join_keys(summary, sheet, name):
    _validate_neuron_identity(summary)
    _validate_neuron_identity(sheet, allow_repeated_records=True)
    if "SampleID" in summary and "SampleID" in sheet:
        keys = ["SampleID", "NeuronID"]
    elif "NeuronUID" in summary and "NeuronUID" in sheet:
        keys = ["NeuronUID"]
    else:
        keys = ["NeuronID"]
    if any(key not in sheet or key not in summary for key in keys):
        raise ValueError(f"{name} lacks exact neuron identity")
    if summary[keys].isna().any().any() or sheet[keys].isna().any().any() or summary.duplicated(keys).any():
        raise ValueError(f"{name} has missing or ambiguous neuron identities")
    return keys


def _aligned_sheet(summary, sheet, name):
    keys = _join_keys(summary, sheet, name)
    if sheet.duplicated(keys).any():
        raise ValueError(f"{name} has missing or ambiguous neuron identities")
    left = summary[keys].apply(tuple, axis=1).tolist()
    right = sheet[keys].apply(tuple, axis=1).tolist()
    if set(left) != set(right):
        raise ValueError(f"{name} neuron membership differs from Summary")
    positions = {key: index for index, key in enumerate(right)}
    aligned = sheet.iloc[[positions[key] for key in left]].reset_index(drop=True)
    if "Neuron_Type" in summary and "Neuron_Type" in aligned and not summary.Neuron_Type.reset_index(drop=True).fillna("").equals(aligned.Neuron_Type.fillna("")):
        raise ValueError(f"{name} neuron types differ from Summary")
    return aligned


def _long_sheet_records(summary, sheet, name, record_columns):
    """Join repeated records without conflating matching IDs across animals."""
    if sheet.empty:
        return [[] for _ in range(len(summary))]
    keys = _join_keys(summary, sheet, name)
    if not set(record_columns) <= set(sheet):
        raise ValueError(f"{name} lacks required record columns")
    allowed = set(summary[keys].apply(tuple, axis=1))
    grouped = {}
    for _, row in sheet.iterrows():
        key = tuple(row[column] for column in keys)
        if key not in allowed:
            raise ValueError(f"{name} contains a neuron absent from Summary")
        grouped.setdefault(key, []).append({column: row[column] for column in record_columns})
    return [grouped.get(key, []) for key in summary[keys].apply(tuple, axis=1)]


def load_processed_df(path) -> pd.DataFrame:
    """Load literal-cell tables or reconstruct a lossless multi-sheet export.

    Absolute projection labels are required: hemisphere-stripped split sheets
    cannot reconstruct anatomical identity or unknown-side lengths.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return normalize_region_dataframe(pd.read_csv(path))
    if path.suffix.lower() != ".xlsx":
        raise ValueError("File must be .xlsx or .csv")
    sheets = pd.read_excel(path, sheet_name=None)
    summary = sheets.get("Summary", next(iter(sheets.values()))).copy()
    _validate_neuron_identity(summary)
    if not any(column in summary for column in ("Region_projection_length", "Region_Projection_Length_finest")) and "Projection_Length_all" not in sheets and any(name.startswith("Projection_Length") for name in sheets):
        raise ValueError("Split-only workbook cannot recover absolute projection lengths; use its source analysis table")
    if "Region_projection_length" not in summary and "Projection_Length_all" in sheets:
        lengths = _aligned_sheet(summary, sheets["Projection_Length_all"], "Projection_Length_all")
        metadata = {"SampleID", "NeuronID", "NeuronUID", "Neuron_Type", "Length_Unit"}
        targets = [column for column in lengths if column not in metadata]
        summary["Region_projection_length"] = [parse_projection_lengths({target: row[target] for target in targets if row[target] != 0})
                                                for _, row in lengths.iterrows()]
    if "Terminal_Regions" not in summary and "Terminal_Sites" in sheets:
        records = _long_sheet_records(summary, sheets["Terminal_Sites"], "Terminal_Sites", ["Terminal_Region"])
        summary["Terminal_Regions"] = [[record["Terminal_Region"] for record in row] for row in records]
        if "Terminal_Count" in summary and not summary.Terminal_Count.eq(summary.Terminal_Regions.apply(len)).all():
            raise ValueError("Terminal_Sites target counts differ from Summary")
    if "Outlier_Details" not in summary and "Outliers" in sheets:
        records = _long_sheet_records(summary, sheets["Outliers"], "Outliers", ["Outlier_Type", "Region", "Voxel_X", "Voxel_Y", "Voxel_Z"])
        summary["Outlier_Details"] = [[{"type": record["Outlier_Type"], "region": record["Region"],
                                        "coords": tuple(record[column] for column in ("Voxel_X", "Voxel_Y", "Voxel_Z"))}
                                       for record in row] for row in records]
        if "Outlier_Count" in summary and not summary.Outlier_Count.eq(summary.Outlier_Details.apply(len)).all():
            raise ValueError("Outliers counts differ from Summary")
    if "Soma_Hierarchy" in sheets and not sheets["Soma_Hierarchy"].empty:
        hierarchy = _aligned_sheet(summary, sheets["Soma_Hierarchy"], "Soma_Hierarchy")
        for column in hierarchy:
            if column.startswith("L") and column[1:].isdigit():
                target = "Soma_Level_" + column[1:]
                values = pd.Series(hierarchy[column].values, index=summary.index)
                if target in summary:
                    conflicts = summary[target].notna() & values.notna() & summary[target].ne(values)
                    if conflicts.any():
                        raise ValueError(f"Soma_Hierarchy conflicts with Summary for {target}")
                    summary[target] = summary[target].fillna(values)
                else:
                    summary[target] = values
    return normalize_region_dataframe(summary)


class LateralityParser:
    # Refined soma labels use L-IDM / R-IDD5 (and legacy L_ / R_).
    # Keep the same explicit-side interpretation in every consumer.
    LEFT_PREFIXES = ("CL_", "SL_", "L-", "L_")
    RIGHT_PREFIXES = ("CR_", "SR_", "R-", "R_")
    @staticmethod
    def get_side(region_name: str) -> str:
        if not isinstance(region_name, str):
            return "Unknown"
        s = str(region_name)
        if any(s.startswith(p) for p in LateralityParser.LEFT_PREFIXES):
            return "L"
        if any(s.startswith(p) for p in LateralityParser.RIGHT_PREFIXES):
            return "R"
        return "Unknown"
    @staticmethod
    def classify_with_soma_side(soma_side: str, terminal_region: str) -> str:
        if not is_known_terminal_target(terminal_region):
            return "Unknown"
        term_side = LateralityParser.get_side(terminal_region)
        if not isinstance(soma_side, str) or soma_side not in ("L", "R") or term_side == "Unknown":
            return "Unknown"
        return "Ipsilateral" if soma_side == term_side else "Contralateral"
    @staticmethod
    def parse_terminal_list_with_soma_side(
        soma_side: str, terminal_regions: list
    ) -> List[Dict[str, str]]:
        if not isinstance(terminal_regions, (list, tuple)):
            terminal_regions = []
        results = []
        for r in terminal_regions:
            results.append(
                {
                    "region": r,
                    "side": LateralityParser.get_side(r),
                    "laterality": LateralityParser.classify_with_soma_side(soma_side, r),
                }
            )
        return results
    @staticmethod
    def split_projection_lengths_with_soma_side(
        soma_side: str, projection_dict: dict
    ) -> Tuple[dict, dict, dict]:
        projection_dict = parse_projection_lengths(projection_dict)
        ipsi, contra, unk = {}, {}, {}
        for region, length in projection_dict.items():
            lat = LateralityParser.classify_with_soma_side(soma_side, region)
            if lat == "Ipsilateral":
                ipsi[region] = length
            elif lat == "Contralateral":
                contra[region] = length
            else:
                unk[region] = length
        return ipsi, contra, unk


def add_laterality_columns(
    df: pd.DataFrame,
    soma_col: str = "Soma_Region",
    terminal_col: str = "Terminal_Regions",
    length_col: str = None,
    soma_x_col: str = "Soma_NII_X",
    soma_side_reference: Optional[pd.Series] = None,
    soma_side_reference_source: Optional[str] = None,
) -> pd.DataFrame:
    """Classify explicit label sides, optionally using a declared reference.
    Unknown labels stay unknown without an independently supplied side reference.
    Sample coordinate medians are not a hemisphere reference. ``soma_x_col``
    remains accepted for compatibility but does not determine side.
    """
    df = df.copy()
    P = LateralityParser
    if length_col is None:
        for candidate in ("Region_Projection_Length_finest", "Region_projection_length"):
            if candidate in df.columns:
                length_col = candidate
                break
    # Prefix side from the soma label; location side from the hemisphere mask.
    df["prefix_derived"] = df[soma_col].apply(P.get_side)
    reference = pd.Series("Unknown", index=df.index, dtype=object)
    if soma_side_reference is not None:
        if not soma_side_reference_source or not soma_side_reference_source.strip():
            raise ValueError("A soma-side reference requires a provenance source")
        if not isinstance(soma_side_reference, pd.Series) or not soma_side_reference.index.equals(df.index):
            raise ValueError("Soma-side reference must be a Series with the exact dataframe index")
        if not soma_side_reference.isin(["L", "R", "Unknown"]).all():
            raise ValueError("Soma-side reference values must be L, R, or Unknown")
        reference = soma_side_reference.copy()
    # Retained legacy diagnostic column; no coordinate-derived assignment.
    df["Soma_Side_Coord"] = "Unknown"
    df["location_derived"] = reference
    df["Soma_Side_Reference_Source"] = soma_side_reference_source
    conflict = (
        df["prefix_derived"].isin(["L", "R"])
        & reference.isin(["L", "R"])
        & df["prefix_derived"].ne(reference)
    )
    df["Soma_Side_Conflict"] = conflict
    df["Soma_Side"] = df["prefix_derived"]
    use_location = df["Soma_Side"].eq("Unknown") & reference.isin(["L", "R"])
    df.loc[use_location, "Soma_Side"] = reference.loc[use_location]
    df.loc[conflict, "Soma_Side"] = "Unknown"
    df["Terminal_Laterality"] = df.apply(
        lambda row: P.parse_terminal_list_with_soma_side(row["Soma_Side"], row[terminal_col]),
        axis=1,
    )
    df["N_Ipsilateral"] = df["Terminal_Laterality"].apply(
        lambda x: sum(1 for t in x if t["laterality"] == "Ipsilateral")
    )
    df["N_Contralateral"] = df["Terminal_Laterality"].apply(
        lambda x: sum(1 for t in x if t["laterality"] == "Contralateral")
    )
    df["N_Laterality_Unknown"] = df["Terminal_Laterality"].apply(
        lambda x: sum(1 for t in x if t["laterality"] == "Unknown")
    )
    df["Ipsilateral_Regions"] = df["Terminal_Laterality"].apply(
        lambda x: list(
            dict.fromkeys(t["region"] for t in x if t["laterality"] == "Ipsilateral")
        )
    )
    df["Contralateral_Regions"] = df["Terminal_Laterality"].apply(
        lambda x: list(
            dict.fromkeys(t["region"] for t in x if t["laterality"] == "Contralateral")
        )
    )
    if length_col and length_col in df.columns:
        splits = df.apply(
            lambda row: P.split_projection_lengths_with_soma_side(row["Soma_Side"], row[length_col]),
            axis=1,
        )
        df["Ipsilateral_Projection_Length"] = splits.apply(lambda x: x[0])
        df["Contralateral_Projection_Length"] = splits.apply(lambda x: x[1])
        df["Unknown_Laterality_Projection_Length"] = splits.apply(lambda x: x[2])
        df["Total_Ipsilateral_Length"] = df["Ipsilateral_Projection_Length"].apply(
            lambda d: sum(d.values()) if d else 0.0
        )
        df["Total_Contralateral_Length"] = df["Contralateral_Projection_Length"].apply(
            lambda d: sum(d.values()) if d else 0.0
        )
        df["Total_Unknown_Laterality_Length"] = df[
            "Unknown_Laterality_Projection_Length"
        ].apply(lambda d: sum(d.values()) if d else 0.0)
        def _lat_idx(row):
            denom = row["Total_Ipsilateral_Length"] + row["Total_Contralateral_Length"]
            if denom == 0:
                return None
            return round(row["Total_Contralateral_Length"] / denom, 4)
        df["Laterality_Index"] = df.apply(_lat_idx, axis=1)
    else:
        print(
            "[LATERALITY] No projection-length column — length columns skipped."
        )
    n = len(df)
    n_ipsi = (df["N_Ipsilateral"] > 0).sum()
    n_contra = (df["N_Contralateral"] > 0).sum()
    n_location = int(use_location.sum())
    print(
        f"[LATERALITY] {n} neurons: "
        f"{n_ipsi} with ipsi targets, {n_contra} with contra targets "
        f"(location_derived soma side: {n_location}; conflicts: {int(conflict.sum())})"
    )
    return df



class NeuronClassifier:
    def __init__(self, atlas_table: pd.DataFrame):
        try:
            ids = pd.to_numeric(atlas_table["Index"], errors="coerce")
        except KeyError:
            ids = pd.to_numeric(atlas_table.iloc[:, 0], errors="coerce")
        self.name_to_id = dict(zip(atlas_table["Abbreviation"], ids))
        if "Full_Name" in atlas_table.columns:
            self.name_to_id.update(dict(zip(atlas_table["Full_Name"], ids)))

    def _get_detailed_category(self, region_identifier: str) -> str:
        rid = self.name_to_id.get(region_identifier)
        if rid is None:
            return "Other"
        rid = int(rid)
        if (1169 <= rid <= 1325) or (1669 <= rid <= 1825):
            return "PT_Target"
        if (1083 <= rid <= 1107) or (1583 <= rid <= 1607):
            return "PT_Target"
        if (1111 <= rid <= 1168) or (1611 <= rid <= 1668):
            return "Thalamus"
        if (1051 <= rid <= 1061) or (1551 <= rid <= 1561):
            return "Striatum"
        if 1 <= rid <= 500:
            return "Cortex_L"
        if 501 <= rid <= 1000:
            return "Cortex_R"
        return "Other"

    def classify_single_neuron(self, terminal_list: list, soma_region: str, soma_side=None) -> str:
        if soma_side is None:
            soma_side = LateralityParser.get_side(soma_region)
        is_PT = is_CT = has_striatum = has_contra = has_ipsi = False
        for t_name in terminal_list:
            cat = self._get_detailed_category(t_name)
            if cat == "PT_Target":
                is_PT = True
            elif cat == "Thalamus":
                is_CT = True
            elif cat == "Striatum":
                has_striatum = True
            elif cat == "Cortex_L":
                if soma_side == "L":
                    has_ipsi = True
                elif soma_side == "R":
                    has_contra = True
            elif cat == "Cortex_R":
                if soma_side == "R":
                    has_ipsi = True
                elif soma_side == "L":
                    has_contra = True
        if is_PT:
            return "PT"
        if is_CT:
            return "CT"
        if has_striatum:
            return "ITs"
        if has_contra:
            return "ITc"
        if has_ipsi:
            return "ITi"
        return "Unclassified"


class AtlasHemisphereReference:
    def __init__(self, mask, atlas, atlas_table, source):
        if mask.ndim != 3 or atlas.shape != mask.shape:
            raise ValueError("Hemisphere reference and selected atlas must share a 3D grid")
        if not source or not str(source).strip():
            raise ValueError("Hemisphere reference requires source provenance")
        if not np.isfinite(mask).all() or not np.equal(mask, np.rint(mask)).all():
            raise ValueError("Hemisphere mask values must be finite integers")
        if atlas_table.Index.duplicated().any():
            raise ValueError("Atlas label indices must be unique")
        if not np.isfinite(atlas).all() or not np.equal(atlas, np.rint(atlas)).all() or atlas.min() < 0:
            raise ValueError("Atlas values must be finite nonnegative integers")
        codes = np.zeros(int(atlas.max()) + 1, dtype=np.uint8)
        for _, row in atlas_table.iterrows():
            index = int(row.Index)
            if 0 <= index < len(codes):
                codes[index] = {"L": 1, "R": 2, "Unknown": 0}[LateralityParser.get_side(row.Abbreviation)]
        sides = codes[atlas.astype(int)]
        self.value_to_side = {}
        self.contingency = {}
        for value in np.unique(mask):
            if value == 0:
                continue
            counts = {side: int(np.count_nonzero((mask == value) & (sides == code)))
                      for side, code in (("L", 1), ("R", 2))}
            if min(counts.values()) or not max(counts.values()):
                raise ValueError(f"Hemisphere mask conflicts with declared atlas labels: {value}: {counts}")
            self.value_to_side[int(value)] = max(counts, key=counts.get)
            self.contingency[int(value)] = counts
        if set(self.value_to_side.values()) != {"L", "R"}:
            raise ValueError("Reference must independently identify both hemispheres")
        self.mask = mask
        self.source = str(source)

    @classmethod
    def from_files(cls, mask_path, atlas_path, key_path, level=6):
        mask_img, atlas_img = nib.load(mask_path), nib.load(atlas_path)
        if mask_img.shape != atlas_img.shape[:3] or not np.allclose(mask_img.affine, atlas_img.affine, rtol=0, atol=1e-7):
            raise ValueError("Hemisphere mask and atlas shape/affine mismatch")
        atlas = np.asanyarray(atlas_img.dataobj)
        if atlas.ndim == 5 and atlas.shape[3] == 1 and 1 <= level <= atlas.shape[4]:
            atlas = atlas[..., 0, level - 1]
        elif atlas.ndim != 3:
            raise ValueError("Unsupported atlas dimensions or hierarchy level")
        sources = []
        for path in (mask_path, atlas_path, key_path):
            path = Path(path)
            sources.append(f"{path}:sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")
        return cls(np.asanyarray(mask_img.dataobj), atlas, pd.read_csv(key_path, sep="\t"), " | ".join(sources))

    def sample(self, xyz):
        xyz = np.asarray(xyz, dtype=float)
        if xyz.shape != (3,) or not np.isfinite(xyz).all():
            raise ValueError("Soma reference lookup requires finite XYZ atlas voxel coordinates")
        voxel = np.rint(xyz).astype(int)
        if not all(0 <= voxel[d] < self.mask.shape[d] for d in range(3)):
            return "Unknown"
        return self.value_to_side.get(int(self.mask[tuple(voxel)]), "Unknown")


def _plot(name, *args, **kwargs):
    from . import overview_plots
    return getattr(overview_plots, name)(*args, **kwargs)


class _LazyPyplot:
    def __getattr__(self, name):
        import matplotlib.pyplot as pyplot
        return getattr(pyplot, name)


plt = _LazyPyplot()


def _integer(token: str, field: str, location: str) -> int:
    """Accept integer-valued numeric notation without rounding identifiers."""
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise ValueError(f"{location}: {field} must be an integer") from exc
    if not value.is_finite() or value != value.to_integral_value():
        raise ValueError(f"{location}: {field} must be a finite integer")
    return int(value)


def parse_swc(text: str, source: str = "SWC") -> list[tuple]:
    """Return validated ``(id, type, x, y, z, radius, parent)`` rows.

    Rows may be unsorted and use integer-valued decimal/scientific notation.
    Blank/comment lines and trailing comments are allowed. Extra columns are
    left to SWC extensions; only the seven standard fields drive traversal.
    Each non-root parent must exist, and every node must reach the one root.
    """
    if not isinstance(text, str):
        raise ValueError(f"{source}: SWC data must be text")

    rows = []
    parents = {}
    roots = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        location = f"{source}, line {line_number}"
        if len(fields) < 7:
            raise ValueError(f"{location}: expected at least 7 SWC columns")
        node_id = _integer(fields[0], "node ID", location)
        node_type = _integer(fields[1], "node type", location)
        parent = _integer(fields[6], "parent ID", location)
        if node_id <= 0:
            raise ValueError(f"{location}: node ID must be positive")
        if node_id in parents:
            raise ValueError(f"{location}: duplicate node ID {node_id}")
        if node_type < 0:
            raise ValueError(f"{location}: node type must be nonnegative")
        if parent != -1 and parent <= 0:
            raise ValueError(f"{location}: parent ID must be -1 or positive")
        try:
            coordinates = tuple(float(value) for value in fields[2:6])
        except ValueError as exc:
            raise ValueError(f"{location}: coordinates and radius must be numeric") from exc
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError(f"{location}: coordinates and radius must be finite")
        if coordinates[3] < 0:
            raise ValueError(f"{location}: radius must be nonnegative")
        rows.append((node_id, node_type, *coordinates, parent))
        parents[node_id] = parent
        if parent == -1:
            roots.append(node_id)

    if len(roots) != 1:
        raise ValueError(f"{source}: expected exactly one root (parent -1), found {len(roots)}")
    for node_id, parent in parents.items():
        if parent != -1 and parent not in parents:
            raise ValueError(f"{source}: node {node_id} references missing parent {parent}")

    complete = set()
    for start in parents:
        path = []
        active = set()
        node_id = start
        while node_id != -1 and node_id not in complete:
            if node_id in active:
                raise ValueError(f"{source}: cycle detected at node {node_id}")
            active.add(node_id)
            path.append(node_id)
            node_id = parents[node_id]
        complete.update(path)
    return rows


class RegionAnalysisPerNeuron:
    def __init__(self, neuron_tracer_obj, atlas_volume: np.ndarray, atlas_table: pd.DataFrame):
        self.neuron = neuron_tracer_obj
        self.atlas = atlas_volume
        self.atlas_table = atlas_table
        if atlas_volume.ndim != 3:
            raise ValueError("Per-neuron analysis requires a selected 3D atlas level")
        if not {"Index", "Abbreviation"}.issubset(atlas_table.columns) or atlas_table.empty:
            raise ValueError("Atlas key requires nonempty Index and Abbreviation columns")
        indices = []
        for raw in atlas_table["Index"]:
            try:
                number = Decimal(str(raw))
            except InvalidOperation as exc:
                raise ValueError("Atlas label indices must be finite nonnegative integers") from exc
            if (isinstance(raw, (bool, np.bool_)) or not number.is_finite()
                    or number != number.to_integral_value() or number < 0):
                raise ValueError("Atlas label indices must be finite nonnegative integers")
            indices.append(int(number))
        if len(indices) != len(set(indices)):
            raise ValueError("Atlas label indices must be unique")
        labels = atlas_table["Abbreviation"].tolist()
        if any(not isinstance(label, str) or not label.strip() or label != label.strip() for label in labels):
            raise ValueError("Atlas abbreviations must be nonblank literal text without surrounding whitespace")
        if len(labels) != len(set(labels)):
            raise ValueError("Atlas abbreviations must be unique to prevent regional length overwrite")
        self.brain_region_map = dict(zip(indices, labels))
        self.mapped_brain_region_lengths: dict = {}
        self.neuron_total_length: float = 0.0
        self.soma_region: str = ""
        self.terminal_regions: list = []

    def run(self):
        all_region_lengths, self.neuron_total_length = (
            self._calculate_neuronal_branch_length()
        )
        self.soma_region, self.terminal_regions = self._soma_and_terminal_region()
        terminal_region_names = {t["region"] for t in self.terminal_regions}
        self.mapped_brain_region_lengths = {
            region: length
            for region, length in all_region_lengths.items()
            if region in terminal_region_names
        }

    @staticmethod
    def _distance(p1, p2) -> float:
        return float(
            np.sqrt(
                (p1.x_nii - p2.x_nii) ** 2
                + (p1.y_nii - p2.y_nii) ** 2
                + (p1.z_nii - p2.z_nii) ** 2
            )
        )

    def _calculate_neuronal_branch_length(self):
        brain_region_lengths = defaultdict(float)
        total_length = 0.0
        for branch in self.neuron.branches:
            for i in range(len(branch) - 1):
                cur, nxt = branch[i], branch[i + 1]
                edge = round(self._distance(cur, nxt), 3)
                total_length += edge
                vox = tuple(
                    np.round([cur.x_nii, cur.y_nii, cur.z_nii]).astype(int).flatten()
                )
                if all(0 <= vox[d] < self.atlas.shape[d] for d in range(3)):
                    rid = int(self.atlas[vox])
                    if rid > 0:
                        brain_region_lengths[rid] += edge
        mapped = {
            self.brain_region_map.get(idx, f"Unknown_{idx}"): length
            for idx, length in brain_region_lengths.items()
        }
        return mapped, total_length

    def _soma_and_terminal_region(self):
        soma = self.neuron.root
        soma_pos = tuple(
            np.round([soma.x_nii, soma.y_nii, soma.z_nii]).astype(int).flatten()
        )
        if all(0 <= soma_pos[d] < self.atlas.shape[d] for d in range(3)):
            sid = int(self.atlas[soma_pos])
            soma_region = self.brain_region_map.get(sid, f"Unknown_{sid}")
        else:
            soma_region = "Out_of_Bounds"
        terminal_regions = []
        for node in self.neuron.terminal_nodes:
            pos = tuple(
                np.round([node.x_nii, node.y_nii, node.z_nii]).astype(int).flatten()
            )
            if all(0 <= pos[d] < self.atlas.shape[d] for d in range(3)):
                tid = int(self.atlas[pos])
                t_name = self.brain_region_map.get(tid, f"Unknown_{tid}")
                terminal_regions.append({"region": t_name, "coords": pos})
            else:
                terminal_regions.append({"region": "Out_of_Bounds", "coords": pos})
        return soma_region, terminal_regions

class PopulationRegionAnalysis:

    def __init__(
        self,
        sample_id: str,
        atlas: np.ndarray,
        atlas_table: pd.DataFrame,
        template_img=None,
        nii_space: str = "monkey",
        arm_key_path: str = None,
        cortex_hierarchy_csv: str = None,
        subcortical_hierarchy_csv: str = None,
        auto_hierarchy: bool = True,
        auto_laterality: bool = True,
        output_base: str = None,
        create_output_folder: bool = False,
        show_plots: bool = True,
        neuron_list: Optional[List[dict]] = None,
        swc_source_dir: str = None,
        iondata_host=None,
        refresh_swc: bool = False,
        hemisphere_reference=None,
    ):
        """
        Args:
            sample_id: Sample ID
            atlas: Atlas volume
            atlas_table: Region lookup table
            template_img: Template image supplied with the population call
            nii_space: Coordinate space
            arm_key_path: Path to ARM key file (fallback L1-L2)
            cortex_hierarchy_csv: CSV file(s) for cortical regions (CL_/CR_)
            subcortical_hierarchy_csv: CSV file(s) for subcortical regions (SL_/SR_)
            auto_hierarchy: Auto-add hierarchy columns
            auto_laterality: Auto-add laterality columns
            output_base: Root for output folders
            create_output_folder: Create timestamped output tree
            show_plots: Whether to display plots
        """
        self.sample_id = sample_id
        self.full_atlas = atlas
        self.atlas_table = atlas_table
        self.template_img = template_img
        self.nii_space = nii_space
        if neuron_list is None or swc_source_dir is None:
            raise ValueError("ReMAP population requires neuron_list and the configured SWC cache")
        self.neuron_list = list(neuron_list)
        self.swc_source_dir = Path(swc_source_dir)
        self.iondata_host = iondata_host
        self.refresh_swc = bool(refresh_swc)
        self.load_failures = []
        self.hemisphere_reference = hemisphere_reference
        self.classifier = NeuronClassifier(atlas_table)
        self.plot_dataframe = pd.DataFrame()
        self.neurons: dict = {}

        self.auto_hierarchy = auto_hierarchy
        self.auto_laterality = auto_laterality
        self.hierarchy: Optional[RegionHierarchy] = None
        self.hierarchy_table = None  # Legacy single table
        self.dual_hierarchy: Optional[DualHierarchyTable] = None  # New dual system
        self._arm_key_path = arm_key_path
        self.show_plots = show_plots

        self.output: Optional[OutputManager] = None
        if create_output_folder:
            self.output = OutputManager(
                base_path=output_base,
                sample_id=sample_id,
                create_timestamp=True,
            )

        # Load ARM key (fallback for L1-L2)
        if arm_key_path:
            self._load_hierarchy(arm_key_path)
        elif auto_hierarchy:
            raise ValueError("Full hierarchy analysis requires explicit arm_key_path")

        # Load user CSV hierarchy (PRIORITY for L3-L6)
        # Use dual hierarchy system if cortex/subcortical paths provided
        if cortex_hierarchy_csv or subcortical_hierarchy_csv:
            self._load_dual_hierarchy(cortex_hierarchy_csv, subcortical_hierarchy_csv)

    # ==================================================================
    # HIERARCHY LOADING
    # ==================================================================
    def _detect_and_load_hierarchy(self):
        """Fallback key search for ``add_hierarchy_columns``.

        Live ``remap population`` and ``remap one`` use the designated DEB
        share profile. This helper checks that share key, then a neighboring
        ``atlas`` folder.
        """
        from ..atlas_profile import dormant_hierarchy_key_candidates

        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = dormant_hierarchy_key_candidates(script_dir)
        for path in candidates:
            if os.path.exists(path):
                self._load_hierarchy(path)
                return

    def _load_hierarchy(self, arm_key_path: str):
        try:
            self.hierarchy = RegionHierarchy.from_file(arm_key_path)
            self._arm_key_path = arm_key_path
        except Exception:
            self.hierarchy = None

    def _load_dual_hierarchy(self, cortex_paths=None, subcortical_paths=None):
        """Load separate hierarchy tables for cortex and subcortical regions."""
        def normalize_paths(paths):
            if paths is None:
                return []
            if isinstance(paths, str):
                return [paths]
            return list(paths)

        cortex_valid = [p for p in normalize_paths(cortex_paths) if os.path.exists(p)]
        subcortical_valid = [p for p in normalize_paths(subcortical_paths) if os.path.exists(p)]

        if cortex_valid or subcortical_valid:
            self.dual_hierarchy = DualHierarchyTable(
                cortex_paths=cortex_valid if cortex_valid else None,
                subcortical_paths=subcortical_valid if subcortical_valid else None,
            )

    # ==================================================================
    # PROCESSING
    # ==================================================================
    def process(
        self,
        limit: int = None,
        level: int = 6,
        neuron_id: Union[str, List[str]] = None,
        add_hierarchy: bool = None,
        add_laterality: bool = None,
    ):
        """
        Process neurons and build the analysis dataframe.

        Args:
            limit: Maximum number of neurons to process (from full list)
            level: Atlas hierarchy level (1-6, default: 6)
            neuron_id: Single neuron ID (str like '001.swc') or list of IDs
                       to process specific neurons
            add_hierarchy: Override auto_hierarchy setting
            add_laterality: Override auto_laterality setting
        """
        if isinstance(level, (bool, np.bool_)) or not isinstance(level, (int, np.integer)) or not 1 <= level <= 6:
            raise ValueError("Atlas level must be an integer between 1 and 6")
        if self.full_atlas.ndim not in (3, 5):
            raise ValueError("Atlas must be a selected 3D level or a 5D hierarchy")
        if self.full_atlas.ndim == 5 and (self.full_atlas.shape[3] != 1 or level > self.full_atlas.shape[4]):
            raise ValueError("Atlas hierarchy geometry does not contain the requested level")
        if neuron_id is not None and not isinstance(neuron_id, str):
            selected_ids = list(neuron_id)
            if len(selected_ids) != len(set(selected_ids)):
                raise ValueError("Requested neuron IDs must be unique")
            neuron_id = selected_ids

        current_atlas = (
            self.full_atlas[:, :, :, 0, level - 1]
            if self.full_atlas.ndim == 5
            else self.full_atlas
        )

        # Build target list based on neuron_id parameter
        if neuron_id is not None:
            # Normalize to list
            if isinstance(neuron_id, str):
                neuron_ids = [neuron_id]
            else:
                neuron_ids = list(neuron_id)

            # Find matching neurons
            target_list = []
            not_found = []
            for nid in neuron_ids:
                matches = [n for n in self.neuron_list if n["name"] == nid]
                if matches:
                    target_list.extend(matches)
                else:
                    not_found.append(nid)

            if not_found:
                print(f"[WARN] Neurons not found: {not_found}")

            if not target_list:
                print(f"[ERROR] No matching neurons found for: {neuron_ids}")
                return
        elif limit:
            target_list = self.neuron_list[:limit]
        else:
            target_list = self.neuron_list

        identities = []
        for entry in target_list:
            sample = str(entry.get("sampleid", "")).strip()
            name = entry.get("name")
            if sample != str(self.sample_id).strip():
                raise ValueError("Selected neuron entry belongs to another sample or lacks sampleid")
            if not isinstance(name, str) or not name.strip() or Path(name).name != name:
                raise ValueError("Selected neuron entry requires a nonempty basename")
            identities.append((sample, name))
        if len(identities) != len(set(identities)):
            raise ValueError("Selected full neuron identities must be unique")

        print(f"Processing {len(target_list)} neurons at Level {level}...")

        data = []
        self.load_failures = []
        for entry in target_list:
            print(f"  -> {entry['name']}")
            neuron = NeuronTracer()
            try:
                neuron.process(
                    entry["sampleid"], entry["name"], nii_space=self.nii_space,
                    cache_root=self.swc_source_dir, iondata_host=self.iondata_host,
                    allow_download=bool(self.iondata_host),
                    refresh=self.refresh_swc,
                )
            except Exception as exc:
                self.load_failures.append({"SampleID": entry.get("sampleid", self.sample_id),
                                           "NeuronID": entry.get("name"), "error": str(exc)})
                print(f"     Load failed for {entry.get('sampleid', self.sample_id)}/{entry.get('name', 'Unknown')}: {exc}")
                continue

            analysis = RegionAnalysisPerNeuron(neuron, current_atlas, self.atlas_table)
            analysis.run()

            neuron.outliers = []
            if "Unknown" in analysis.soma_region or analysis.soma_region == "Out_of_Bounds":
                root = neuron.root
                neuron.outliers.append(
                    {
                        "type": "Soma",
                        "region": analysis.soma_region,
                        "coords": (
                            int(root.x_nii),
                            int(root.y_nii),
                            int(root.z_nii),
                        ),
                    }
                )
            for item in analysis.terminal_regions:
                if "Unknown" in item["region"] or item["region"] == "Out_of_Bounds":
                    neuron.outliers.append(
                        {
                            "type": "Terminal",
                            "region": item["region"],
                            "coords": item["coords"],
                        }
                    )
            self.neurons[neuron.swc_filename] = neuron

            seen, term_unique = set(), []
            for item in analysis.terminal_regions:
                r = item["region"]
                if r not in seen:
                    seen.add(r)
                    term_unique.append(r)

            n_type = self.classifier.classify_single_neuron(
                term_unique, analysis.soma_region
            )
            root = neuron.root

            data.append(
                {
                    "SampleID": self.sample_id,
                    "NeuronID": neuron.swc_filename,
                    "Neuron_Type": n_type,
                    "Soma_Region": analysis.soma_region,
                    "Soma_NII_X": round(root.x_nii, 4),
                    "Soma_NII_Y": round(root.y_nii, 4),
                    "Soma_NII_Z": round(root.z_nii, 4),
                    "Soma_Phys_X": round(root.x, 4),
                    "Soma_Phys_Y": round(root.y, 4),
                    "Soma_Phys_Z": round(root.z, 4),
                    "Total_Length": analysis.neuron_total_length,
                    "Length_Unit": "voxel",
                    "Terminal_Count": len(term_unique),
                    "Terminal_Regions": term_unique,
                    "Region_projection_length": analysis.mapped_brain_region_lengths,
                    "Outlier_Count": len(neuron.outliers),
                    "Outlier_Details": neuron.outliers,
                }
            )

        self.plot_dataframe = pd.DataFrame(data)
        if self.plot_dataframe.empty:
            return

        do_hier = add_hierarchy if add_hierarchy is not None else self.auto_hierarchy
        hier_available = self.hierarchy is not None or self.hierarchy_table is not None or self.dual_hierarchy is not None
        if do_hier and hier_available:
            self._apply_hierarchy_columns(max_level=6, projection_min_level=6)

        do_lat = add_laterality if add_laterality is not None else self.auto_laterality
        if do_lat:
            self._apply_laterality_columns()

    # ==================================================================
    # HIERARCHY HELPERS
    # ==================================================================
    def _apply_hierarchy_columns(self, max_level: int = 6, projection_min_level: int = 1):
        """
        Apply hierarchy columns with configurable levels for soma and projections.

        Uses dual hierarchy system if available, otherwise falls back to
        single hierarchy table or ARM key.

        Args:
            max_level: Max hierarchy level for soma regions (default: 6, covers L1-L6)
            projection_min_level: Min hierarchy level for projections (default: 1, covers L1-L6)
        """
        # Determine which hierarchy source to use
        if self.dual_hierarchy is not None:
            hierarchy_source = self.dual_hierarchy
        elif self.hierarchy_table is not None:
            hierarchy_source = self.hierarchy_table
        elif self.hierarchy is not None:
            hierarchy_source = None  # Will use ARM key in functions
        else:
            return

        self.plot_dataframe = add_soma_hierarchy_column(
            self.plot_dataframe, self.hierarchy, max_level=max_level,
            hierarchy_table=hierarchy_source,
        )
        self.plot_dataframe = add_projection_hierarchy(
            self.plot_dataframe, self.hierarchy, max_level=max_level,
            hierarchy_table=hierarchy_source,
        )

        # Projection hierarchy: projection_min_level to max_level
        self.plot_dataframe = add_projection_length_hierarchy(
            self.plot_dataframe,
            self.hierarchy,
            "Region_projection_length",
            max_level,
            min_level=projection_min_level,
            hierarchy_table=hierarchy_source,
        )

        # Verify all projection columns exist
        self._ensure_projection_columns_exist(projection_min_level, max_level)

    def _ensure_projection_columns_exist(self, min_level: int, max_level: int):
        """Ensure projection length columns exist, create empty dicts if missing."""
        for lv in range(min_level, max_level + 1):
            col_name = f"Region_Projection_Length_L{lv}"
            if col_name not in self.plot_dataframe.columns:
                self.plot_dataframe[col_name] = self.plot_dataframe.apply(lambda _: {}, axis=1)

    def _apply_laterality_columns(self):
        length_col = None
        for c in ("Region_Projection_Length_finest", "Region_projection_length"):
            if c in self.plot_dataframe.columns:
                length_col = c
                break
        reference = getattr(self, "hemisphere_reference", None)
        reference_sides = None
        if reference is not None:
            sides = []
            for _, row in self.plot_dataframe.iterrows():
                neuron = self.neurons.get(row["NeuronID"])
                xyz = ([neuron.root.x_nii, neuron.root.y_nii, neuron.root.z_nii]
                       if neuron is not None else [row["Soma_NII_" + a] for a in "XYZ"])
                sides.append(reference.sample(xyz))
            reference_sides = pd.Series(sides, index=self.plot_dataframe.index)
        self.plot_dataframe = add_laterality_columns(
            self.plot_dataframe,
            soma_col="Soma_Region",
            terminal_col="Terminal_Regions",
            length_col=length_col,
            soma_side_reference=reference_sides,
            soma_side_reference_source=reference.source if reference is not None else None,
        )
        if hasattr(self, "classifier"):
            self.plot_dataframe["Neuron_Type"] = self.plot_dataframe.apply(
                lambda row: self.classifier.classify_single_neuron(
                    row["Terminal_Regions"], row["Soma_Region"], soma_side=row["Soma_Side"]), axis=1)

    def apply_soma_labels(self, mapping: dict, source: str):
        """Apply reviewed labels and recompute dependent views together.

        This edits this analysis instance only. It does not promote annotations
        or modify source workbooks. Conflicts with the reference remain explicit.
        """
        if not source or not str(source).strip():
            raise ValueError("Refined soma labels require source provenance")
        if "Soma_Region_Auto" not in self.plot_dataframe:
            self.plot_dataframe["Soma_Region_Auto"] = self.plot_dataframe.Soma_Region
        labels = self.plot_dataframe.NeuronID.map(mapping)
        use = labels.notna()
        self.plot_dataframe.loc[use, "Soma_Region"] = labels.loc[use]
        self.plot_dataframe.loc[use, "Soma_Label_Source"] = source
        self._apply_hierarchy_columns(max_level=6, projection_min_level=1)
        self._apply_laterality_columns()
        return self.plot_dataframe

    def load_processed_dataframe(self, df_or_path) -> pd.DataFrame:
        if isinstance(df_or_path, pd.DataFrame):
            loaded = normalize_region_dataframe(df_or_path)
        elif isinstance(df_or_path, (str, os.PathLike)):
            loaded = load_processed_df(df_or_path)
        else:
            raise TypeError("Expected DataFrame or file path")
        self.plot_dataframe = loaded
        print(f"Loaded {len(self.plot_dataframe)} neurons")
        return self.plot_dataframe

    # ==================================================================
    # DERIVED VIEWS
    # ==================================================================
    def get_summary_df(self) -> pd.DataFrame:
        """Sheet 1: Scalar-only summary."""
        cols = [
            "NeuronUID", "SampleID", "NeuronID", "Neuron_Type", "Soma_Region", "Soma_Side",
            "prefix_derived", "location_derived", "Soma_Side_Conflict",
            "Soma_Side_Reference_Source", "Soma_Region_Auto", "Soma_Label_Source",
            "Soma_NII_X", "Soma_NII_Y", "Soma_NII_Z",
            "Soma_Phys_X", "Soma_Phys_Y", "Soma_Phys_Z",
            "Total_Length", "Length_Unit", "Terminal_Count",
            "N_Ipsilateral", "N_Contralateral", "N_Laterality_Unknown",
            "Total_Ipsilateral_Length", "Total_Contralateral_Length", "Total_Unknown_Laterality_Length",
            "Laterality_Index", "Outlier_Count",
        ]
        available = [c for c in cols if c in self.plot_dataframe.columns]
        return self.plot_dataframe[available].copy()

    def get_soma_hierarchy_df(self) -> pd.DataFrame:
        """Sheet 2: Hierarchy dict expanded to L1–L6."""
        identity = [column for column in ("NeuronUID", "SampleID", "NeuronID", "Soma_Region")
                    if column in self.plot_dataframe]
        neuron_metadata(self.plot_dataframe)
        df = self.plot_dataframe[identity].copy()
        for lv in range(1, 7):
            col = f"Soma_Level_{lv}"
            if col in self.plot_dataframe:
                df[f"L{lv}"] = self.plot_dataframe[col]
        if "Soma_Region_Hierarchy" in self.plot_dataframe.columns:
            hier_exp = self.plot_dataframe["Soma_Region_Hierarchy"].apply(
                lambda d: pd.Series(d) if isinstance(d, dict) else pd.Series(dtype=str)
            )
            for lv in range(1, 7):
                key = f"L{lv}"
                if key not in hier_exp.columns:
                    hier_exp[key] = None
            hier_exp = hier_exp[[f"L{lv}" for lv in range(1, 7)]]
            for key in hier_exp:
                if key in df:
                    conflicts = df[key].notna() & hier_exp[key].notna() & df[key].ne(hier_exp[key])
                    if conflicts.any():
                        raise ValueError(f"Conflicting soma hierarchy values for {key}")
                    df[key] = df[key].fillna(hier_exp[key])
                else:
                    df[key] = hier_exp[key]
        return df

    def get_projection_matrix(self, level: str = "finest") -> pd.DataFrame:
        """Neuron x region retained reconstruction lengths in the source unit."""
        if level == "finest":
            candidates = [
                "Region_Projection_Length_finest",
                "Region_projection_length",
            ]
        else:
            # Handle both string and int level
            level_int = int(level) if isinstance(level, str) and level.isdigit() else level
            candidates = [f"Region_Projection_Length_L{level_int}"]

        length_col = None
        for c in candidates:
            if c in self.plot_dataframe.columns:
                length_col = c
                break

        if length_col is None:
            available_proj_cols = [
                c for c in self.plot_dataframe.columns
                if 'Projection_Length' in c or 'projection_length' in c
            ]
            print(f"[WARN] No projection-length column for level='{level}'")
            print(f"  Available projection columns: {available_proj_cols}")
            return pd.DataFrame()

        # Convert column to list of dicts, handling non-dict values
        # Keep prefixes internally for correct laterality classification
        data_list = []
        for val in self.plot_dataframe[length_col]:
            data_list.append(parse_projection_lengths(val))

        matrix = pd.DataFrame(data_list)
        matrix.fillna(0, inplace=True)

        if matrix.empty:
            print(f"[WARN] Empty matrix for level='{level}'")
            return pd.DataFrame()

        regular = sorted([c for c in matrix.columns if c != "_Unmapped"])
        ordered = regular + (["_Unmapped"] if "_Unmapped" in matrix.columns else [])
        matrix = matrix[ordered]
        metadata = neuron_metadata(self.plot_dataframe)
        matrix = pd.concat([metadata, matrix.reset_index(drop=True)], axis=1)

        if "_Unmapped" in matrix.columns:
            total_u = matrix["_Unmapped"].sum()
            total_a = matrix.drop(columns=metadata.columns).sum().sum()
            if total_u > 0:
                pct = total_u / total_a * 100 if total_a > 0 else 0
                print(
                    f"[MATRIX L{level}] _Unmapped: {total_u:.1f} source units (see Length_Unit; {pct:.1f}%)"
                )

        return matrix

    def get_projection_matrix_split(self, level: str = "finest") -> tuple:
        """
        Split projection matrix into ipsilateral and contralateral DataFrames.

        Uses original data with prefixes for correct laterality classification,
        then removes hemisphere prefixes using collision-safe target labels.
        Cortical/subcortical homonyms retain separate C_/S_ namespaces.

        Args:
            level: Hierarchy level ("finest" or 1-6)

        Returns:
            Tuple of (ipsi_df, contra_df) with collision-safe regional labels.
        """
        # Get source column with prefixes (for correct laterality classification)
        if level == "finest":
            candidates = ["Region_Projection_Length_finest", "Region_projection_length"]
        else:
            level_int = int(level) if isinstance(level, str) and level.isdigit() else level
            candidates = [f"Region_Projection_Length_L{level_int}"]

        source_col = None
        for c in candidates:
            if c in self.plot_dataframe.columns:
                source_col = c
                break

        if source_col is None:
            return pd.DataFrame(), pd.DataFrame()

        # Ensure laterality columns exist
        if "Soma_Side" not in self.plot_dataframe.columns:
            self._apply_laterality_columns()

        metadata = neuron_metadata(self.plot_dataframe)
        lengths = self.plot_dataframe[source_col].apply(parse_projection_lengths)
        atlas_regions = getattr(self, "atlas_table", pd.DataFrame()).get("Abbreviation", [])
        column_names = projection_column_names(
            {region for mapping in lengths for region in mapping}, atlas_regions)

        # Build rows with clean (stripped) column names
        ipsi_data = []
        contra_data = []

        for position, (_, row) in enumerate(self.plot_dataframe.iterrows()):
            soma_side = row.get("Soma_Side", "Unknown")
            length_dict = lengths.iloc[position]

            ipsi_row = {}
            contra_row = {}

            # Fill in values with stripped column names
            for region, length in length_dict.items():
                if length == 0:
                    continue
                lat = LateralityParser.classify_with_soma_side(soma_side, region)
                clean_region = column_names[region]

                if lat == "Ipsilateral":
                    ipsi_row[clean_region] = ipsi_row.get(clean_region, 0) + length
                elif lat == "Contralateral":
                    contra_row[clean_region] = contra_row.get(clean_region, 0) + length

            ipsi_data.append(ipsi_row)
            contra_data.append(contra_row)

        # Create DataFrames
        ipsi_df = pd.concat([metadata, pd.DataFrame(ipsi_data).fillna(0)], axis=1)
        contra_df = pd.concat([metadata, pd.DataFrame(contra_data).fillna(0)], axis=1)

        return ipsi_df, contra_df

    def get_projection_strength_split(self, level: str = "finest") -> tuple:
        """Log-transform the final split lengths, after anatomical aggregation."""
        results = []
        for lengths in self.get_projection_matrix_split(level):
            strength = lengths.copy()
            targets = [column for column in strength if column not in ("NeuronUID", "SampleID", "NeuronID", "Neuron_Type")]
            strength[targets] = np.log10(strength[targets] + 1).round(4)
            results.append(strength)
        return tuple(results)

    def get_terminal_sites_df(self) -> pd.DataFrame:
        """Distinct endpoint-target regions from all-compartment legacy leaves.

        These rows do not establish biological terminal sites or boutons.
        """
        rows = []
        for _, nr in self.plot_dataframe.iterrows():
            nid = nr["NeuronID"]
            identity = {column: nr[column] for column in ("NeuronUID", "SampleID") if column in nr}
            ntype = nr.get("Neuron_Type", "")
            soma = nr.get("Soma_Region", "")
            lat_info = nr.get("Terminal_Laterality", None)
            if isinstance(lat_info, list) and lat_info:
                for term in lat_info:
                    rows.append(
                        {
                            **identity,
                            "NeuronID": nid,
                            "Neuron_Type": ntype,
                            "Terminal_Region": term.get("region", ""),
                            "Side": term.get("side", ""),
                            "Laterality": term.get("laterality", ""),
                        }
                    )
            else:
                terminals = nr.get("Terminal_Regions", [])
                if not isinstance(terminals, (list, tuple)):
                    terminals = parse_terminal_regions(terminals)
                for t_region in terminals:
                    rows.append(
                        {
                            **identity,
                            "NeuronID": nid,
                            "Neuron_Type": ntype,
                            "Terminal_Region": t_region,
                            "Side": LateralityParser.get_side(t_region),
                            "Laterality": LateralityParser.classify_with_soma_side(nr.get("Soma_Side", LateralityParser.get_side(soma)), t_region),
                        }
                    )
        df = pd.DataFrame(rows)
        hierarchy_source = self.dual_hierarchy or self.hierarchy_table
        if (self.hierarchy or hierarchy_source) and not df.empty:
            for lv in [1, 3, 6]:
                df[f"Terminal_L{lv}"] = df["Terminal_Region"].apply(
                    lambda r, _lv=lv: resolve_to_level(
                        str(r), _lv, self.hierarchy, hierarchy_source
                    )
                )
        return df

    def get_laterality_df(self) -> pd.DataFrame:
        """Per-neuron counts and lengths relative to the resolved soma side.

        Laterality_Index is Contra/(Ipsi+Contra), 0..1; unresolved lengths are
        excluded. The separate signed contrast (Contra-Ipsi)/(Contra+Ipsi)
        ranges from -1 to 1 and is not produced by this column. A zero
        resolved denominator remains missing.
        """
        scalar_cols = [
            "NeuronUID", "SampleID", "NeuronID", "Neuron_Type", "Soma_Region", "Soma_Side",
            "prefix_derived", "location_derived", "Soma_Side_Conflict",
            "N_Ipsilateral", "N_Contralateral", "N_Laterality_Unknown",
            "Total_Ipsilateral_Length", "Total_Contralateral_Length",
            "Total_Unknown_Laterality_Length", "Laterality_Index",
        ]
        available = [c for c in scalar_cols if c in self.plot_dataframe.columns]
        df = self.plot_dataframe[available].copy()
        for list_col in ("Ipsilateral_Regions", "Contralateral_Regions"):
            if list_col in self.plot_dataframe.columns:
                df[list_col] = self.plot_dataframe[list_col].apply(
                    lambda x: ", ".join(x) if isinstance(x, list) else ""
                )
        return df

    def get_outlier_df(self) -> pd.DataFrame:
        """Sheet 7: Long-format outliers."""
        rows = []
        for _, nr in self.plot_dataframe.iterrows():
            details = nr.get("Outlier_Details", [])
            identity = {column: nr[column] for column in ("NeuronUID", "SampleID") if column in nr}
            if not isinstance(details, list):
                if isinstance(details, str):
                    try:
                        import ast
                        details = ast.literal_eval(details)
                    except Exception:
                        continue
                else:
                    continue
            for o in details:
                coords = o.get("coords", (None, None, None))
                if isinstance(coords, (list, tuple)) and len(coords) >= 3:
                    vx, vy, vz = coords[0], coords[1], coords[2]
                else:
                    vx, vy, vz = None, None, None
                rows.append(
                    {
                        **identity,
                        "NeuronID": nr["NeuronID"],
                        "Neuron_Type": nr.get("Neuron_Type", ""),
                        "Outlier_Type": o.get("type", ""),
                        "Region": o.get("region", ""),
                        "Voxel_X": vx,
                        "Voxel_Y": vy,
                        "Voxel_Z": vz,
                    }
                )
        return pd.DataFrame(rows)

    # ==================================================================
    # SAVE
    # ==================================================================
    def save_report(self, content: str, name: str):
        if self.output is None:
            print(content)
            return
        p = self.output.get_report_path(name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[SAVED] {p}")

    def save_all(
        self,
        include_strength_levels: list = None,
        generate_plots: bool = True,
        swc_plots: str = "off",
    ) -> Optional[str]:
        """
        Save everything:
            tables/  → multi-sheet Excel (includes laterality columns)
            reports/ → 3 text reports
            plots/   → all plots as PNG

        Args:
            include_strength_levels: Extra hierarchy levels (e.g. [1, 3, 6]).
                                     Will generate Projection_Length_L{n} and
                                     Projection_Strength_L{n} sheets WITH ipsi/contra
                                     columns (e.g., Projection_Strength_L6_IPSI).
            generate_plots: If True, generate and save all plots.
        """
        if self.plot_dataframe.empty:
            print("[ERROR] No data. Run process() first.")
            return None

        if self.output is None:
            print("[WARN] No output manager. Set create_output_folder=True.")
            fallback = f"{self.sample_id}_results.xlsx"
            self._write_workbook(fallback, include_strength_levels)
            return None

        print("\n" + "=" * 60)
        print(f"SAVING ALL RESULTS: {self.sample_id}")
        print("=" * 60)

        # Ensure all required hierarchy columns exist before saving
        if include_strength_levels:
            self._ensure_hierarchy_columns_for_levels(include_strength_levels)

        # 1. TABLES (includes laterality columns integrated)
        path = self.output.get_table_path(f"{self.sample_id}_results")
        self._write_workbook(str(path), include_strength_levels)

        # 2. REPORTS (3 separate files)
        print("\n[REPORTS]")
        self._save_analysis_summary_report()
        self._save_terminal_report()
        self._save_projection_sites_report()

        # 3. PLOTS
        if generate_plots:
            print("\n[PLOTS]")
            self._generate_all_plots()
        if swc_plots not in {None, False, "off"}:
            print("\n[SWC PLOTS]")
            self._write_swc_plots(str(swc_plots))

        self.output.print_summary()
        return str(self.output.output_dir)

    def _ensure_hierarchy_columns_for_levels(self, levels: list):
        """
        Ensure hierarchy columns exist for all requested levels.
        Creates missing levels on-demand when save_all() requests them.

        Args:
            levels: List of levels to ensure exist (e.g., [3, 6] for L3 and L6)
        """
        if not levels:
            return

        missing_levels = []
        for lv in levels:
            col_name = f"Region_Projection_Length_L{lv}"
            if col_name not in self.plot_dataframe.columns:
                missing_levels.append(lv)

        if missing_levels:
            print(f"[HIERARCHY] Creating missing projection columns: {missing_levels}")
            if self.hierarchy is not None or self.hierarchy_table is not None or self.dual_hierarchy is not None:
                # Only create the missing levels (not all L1-L6)
                min_missing = min(missing_levels)
                max_missing = max(missing_levels)
                print(f"[HIERARCHY] Generating levels {min_missing}-{max_missing}")
                self._apply_hierarchy_columns(max_level=6, projection_min_level=min_missing)
            else:
                print("[WARN] No hierarchy source available. Creating empty columns.")
                self._ensure_projection_columns_exist(min(missing_levels), max(missing_levels))


    def _write_workbook(
        self,
        path: str,
        include_strength_levels: list = None,
    ):
        print(f"\n[EXCEL] Writing: {path}")
        destination = Path(path)
        if destination.exists():
            destination.unlink()

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            # Sheet 1: Summary
            summary = self.get_summary_df()
            summary.to_excel(writer, sheet_name="Summary", index=False)
            print(
                f"  [Sheet] Summary: {len(summary)} rows x {len(summary.columns)} cols"
            )

            # Sheet 2: Soma Hierarchy
            soma_hier = self.get_soma_hierarchy_df()
            soma_hier.to_excel(writer, sheet_name="Soma_Hierarchy", index=False)
            print(
                f"  [Sheet] Soma_Hierarchy: {len(soma_hier)} rows x {len(soma_hier.columns)} cols"
            )

            # Sheet 3: Terminal Sites
            terminals = self.get_terminal_sites_df()
            terminals.to_excel(writer, sheet_name="Terminal_Sites", index=False)
            print(f"  [Sheet] Terminal_Sites: {len(terminals)} rows")

            # Sheet 4: Laterality (scalar summary)
            laterality = self.get_laterality_df()
            if len(laterality.columns) > 2:
                laterality.to_excel(
                    writer, sheet_name="Laterality", index=False
                )
                print(
                    f"  [Sheet] Laterality: {len(laterality)} rows x {len(laterality.columns)} cols"
                )
            else:
                print("  [Sheet] Laterality: SKIPPED (insufficient columns)")

            # Sheet 5: Outliers
            outliers = self.get_outlier_df()
            outliers.to_excel(writer, sheet_name="Outliers", index=False)
            n_o = len(outliers)
            print(
                f"  [Sheet] Outliers: {n_o} events"
                + (" (clean!)" if n_o == 0 else "")
            )

            # Projection sheets with laterality splits
            # Preserve absolute atlas labels and unknown-side lengths for
            # reconstruction and cross-sheet QC; splits alone lose that data.
            all_lengths = self.get_projection_matrix("finest")
            if not all_lengths.empty:
                all_lengths.to_excel(writer, sheet_name="Projection_Length_all", index=False)
            # Sheet 6-7: Projection Length finest (ipsi/contra split)
            ipsi_len, contra_len = self.get_projection_matrix_split("finest")
            if not ipsi_len.empty:
                ipsi_len.to_excel(writer, sheet_name="Projection_Length_ipsi", index=False)
                print(f"  [Sheet] Projection_Length_ipsi: {len(ipsi_len)} neurons x {len(ipsi_len.columns)-2} regions")
            if not contra_len.empty:
                contra_len.to_excel(writer, sheet_name="Projection_Length_contra", index=False)
                print(f"  [Sheet] Projection_Length_contra: {len(contra_len)} neurons x {len(contra_len.columns)-2} regions")

            # Sheet 8-9: Projection Strength finest (ipsi/contra split)
            ipsi_str, contra_str = self.get_projection_strength_split("finest")
            if not ipsi_str.empty:
                ipsi_str.to_excel(writer, sheet_name="Projection_Strength_ipsi", index=False)
                print(f"  [Sheet] Projection_Strength_ipsi: {len(ipsi_str)} neurons x {len(ipsi_str.columns)-2} regions")
            if not contra_str.empty:
                contra_str.to_excel(writer, sheet_name="Projection_Strength_contra", index=False)
                print(f"  [Sheet] Projection_Strength_contra: {len(contra_str)} neurons x {len(contra_str.columns)-2} regions")

            # Extra sheets for specified hierarchy levels
            if include_strength_levels:
                for lv in include_strength_levels:
                    # Length split
                    ipsi_len_lv, contra_len_lv = self.get_projection_matrix_split(lv)
                    if not ipsi_len_lv.empty:
                        ipsi_len_lv.to_excel(
                            writer,
                            sheet_name=f"Projection_Length_L{lv}_ipsi",
                            index=False,
                        )
                        print(f"  [Sheet] Projection_Length_L{lv}_ipsi: {len(ipsi_len_lv)} neurons x {len(ipsi_len_lv.columns)-2} regions")
                    if not contra_len_lv.empty:
                        contra_len_lv.to_excel(
                            writer,
                            sheet_name=f"Projection_Length_L{lv}_contra",
                            index=False,
                        )
                        print(f"  [Sheet] Projection_Length_L{lv}_contra: {len(contra_len_lv)} neurons x {len(contra_len_lv.columns)-2} regions")

                    # Strength split
                    ipsi_str_lv, contra_str_lv = self.get_projection_strength_split(lv)
                    if not ipsi_str_lv.empty:
                        ipsi_str_lv.to_excel(
                            writer,
                            sheet_name=f"Projection_Strength_L{lv}_ipsi",
                            index=False,
                        )
                        print(f"  [Sheet] Projection_Strength_L{lv}_ipsi: {len(ipsi_str_lv)} neurons x {len(ipsi_str_lv.columns)-2} regions")
                    if not contra_str_lv.empty:
                        contra_str_lv.to_excel(
                            writer,
                            sheet_name=f"Projection_Strength_L{lv}_contra",
                            index=False,
                        )
                        print(f"  [Sheet] Projection_Strength_L{lv}_contra: {len(contra_str_lv)} neurons x {len(contra_str_lv.columns)-2} regions")

        print(f"\n[SAVED] {path}")

    # ==================================================================
    # 3 SEPARATE REPORTS
    # ==================================================================
    def _save_analysis_summary_report(self):
        """Report 1/3: Overall analysis summary."""
        df = self.plot_dataframe
        n = len(df)

        lines = [
            "=" * 60,
            f"REGION ANALYSIS REPORT - {self.sample_id}",
            "=" * 60,
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
            "--- OVERVIEW ---",
            f"Total neurons: {n}",
        ]

        if "Neuron_Type" in df.columns:
            lines.append("\n--- Neuron Types ---")
            for t, c in df["Neuron_Type"].value_counts().items():
                lines.append(f"  {t}: {c} ({c / n * 100:.1f}%)")

        lines.append("\n--- Soma Regions (Top 10) ---")
        for r, c in df["Soma_Region"].value_counts().head(10).items():
            lines.append(f"  {r}: {c}")

        if "Soma_Side" in df.columns:
            lines.append("\n--- Laterality ---")
            for side, c in df["Soma_Side"].value_counts().items():
                lines.append(f"  Soma side {side}: {c}")
            if "N_Ipsilateral" in df.columns:
                lines.append(
                    f"  Total ipsilateral endpoint-target entries:   {int(df['N_Ipsilateral'].sum())}"
                )
                lines.append(
                    f"  Total contralateral endpoint-target entries: {int(df['N_Contralateral'].sum())}"
                )
            if "Laterality_Index" in df.columns:
                valid = df["Laterality_Index"].dropna()
                if not valid.empty:
                    lines.append(
                        f"  Contralateral length fraction [Contra/(Ipsi+Contra), 0..1] - mean: {valid.mean():.3f}, "
                        f"median: {valid.median():.3f}"
                    )

        length_col = None
        for c in ("Region_Projection_Length_finest", "Region_projection_length"):
            if c in df.columns:
                length_col = c
                break
        if length_col:
            all_lengths = []
            for d in df[length_col]:
                if isinstance(d, dict):
                    all_lengths.extend(d.values())
            if all_lengths:
                arr = np.array(all_lengths)
                log_arr = np.log10(arr + 1)
                lines.append("\n--- Retained Regional Reconstruction Lengths (Source Units) ---")
                lines.append(
                    f"  Retained regional length: mean={arr.mean():.2f}, "
                    f"median={np.median(arr):.2f}, max={arr.max():.2f} source units (see Length_Unit)"
                )
                lines.append(
                    f"  Display log10(length + 1): mean={log_arr.mean():.3f}, "
                    f"median={np.median(log_arr):.3f}, max={log_arr.max():.3f}"
                )

        lines += [
            "",
            "--- Morphology ---",
            f"Total reconstruction length - Mean: {df['Total_Length'].mean():.2f}, "
            f"Std: {df['Total_Length'].std():.2f} source units (see Length_Unit)",
            f"Distinct endpoint-target regions (legacy all compartments) - Mean: {df['Terminal_Count'].mean():.2f}, "
            f"Max: {int(df['Terminal_Count'].max())}",
        ]

        n_out_neurons = int((df["Outlier_Count"] > 0).sum())
        total_outliers = int(df["Outlier_Count"].sum())
        lines += [
            "",
            "--- Outliers ---",
            f"Neurons with outliers: {n_out_neurons} ({n_out_neurons / n * 100:.1f}%)",
            f"Total outlier events: {total_outliers}",
        ]

        # Add hierarchy column status
        lines.append("\n--- Hierarchy Columns Status ---")
        for lv in range(1, 7):
            col_name = f"Region_Projection_Length_L{lv}"
            status = "OK" if col_name in df.columns else "MISSING"
            lines.append(f"  L{lv}: {status}")

        lines += [
            "",
            "--- Excel Workbook Contents ---",
            "  Sheet 1: Summary                    (scalar overview)",
            "  Sheet 2: Soma_Hierarchy             (L1-L6 expanded)",
            "  Sheet 3: Terminal_Sites             (one row per distinct endpoint-target region; legacy all compartments)",
            "  Sheet 4: Laterality                 (ipsi/contra scalars)",
            "  Sheet 5: Outliers                   (one row per outlier)",
            "",
            "  Projection Length Sheets (split by laterality):",
            "    Projection_Length_ipsi          (ipsilateral regions only)",
            "    Projection_Length_contra        (contralateral regions only)",
            "    Projection_Length_L{n}_ipsi     (level n, ipsilateral)",
            "    Projection_Length_L{n}_contra   (level n, contralateral)",
            "",
            "  Projection Strength Sheets (display log10(retained length + 1), source-unit dependent):",
            "    Projection_Strength_ipsi        (ipsilateral regions, log10)",
            "    Projection_Strength_contra      (contralateral regions, log10)",
            "    Projection_Strength_L{n}_ipsi   (level n, ipsilateral, log10)",
            "    Projection_Strength_L{n}_contra (level n, contralateral, log10)",
            "",
            "=" * 60,
        ]

        report = "\n".join(lines)
        self.save_report(report, "analysis_summary")
        print(report)

    def _save_terminal_report(self):
        """Report 2/3: Distinct endpoint-target regions from all-compartment legacy leaves."""
        df = self.plot_dataframe
        if df.empty or "Terminal_Regions" not in df.columns:
            return

        df_temp = df.copy()
        df_temp["Terminal_Regions"] = df_temp["Terminal_Regions"].apply(
            parse_terminal_regions
        )
        df_temp["_known"] = df_temp["Terminal_Regions"].apply(
            lambda x: sum(is_known_terminal_target(r) for r in x)
        )
        df_temp["_unk"] = df_temp["Terminal_Regions"].apply(
            lambda x: sum(not is_known_terminal_target(r) for r in x)
        )
        total_known = int(df_temp["_known"].sum())
        total_unknown = int(df_temp["_unk"].sum())
        total_sites = total_known + total_unknown
        n_with_unk = int((df_temp["_unk"] > 0).sum())
        n_only_known = int(((df_temp["_unk"] == 0) & (df_temp["_known"] > 0)).sum())
        n_no_targets = int(df_temp["Terminal_Regions"].map(len).eq(0).sum())
        total_n = len(df_temp)

        counts = terminal_target_region_counts(df_temp["Terminal_Regions"]).head(30)

        lines = [
            "=" * 60,
            "ENDPOINT-TARGET REGION DISTRIBUTION REPORT",
            "=" * 60,
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Sample: {self.sample_id}",
            "",
            "--- Known vs Unknown Statistics ---",
            "  Entries are distinct endpoint-target regions per neuron from legacy all-compartment leaves; biological terminals/boutons are not verified.\n  Unknown includes explicit unknown, outside, unmapped, absent and invalid targets.",
            f"  Total endpoint-target entries: {total_sites}",
            f"  Known endpoint-target entries: {total_known} ({total_known / max(total_sites, 1) * 100:.1f}%)",
            f"  Unresolved endpoint-target entries: {total_unknown} ({total_unknown / max(total_sites, 1) * 100:.1f}%)",
            f"  Neurons with unknown regions: {n_with_unk} ({n_with_unk / total_n * 100:.1f}%)",
            f"  Neurons with only known regions: {n_only_known} ({n_only_known / total_n * 100:.1f}%)",
            f"  Neurons with no target entries: {n_no_targets} ({n_no_targets / total_n * 100:.1f}%)",
            "",
            "--- Endpoint-Target Region Distribution (Top 30) ---",
            f"  Total unique regions: {len(counts)}",
            f"  Total entries (known only): {int(counts.sum())}",
            "",
        ]
        for i, (region, cnt) in enumerate(counts.items(), 1):
            pct = cnt / max(counts.sum(), 1) * 100
            lines.append(f"    {i:2d}. {region}: {cnt} neurons ({pct:.1f}%)")
        lines += ["", "=" * 60]

        report = "\n".join(lines)
        self.save_report(report, "terminal_report")

    def _save_projection_sites_report(self):
        """Report 3/3: Known distinct endpoint-target region counts and outliers."""
        df = self.plot_dataframe
        if df.empty or "Terminal_Regions" not in df.columns:
            return

        df_temp = df.copy()
        df_temp["Terminal_Regions"] = df_temp["Terminal_Regions"].apply(
            parse_terminal_regions
        )
        df_temp["_psc"] = df_temp["Terminal_Regions"].apply(
            lambda x: sum(is_known_terminal_target(r) for r in x)
        )
        df_temp["_usc"] = df_temp["Terminal_Regions"].apply(
            lambda x: sum(not is_known_terminal_target(r) for r in x)
        )
        if "Outlier_Count" not in df_temp.columns:
            df_temp["Outlier_Count"] = 0

        total_n = len(df_temp)
        n_wu = int((df_temp["_usc"] > 0).sum())
        n_wo = int((df_temp["Outlier_Count"] > 0).sum())

        lines = [
            "=" * 60,
            "ENDPOINT-TARGET REGION COUNTS (KNOWN REGIONS ONLY)",
            "=" * 60,
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Sample: {self.sample_id}",
            "",
            f"Total neurons analyzed: {total_n}",
            "",
            "--- Known Endpoint-Target Regions (Unresolved Excluded) ---",
            f"  Total known endpoint-target entries: {int(df_temp['_psc'].sum())}",
            f"  Mean known endpoint-target regions per neuron: {df_temp['_psc'].mean():.2f}",
            f"  Median: {df_temp['_psc'].median():.1f}",
            f"  Min: {int(df_temp['_psc'].min())}",
            f"  Max: {int(df_temp['_psc'].max())}",
            f"  Std: {df_temp['_psc'].std():.2f}",
            "",
            "  Distribution of known endpoint-target regions per neuron:",
        ]
        known_dist = df_temp["_psc"].value_counts().sort_index()
        for sites, count in known_dist.head(15).items():
            lines.append(
                f"    {int(sites)} endpoint-target region(s): {int(count)} neurons "
                f"({count / total_n * 100:.1f}%)"
            )

        lines += [
            "",
            "--- Unresolved Endpoint-Target Regions (Excluded from Plot) ---",
            "  Entries are distinct endpoint-target regions per neuron from legacy all-compartment leaves; biological terminals/boutons are not verified.\n  Unknown includes explicit unknown, outside, unmapped, absent and invalid targets.",
            f"  Neurons with unresolved endpoint-target regions: {n_wu} ({n_wu / total_n * 100:.1f}%)",
            f"  Total unresolved endpoint-target entries excluded: {int(df_temp['_usc'].sum())}",
            f"  Mean unresolved endpoint-target regions per neuron: {df_temp['_usc'].mean():.2f}",
            "",
            "--- Outlier Statistics ---",
            f"  Neurons with outliers: {n_wo} ({n_wo / total_n * 100:.1f}%)",
            f"  Total outliers: {int(df_temp['Outlier_Count'].sum())}",
            f"  Mean outliers per neuron: {df_temp['Outlier_Count'].mean():.2f}",
            "",
            "  Distribution of outlier count per neuron:",
        ]
        outlier_dist = df_temp["Outlier_Count"].value_counts().sort_index()
        for outliers, count in outlier_dist.head(10).items():
            lines.append(
                f"    {int(outliers)} outlier(s): {int(count)} neurons "
                f"({count / total_n * 100:.1f}%)"
            )
        lines += ["", "=" * 60]

        report = "\n".join(lines)
        self.save_report(report, "projection_sites_report")

    # ==================================================================
    # GENERATE ALL PLOTS
    # ==================================================================
    def _generate_all_plots(self):
        """Generate and save all standard plots."""
        df = self.plot_dataframe
        if df.empty:
            return

        print("  Generating plots...")

        # 1. Type distribution
        try:
            s = str(self.output.get_plot_path("type_distribution"))
            _plot("plot_type_distribution_df", df, save_path=s, show=self.show_plots)
        except Exception as e:
            print(f"  [WARN] type_distribution failed: {e}")

        # 2. Soma distribution
        try:
            s = str(self.output.get_plot_path("soma_distribution"))
            _plot("plot_soma_distribution_df", df, save_path=s, show=self.show_plots)
        except Exception as e:
            print(f"  [WARN] soma_distribution failed: {e}")

        # 3. Terminal distribution
        try:
            s = str(self.output.get_plot_path("terminal_distribution"))
            _plot("plot_terminal_distribution_df", df, save_path=s, show=self.show_plots)
        except Exception as e:
            print(f"  [WARN] terminal_distribution failed: {e}")

        # 4. Projection sites count
        try:
            s = str(self.output.get_plot_path("projection_sites_count"))
            _plot("plot_projection_sites_count_df", df, save_path=s, show=self.show_plots)
        except Exception as e:
            print(f"  [WARN] projection_sites_count failed: {e}")

        # 5. Laterality summary
        if "N_Ipsilateral" in df.columns:
            try:
                s = str(self.output.get_plot_path("laterality_summary"))
                _plot("plot_laterality_summary_df", df, save_path=s, show=self.show_plots)
            except Exception as e:
                print(f"  [WARN] laterality_summary failed: {e}")

        # 6. Stacked region distribution (all levels in one plot)
        if "Soma_Region_Hierarchy" in df.columns or any(f"Soma_Level_{level}" in df.columns for level in range(1, 7)):
            try:
                s = str(self.output.get_plot_path("region_dist_stacked"))
                _plot("plot_region_distribution_stacked", df, save_path=s, show=self.show_plots)
            except Exception as e:
                print(f"  [WARN] region_dist_stacked failed: {e}")

        # 7. Projection by soma
        if len(df["Soma_Region"].unique()) > 1:
            try:
                regions = df["Soma_Region"].unique()
                data = [
                    df.loc[df["Soma_Region"] == r, "Total_Length"] for r in regions
                ]
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.boxplot(data, tick_labels=regions)
                ax.set_title("Total reconstruction length by soma region (source unit)")
                plt.xticks(rotation=45)
                plt.tight_layout()
                p = self.output.get_plot_path("projection_by_soma")
                fig.savefig(p, dpi=300, bbox_inches="tight")
                print(f"  [SAVED] {p}")
                if self.show_plots:
                    plt.show()
                plt.close(fig)
            except Exception as e:
                print(f"  [WARN] projection_by_soma failed: {e}")

        print("  Report plots generated.")

    def _write_swc_plots(self, mode: str):
        """Write SWC shapes only when requested. A montage stops after 12 neurons."""
        neurons = list(getattr(self, "neurons", {}).items())
        if not neurons or mode in {None, False, "off"}:
            return
        if mode == "each":
            for neuron_id, neuron in neurons:
                try:
                    safe = str(neuron_id).replace("/", "_")
                    neuron.plot_neuron(
                        save_path=str(self.output.get_swc_plot_path(f"swc_shape_{safe}")),
                        show=False,
                    )
                except Exception as e:
                    print(f"  [WARN] swc_shape failed for {neuron_id}: {e}")
            return
        if mode != "montage":
            raise ValueError("swc_plots must be off, montage, or each")
        limit = 12
        shown = neurons[:limit]
        omitted = len(neurons) - len(shown)
        import io
        import math
        columns = 4 if len(shown) > 4 else max(len(shown), 1)
        rows = math.ceil(len(shown) / columns)
        canvas, axes = plt.subplots(rows, columns, figsize=(4 * columns, 3.2 * rows))
        flat_axes = list(np.atleast_1d(axes).ravel())
        for axis, (neuron_id, neuron) in zip(flat_axes, shown):
            buffer = io.BytesIO()
            neuron.plot_neuron(save_path=buffer, show=False, dpi=80)
            buffer.seek(0)
            axis.imshow(plt.imread(buffer, format="png"))
            axis.set_title(str(neuron_id), fontsize=8)
            axis.axis("off")
        for axis in flat_axes[len(shown):]:
            axis.axis("off")
        title = f"SWC shapes ({len(shown)} shown)"
        if omitted:
            title += f"; {omitted} neurons not drawn"
        canvas.suptitle(title)
        canvas.tight_layout()
        path = self.output.get_swc_plot_path("swc_montage")
        canvas.savefig(path, dpi=120, bbox_inches="tight")
        print(f"  [SAVED] {path}")
        plt.close(canvas)
