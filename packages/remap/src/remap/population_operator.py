"""Run the source Step1 population workflow on explicitly declared local files.

Version: 0.2.1 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-10-25: Step1 population plan and workbook receipt.
- 2026-11-10: Stable animal folder (neuron_table/, report/report_plots, swc_plots). Optional summary plots and SWC montage/each.
- 2026-11-10: Omitted atlas paths come from the designated fMOST profile. Cross-drive registration paths no longer drop the receipt.
Status: candidate

Omitted atlas, atlas key, and hemisphere mask use the designated fMOST share
DEB profile. Template and hierarchy CSVs stay in the caller config.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd

from . import __version__
from .atlas_profile import (
    NOT_DESIGNATED,
    apply_designated_atlas,
    atlas_profile_record,
    designated_atlas_version,
    designated_coordinate_scale_um,
)
from .registration_path import legacy_registration_path
from .run_analysis import sha256
from .region_analysis import PopulationRegionAnalysis
from .region_analysis.neuron_table import AtlasHemisphereReference


INPUT_NAMES = ("atlas", "atlas_key", "template", "hemisphere_mask",
               "cortex_hierarchy_csv", "subcortical_hierarchy_csv")


def plan_population(config: dict, *, neuron_ids=None) -> dict:
    """Preflight exact inputs and hashes without parsing volumes or writing output."""
    if not isinstance(config, dict):
        raise ValueError("population config must be a JSON object")
    allowed = {"sample_id", "neuron_ids", "swc_source_dir", *INPUT_NAMES, "output_base",
               "atlas_level", "source_date", "registry_path", "source_id", "generate_plots",
               "swc_plots",
               "coordinate_scale", "coordinate_offset", "declared_space", "source_units",
               "refined_soma", "iondata_host", "refresh_swc"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"Unknown population config parameters: {sorted(unknown)}")
    supplied_atlas = [
        key for key in ("atlas", "atlas_key", "hemisphere_mask")
        if key in config and config[key] is not None
    ]
    config = apply_designated_atlas(config)
    missing = [name for name in NOT_DESIGNATED
               if not isinstance(config.get(name), str) or not config[name].strip()]
    if missing:
        raise ValueError(
            "Population config must set "
            + ", ".join(missing)
            + ". The designated DEB share profile supplies atlas, atlas_key, and hemisphere_mask")
    scale = designated_coordinate_scale_um()
    if config.get("coordinate_scale", scale) != scale or config.get("coordinate_offset", [0, 0, 0]) != [0, 0, 0]:
        raise ValueError("Full Step1 local tracer supports only source XYZ / 250 with zero offset")
    declared_space = config.get(
        "declared_space", f"{designated_atlas_version()} atlas voxel index (caller declaration)")
    if not isinstance(declared_space, str) or not declared_space.strip():
        raise ValueError("declared_space must be nonempty")
    source_units = config.get("source_units")
    if source_units is not None and (not isinstance(source_units, str) or not source_units.strip()):
        raise ValueError("source_units must be null or a nonempty caller declaration")
    swc_plots = config.get("swc_plots", "off")
    if swc_plots is False:
        swc_plots = "off"
    if swc_plots not in {"off", "montage", "each"}:
        raise ValueError("swc_plots must be off, montage, or each")
    sample = config.get("sample_id")
    if not isinstance(sample, str) or not sample or sample != sample.strip() or Path(sample).name != sample:
        raise ValueError("sample_id must be one exact, nonempty directory-safe identity")
    ids = neuron_ids if neuron_ids is not None else config.get("neuron_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(v, str) or not v.endswith(".swc")
                                                 or Path(v).name != v or v != v.strip() for v in ids):
        raise ValueError("neuron_ids must be a nonempty list of exact SWC basenames")
    if len(ids) != len(set(ids)):
        raise ValueError("neuron_ids must be unique")
    level = config.get("atlas_level", 6)
    if isinstance(level, bool) or not isinstance(level, int) or level != 6:
        raise ValueError("Full Step1 population contract currently uses atlas_level=6")
    source_date = config.get("source_date")
    if source_date is not None:
        try:
            if len(source_date) != 8 or date.fromisoformat(f"{source_date[:4]}-{source_date[4:6]}-{source_date[6:]}").strftime("%Y%m%d") != source_date:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("source_date must be YYYYMMDD or null") from exc
    root = Path(config["swc_source_dir"])
    if root.exists():
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("swc cache must be a directory")
    elif config.get("iondata_host"):
        root = root.resolve()
    else:
        raise ValueError("swc cache directory does not exist")
    inputs = {name: Path(config[name]).resolve(strict=True) for name in INPUT_NAMES}
    if config.get("refined_soma") is not None:
        inputs["refined_soma"] = Path(config["refined_soma"]).resolve(strict=True)
    swcs = {name: (root / name).resolve() for name in ids}
    if any(path.parent != root for path in swcs.values()):
        raise ValueError("Every selected SWC must remain inside swc_source_dir")
    if not config.get("iondata_host") and any(not path.is_file() for path in swcs.values()):
        raise ValueError("Every selected SWC must already be in the cache, or iondata_host must be set")
    iondata_host = str(config["iondata_host"]).rstrip("/") if config.get("iondata_host") else None
    refresh_swc = bool(config.get("refresh_swc", False))
    if refresh_swc and not iondata_host:
        raise ValueError("refresh_swc requires iondata_host")
    if any(not path.is_file() for path in inputs.values()):
        raise ValueError("Population scientific inputs must be files")
    output_base = Path(config["output_base"]).resolve()
    if output_base == root or root in output_base.parents:
        raise ValueError("output_base must not be inside the SWC source directory")
    if any(output_base == path.parent or path.parent in output_base.parents for path in inputs.values()):
        raise ValueError("output_base must not be inside a scientific input directory")
    registry = config.get("registry_path")
    if registry is not None:
        registry_path = Path(registry).resolve()
        boundary = registry_path.parent
        if boundary.name == "data_progress" and boundary.parent.name == "group_analysis":
            boundary = boundary.parent.parent
        if output_base == boundary or boundary in output_base.parents:
            raise ValueError("output_base must be outside the declared legacy PA registry workspace")
        registry = str(registry_path)
    source_id = config.get("source_id", f"remap_neurons_{sample}")
    if not isinstance(source_id, str) or not source_id or not all(c.isalnum() or c == "_" for c in source_id):
        raise ValueError("source_id must contain only letters, numbers, and underscores")
    return {"schema": "remap.population_plan.v1", "version": __version__,
            "atlas_profile": atlas_profile_record(overrides=supplied_atlas),
            "sample_id": sample, "neuron_ids": ids, "atlas_level": level,
            "swc_source_dir": str(root),
            "iondata_host": iondata_host,
            "refresh_swc": refresh_swc,
            "source_date": source_date,
            "source_id": source_id, "registry_path": registry,
            "output_base": str(output_base), "generate_plots": bool(config.get("generate_plots", False)),
            "swc_plots": swc_plots,
            "declared_space": declared_space, "source_units": source_units,
            "coordinate_mapping": {"source_xyz_divided_by": 250, "then_voxel_offset": [0, 0, 0],
                                   "affine_applied": False},
            "inputs": {name: {"path": str(path), "sha256": sha256(path)} for name, path in inputs.items()},
            "swcs": {name: {"path": str(path), "sha256": sha256(path) if path.is_file() else None,
                             "fetch_required": (not path.is_file()) or refresh_swc}
                     for name, path in swcs.items()}}


def run_population(plan: dict) -> dict:
    """Execute original population formulas, then emit a manager registration receipt."""
    for item in list(plan["inputs"].values()) + list(plan["swcs"].values()):
        if item["sha256"] is not None and sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Input changed after preflight: {item['path']}")
    paths = {key: value["path"] for key, value in plan["inputs"].items()}
    atlas_img = nib.load(paths["atlas"])
    atlas = np.asanyarray(atlas_img.dataobj)
    if atlas.ndim != 5 or atlas.shape[3] != 1 or atlas.shape[4] < 6:
        raise ValueError("Full Step1 contract requires a 5D atlas with level 6")
    selected = atlas[:, :, :, 0, 5]
    if any(v == 0 for v in selected.shape) or not np.isfinite(selected).all() or (selected < 0).any() or not np.equal(selected, np.floor(selected)).all():
        raise ValueError("Selected atlas labels must be finite nonnegative integers")
    key = pd.read_csv(paths["atlas_key"], sep="\t")
    reference = AtlasHemisphereReference.from_files(paths["hemisphere_mask"], paths["atlas"],
                                                   paths["atlas_key"], level=6)
    sample = plan["sample_id"]
    pop = PopulationRegionAnalysis(
        sample_id=sample, atlas=atlas, atlas_table=key,
        template_img=nib.load(paths["template"]), nii_space="monkey",
        arm_key_path=paths["atlas_key"], cortex_hierarchy_csv=paths["cortex_hierarchy_csv"],
        subcortical_hierarchy_csv=paths["subcortical_hierarchy_csv"],
        output_base=plan["output_base"], create_output_folder=True, show_plots=False,
        neuron_list=[{"sampleid": sample, "name": name} for name in plan["neuron_ids"]],
        swc_source_dir=plan["swc_source_dir"],
        iondata_host=plan.get("iondata_host"), refresh_swc=bool(plan.get("refresh_swc", False)),
        hemisphere_reference=reference)
    pop.process(neuron_id=plan["neuron_ids"], level=6)
    if pop.load_failures or len(pop.plot_dataframe) != len(plan["neuron_ids"]):
        raise RuntimeError(f"Full population processing incomplete: {pop.load_failures}")
    for name in plan["neuron_ids"]:
        path = Path(plan["swc_source_dir"]) / name
        if not path.is_file():
            raise RuntimeError(f"SWC was not cached: {sample}/{name}")
        current = sha256(path)
        entry = plan["swcs"][name]
        if entry["sha256"] != current:
            entry["path"] = str(path)
            entry["sha256"] = current
            entry["fetch_required"] = True
    if "refined_soma" in paths:
        labels = pd.read_excel(paths["refined_soma"], sheet_name="Summary")
        if not {"NeuronID", "Soma_Region"}.issubset(labels) or labels.NeuronID.isna().any() or labels.NeuronID.duplicated().any():
            raise ValueError("Refined soma Summary requires unique NeuronID and Soma_Region")
        if "SampleID" in labels and not labels.SampleID.astype(str).eq(sample).all():
            raise ValueError("Refined soma labels contain another sample")
        if labels.Soma_Region.isna().any():
            raise ValueError("Refined soma labels must be present")
        source = f"{paths['refined_soma']}:sha256={plan['inputs']['refined_soma']['sha256']}"
        pop.apply_soma_labels(dict(zip(labels.NeuronID.astype(str), labels.Soma_Region)), source)
    output_dir = Path(pop.save_all(include_strength_levels=[3],
                                   generate_plots=plan["generate_plots"],
                                   swc_plots=plan.get("swc_plots", "off")))
    workbook = output_dir / "neuron_table" / f"{sample}_results.xlsx"
    summary = pd.read_excel(workbook, sheet_name="Summary")
    if list(summary["SampleID"].astype(str)) != [sample] * len(plan["neuron_ids"]) or list(summary["NeuronID"]) != plan["neuron_ids"]:
        raise ValueError("Workbook Summary identity or order differs from the requested cohort")
    columns = [str(column) for column in summary.columns if not str(column).startswith("review_")]
    hierarchy = pd.read_excel(workbook, sheet_name="Soma_Hierarchy")
    if list(hierarchy["SampleID"].astype(str)) != [sample] * len(plan["neuron_ids"]) or list(hierarchy["NeuronID"]) != plan["neuron_ids"]:
        raise ValueError("Workbook Soma_Hierarchy identity or order differs from requested cohort")
    hierarchy_columns = ["SampleID", "NeuronID", *[f"L{i}" for i in range(1, 7) if f"L{i}" in hierarchy]]
    if len(hierarchy_columns) != 8:
        raise ValueError("Workbook Soma_Hierarchy requires L1 through L6")
    entry = {"id": plan["source_id"], "role": "analysis", "producer": "remap",
             "path": legacy_registration_path(workbook, Path(plan["registry_path"]).parent) if plan["registry_path"] else None,
             "source_date": plan["source_date"], "format": "xlsx", "sheet": "Summary",
             "sample_column": "SampleID", "neuron_column": "NeuronID", "columns": columns}
    hierarchy_entry = {**entry, "id": f"remap_hierarchy_{sample}", "sheet": "Soma_Hierarchy",
                       "columns": hierarchy_columns}
    if hierarchy_entry["id"] == entry["id"]:
        raise ValueError("Summary and hierarchy registration source IDs must differ")
    with pd.ExcelFile(workbook) as book:
        sheets = book.sheet_names
    projection_sheets = {name: ("display log10(retained voxel length + 1)" if "Strength" in name
                                else "retained atlas-voxel edge length")
                         for name in sheets if name.startswith("Projection_")}
    receipt = {"schema": "remap.population_receipt.v1", "version": __version__,
               "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "plan": plan, "workbook": str(workbook.resolve()), "workbook_sha256": sha256(workbook),
               "sheets": sheets, "rows": len(summary),
               "registration_entry": entry, "registrations": [entry, hierarchy_entry],
               "projection_sheet_metrics": projection_sheets,
               "registration_status": "candidate only; legacy PA registry not modified",
               "anatomical_registration_acceptance": "not established by this software run"}
    receipt_path = output_dir / "report" / "run_provenance.json"
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    receipt["receipt"] = str(receipt_path.resolve())
    return receipt
