"""Bounded local terminal inspection plots.

Version: 1.13.0.dev5 (local/unreleased)
Last updated: 2026-11-03
Change history: ../../CHANGELOG.md
Status: candidate visualization; markers do not establish scientific acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone

from .sources import read_swc
from .swc_terminal_candidates import list_terminal_rows, all_leaf_ids


MAX_VOXELS = 64_000_000
SETTING_KEYS = ("width_um", "height_um", "depth_um", "overlay_depth_um",
                "scale_bar_um", "dpi", "sagittal_slab_um", "sagittal_trace_width")
ALIASES = {"context_radius_um": ("width_um", "height_um"),
           "context_depth_radius_um": ("depth_um",),
           "slab_half_depth_um": ("overlay_depth_um",)}


def _review_defaults(review):
    return {"width_um": float(review["context"]["width_um"]),
            "height_um": float(review["context"]["height_um"]),
            "depth_um": float(review["context"]["depth_um"]),
            "overlay_depth_um": float(review["context"]["swc_overlay_depth_um"]),
            "scale_bar_um": float(review["scale_bar_um"]["context"]),
            "dpi": int(review["figure"]["review_dpi"]),
            "sagittal_slab_um": 100.0,
            "sagittal_trace_width": 0.7}


def settings_schema(config=None):
    from .config import resolve_settings as resolve_review_settings
    defaults = _review_defaults(resolve_review_settings("review", config=config))
    effects = {
        "dpi": "Output resolution inherited from review figure.review_dpi.",
        "width_um": "Native context width inherited from review context.width_um.",
        "height_um": "Native context height inherited from review context.height_um.",
        "depth_um": "Native context stack depth inherited from review context.depth_um; sagittal DS stays full plane.",
        "overlay_depth_um": "Raw SWC overlay depth inherited from review context.swc_overlay_depth_um.",
        "scale_bar_um": "Context scale bar inherited from review scale_bar_um.context.",
        "sagittal_slab_um": "Total thickness of raw SWC segments intersecting the full DS sagittal plane.",
        "sagittal_trace_width": "Drawn width in points for the sagittal SWC overlay.",
    }
    return {"schema": "vispa.terminal_inspection.settings.v1", "settings": {
        key: {"default": value, "type": "integer" if key == "dpi" else "positive_number",
              "effect": effects[key]}
        for key, value in defaults.items()}, "aliases": ALIASES,
        "max_voxels": MAX_VOXELS}


def resolve_settings(overrides=(), review_settings=None):
    if review_settings is None:
        from .config import resolve_settings as resolve_review_settings
        review_settings = resolve_review_settings("review")
    result = _review_defaults(review_settings)
    for item in overrides:
        key, sep, value = item.partition("=")
        if not sep or key not in SETTING_KEYS and key not in ALIASES:
            raise ValueError(f"unknown terminal setting {key!r}; see terminal-settings")
        parsed = float(value)
        if not math.isfinite(parsed) or parsed <= 0 or (key == "dpi" and not parsed.is_integer()):
            raise ValueError(f"{key} must be a positive finite {'integer' if key == 'dpi' else 'number'}")
        if key in ALIASES:
            for target in ALIASES[key]:
                result[target] = 2 * parsed
        else:
            result[key] = int(parsed) if key == "dpi" else parsed
    if not 72 <= result["dpi"] <= 600:
        raise ValueError("dpi must be 72–600")
    from .renderers.microscopy_panels import RESOLUTION_LOW
    predicted = math.prod(math.ceil(result[key] / spacing) + 2 for key, spacing in
                          zip(("width_um", "height_um", "depth_um"), RESOLUTION_LOW))
    if predicted > MAX_VOXELS:
        raise ValueError(f"requested context may exceed {MAX_VOXELS:,} voxels ({predicted:,} estimated)")
    return result


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _name(value):
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in value):
        raise ValueError("subject and soma must be simple identifiers")
    return value


def _subject_folder(value):
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+\([A-Za-z0-9_-]+\)_vispa", value):
        raise ValueError("subject folder must look like <sample>(<monkey>)_vispa")
    return value


def _write_soma_metadata(path, subject, soma, frame, root_xyz, raw_swc, sample,
                         subject_folder, monkey_id):
    expected = {"schema": "vispa.soma_folder.v1", "subject": subject, "soma": soma,
                "sample": sample, "subject_folder": subject_folder,
                "monkey_id": monkey_id, "neuron_folder": f"neuron_swc_{soma}",
                "raw_soma_xyz_um": list(root_xyz),
                "raw_swc": str(raw_swc), "raw_swc_sha256": _sha(raw_swc),
                "coordinate_frame": frame, "status": "candidate_visualization"}
    if not path.exists():
        path.write_text(json.dumps({**expected,
            "created_at_utc": datetime.now(timezone.utc).isoformat()}, indent=2)+"\n",
            encoding="utf-8")
    else:
        existing = json.loads(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if key in existing and existing[key] != value:
                raise ValueError(f"existing soma metadata conflicts on {key}")


def _triple(values, label):
    if len(values) != 3 or not all(math.isfinite(float(v)) for v in values):
        raise ValueError(f"{label} requires three finite XYZ numbers")
    return tuple(map(float, values))


def _table_sites(path, source, frame):
    if path is None:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("table must be a JSON object with rows")
    declared = payload.get("coordinate_frame") or payload.get("raw_coordinate_frame")
    if declared is not None and declared != frame:
        raise ValueError(f"table frame {declared!r} differs from image frame {frame!r}")
    sites = []
    for row in payload["rows"]:
        xyz = row.get("raw_xyz_um")
        if xyz is None:
            raise ValueError("table row lacks raw_xyz_um; processed coordinates cannot be placed in raw image")
        sites.append({"node_id": int(row["node_id"]), "xyz_um": _triple(xyz, "table raw_xyz_um"),
                      "region": row.get("region")})
    return sites


def _region_from_table(payload, node_id):
    """Return only the selected terminal row's declared processed-frame region."""
    from .swc_terminal_candidates import region_line
    row = next((site for site in payload if site["node_id"] == node_id), None)
    if row is None:
        return {"status": "unresolved", "label": "unresolved", "source": None}
    region = row.get("region")
    if isinstance(region, str) and region.strip():
        return {"status": "provisional", "label": region.strip(),
                "source": "remap_one_neuron_voxel_match", "region": region.strip(),
                "voxel": row.get("remap_voxel"),
                "match_status": row.get("region_match_status")}
    if not isinstance(region, dict):
        return {"status": "unresolved", "label": "unresolved", "source": None}
    names = region.get("names")
    if not isinstance(names, dict) or not names:
        return {"status": "unresolved", "label": "unresolved", "source": None}
    label = region_line(region)
    return {"status": "provisional", "label": label, "source": "terminal_table_row",
            "region": region}


def _remap_sites(path, raw_tree, processed_swc, sample, soma):
    """Match ReMAP one-neuron voxel rows to unique graph leaves only."""
    import numpy as np
    from .swc_terminal_candidates import pair_processed
    path = Path(path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "remap.one_neuron.v1":
        raise ValueError("ReMAP site input must have schema remap.one_neuron.v1")
    if str(payload.get("sample_id")) != str(sample) or payload.get("neuron_id") != f"{soma}.swc":
        raise ValueError("ReMAP one-neuron sample/neuron identity differs from request")
    expected_hash = (payload.get("source_sha256") or {}).get("swc")
    if not expected_hash or expected_hash != _sha(processed_swc):
        raise ValueError("ReMAP source SWC hash differs from declared processed SWC")
    mapping = payload.get("coordinate_mapping") or {}
    scale = float(mapping.get("source_xyz_divided_by", 0))
    offset = _triple(mapping.get("then_voxel_offset", ()), "ReMAP voxel offset")
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("ReMAP coordinate scale must be positive")
    processed_xyz = pair_processed(raw_tree, read_swc(processed_swc))
    raw_nodes = {node.id: node for node in raw_tree.points}
    leaves = all_leaf_ids(raw_tree)
    by_voxel = {}
    for node_id in leaves:
        voxel = tuple(int(v) for v in np.rint(np.asarray(processed_xyz[node_id])/scale + offset))
        by_voxel.setdefault(voxel, []).append(node_id)
    records = {}
    for entry in payload.get("terminal_sites", []):
        voxel = tuple(int(v) for v in _triple(entry.get("voxel", ()), "ReMAP terminal voxel"))
        records.setdefault(voxel, []).append(entry)
    sites, ambiguous = [], []
    for voxel, rows in records.items():
        candidates = by_voxel.get(voxel, [])
        regions = {str(row.get("region", "")) for row in rows}
        if not candidates or len(regions) != 1:
            ambiguous.append({"voxel": voxel, "candidate_node_ids": candidates,
                              "remap_row_count": len(rows), "status": "unresolved"})
            continue
        if len(rows) != 1 or len(candidates) != 1:
            ambiguous.append({"voxel": voxel, "candidate_node_ids": candidates,
                              "remap_row_count": len(rows),
                              "status": "shared_voxel_same_region"})
        for node_id in candidates:
            sites.append({"node_id": node_id, "xyz_um": raw_nodes[node_id].xyz,
                          "region": next(iter(regions)), "remap_voxel": voxel,
                          "region_match_status": ("unique_voxel" if len(rows) == len(candidates) == 1
                                                  else "shared_voxel_same_region")})
    return sites, {"schema": payload["schema"], "path": str(path), "sha256": _sha(path),
                   "processed_swc": str(processed_swc), "processed_swc_sha256": expected_hash,
                   "source_sha256": payload.get("source_sha256"),
                   "paths": payload.get("paths"),
                   "coordinate_mapping": mapping, "declared_space": payload.get("declared_space"),
                   "atlas_level": payload.get("atlas_level"), "unmatched_or_ambiguous": ambiguous,
                   "status": "provisional_voxel_join; unique graph leaves only"}


def _remap_workbook_regions(path, sample, soma):
    """Read ReMAP population targets without treating region rows as site IDs."""
    from .data_input_adaptor import _workbook_rows
    path = Path(path).resolve()
    rows = _workbook_rows(path, "Terminal_Sites")
    required = {"NeuronID", "Terminal_Region"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("ReMAP Terminal_Sites sheet lacks exact identity/region columns")
    if "SampleID" in rows[0]:
        identity_source = "Terminal_Sites.SampleID"
        exact = [row for row in rows if row["SampleID"] == str(sample)
                 and row["NeuronID"] == f"{soma}.swc"]
    else:
        if not re.fullmatch(re.escape(str(sample)) + r"_(?:FULL|results(?:_\d{8}_\d{6})?)",
                            path.stem, re.IGNORECASE):
            raise ValueError("ReMAP workbook without SampleID must have exact sample-prefixed filename")
        identity_source = "workbook_filename"
        exact = [row for row in rows if row["NeuronID"] == f"{soma}.swc"]
    if not exact:
        raise ValueError("ReMAP Terminal_Sites has no rows for exact sample/neuron")
    regions = sorted({row["Terminal_Region"].strip() for row in exact
                      if row["Terminal_Region"].strip()})
    return {"path": str(path), "sha256": _sha(path), "sample_id": str(sample),
            "sample_identity_source": identity_source,
            "neuron_id": f"{soma}.swc", "row_count": len(exact), "regions": regions,
            "status": "population_region_membership_only; no endpoint node or voxel identity"}


def _sagittal_swc_segments(tree, geometry, crop_jk, slab_i_bounds):
    """Map raw SWC to candidate DS indices and clip each edge to the i slab."""
    from .renderers.microscopy_panels import _out_ijk, _clip_segment_i
    j0, j1, k0, k1 = crop_jk
    low_i, high_i = slab_i_bounds
    by_id = {node.id: node for node in tree.points}
    segments = []
    for node in tree.points:
        parent = by_id.get(node.parent_id)
        if parent is None:
            continue
        p = _out_ijk(node.xyz, "A", geometry)
        q = _out_ijk(parent.xyz, "A", geometry)
        slab = _clip_segment_i(p, q, low_i, high_i)
        if slab is None:
            continue
        display_p = (slab[0][0] - j0, (k1 - 1) - slab[0][1])
        display_q = (slab[1][0] - j0, (k1 - 1) - slab[1][1])
        clipped = _clip_display_segment(display_p, display_q, 0, j1-j0-1, 0, k1-k0-1)
        if clipped is not None:
            segments.append(clipped)
    return segments


def _clip_display_segment(p, q, xmin, xmax, ymin, ymax):
    """Clip a display edge without rounding away a short visible segment."""
    x0, y0 = p
    dx, dy = q[0]-x0, q[1]-y0
    low, high = 0.0, 1.0
    for direction, distance in ((-dx, x0-xmin), (dx, xmax-x0),
                                (-dy, y0-ymin), (dy, ymax-y0)):
        if abs(direction) < 1e-12:
            if distance < 0:
                return None
            continue
        fraction = distance / direction
        if direction < 0:
            low = max(low, fraction)
        else:
            high = min(high, fraction)
        if low > high:
            return None
    return ((x0+low*dx, y0+low*dy), (x0+high*dx, y0+high*dy))


def _configured_panels(image, origin, resolution, tree, target, sites, sample, soma,
                       node_id, swc_path, out_dir, config_path, resolved, terminal_region=None):
    """Use the established VisPa context and full DS sagittal panel renderers."""
    from . import toolkit as tk
    from .config import load
    from .renderers.microscopy_panels import prepare_sagittal_panel
    cfg = load(config_path)
    tk.configure_data_sources(config_path, cfg)
    tool = tk.VisPa(str(sample), cache_dir=str(out_dir / "source_cache"))
    try:
        old_overlay = tk.REVIEW_SETTINGS["context"]["swc_overlay_depth_um"]
        tk.REVIEW_SETTINGS["context"]["swc_overlay_depth_um"] = resolved["overlay_depth_um"]
        try:
            context = tool.plot_widefield_context(
                image, origin, resolution, target, soma,
                suffix=f"TerminalContext{node_id}", swc_tree=tree, output_dir=str(out_dir),
                target_label="Selected terminal", recorded_sites_xyz_um=[s["xyz_um"] for s in sites])
        finally:
            tk.REVIEW_SETTINGS["context"]["swc_overlay_depth_um"] = old_overlay
        context["scale_bar_um"] = resolved["scale_bar_um"]
        context["lock_image_extent"] = True
        region_label = (terminal_region or {}).get("label", "unresolved")
        context["title"] = (f"{sample} | Terminal {node_id} | provisional terminal region: "
                            f"{region_label} | native 5 µm context")
        root_xyz = tree.root.xyz
        prepared = prepare_sagittal_panel(str(sample), str(soma), root_xyz,
                                           swc_path=swc_path, target_node_id=node_id,
                                           slab_thickness_mm=resolved["sagittal_slab_um"] / 1000)
        sagittal = prepared["panel"]
        sagittal["lock_image_extent"] = True
        from .renderers.microscopy_panels import _out_ijk
        geometry = prepared["provenance"]["nifti_geometry"]
        j0,j1,k0,k1 = prepared["provenance"]["crop_jk"]
        low_i, high_i = prepared["provenance"].get("slab_i_bounds", (-float("inf"), float("inf")))
        segments = _sagittal_swc_segments(tree, geometry, (j0,j1,k0,k1), (low_i,high_i))
        sagittal["edge_segments"] = segments
        sagittal["trace_line_width"] = resolved["sagittal_trace_width"]
        sagittal["legend"].append(("line", "red", "raw SWC trace in provisional DS i slab"))
        sagittal["notes"] = [note.replace("no raw-SWC trace is drawn", "raw SWC trace is projected through the declared i slab")
                             for note in sagittal["notes"]]
        prepared["provenance"]["terminal_swc_overlay"] = {
            "mapping": "A", "status": "provisional_raw_swc_to_ds_indices",
            "slab_thickness_um": resolved["sagittal_slab_um"],
            "slab_i_bounds": [low_i, high_i], "segments_drawn": len(segments),
            "line_width_points": resolved["sagittal_trace_width"]}
        for site in sites:
            i, j, k = _out_ijk(site["xyz_um"], "A", geometry)
            if low_i <= i <= high_i and j0 <= j < j1 and k0 <= k < k1:
                sagittal["markers"].append((j-j0,(k1-1)-k,"magenta",12.0,
                                            "Recorded table site", {"site_marker": True}))
        sagittal["legend"].append(("marker", "magenta", "recorded table sites in DS i slab"))
        sagittal["title"] = (f"Full DS sagittal | Terminal {node_id} | provisional terminal region: "
                             f"{region_label} | provisional mapping")
        sagittal["legend"].append(("marker", sagittal["markers"][0][2],
                                   "selected terminal (provisional placement)"))
        rendered = tool.plot_tri_plot([context, sagittal], str(soma), output_dir=str(out_dir),
                                      suffix=f"Terminal{node_id}", legend=True, dpi=resolved["dpi"],
                                      caveats=["Candidate visualization; raw SWC-to-DS mapping unvalidated."])
        return Path(rendered), prepared["provenance"]
    finally:
        tool.close()


def inspect(*, input_path=None, swc_path, subject, soma, node_id, origin=None, resolution=None,
            coordinate_frame="native fMOST raw SWC XYZ", output_root, table_path=None, table_source="vispa",
            sample=None, config_path=None, remap_one_neuron_path=None, processed_swc_path=None,
            remap_workbook_path=None, subject_folder=None,
            leaf_scope="axon", settings=(), dry_run=False):
    """Render one selected terminal using one local ZYX image and raw-frame SWC."""
    import numpy as np
    input_path = Path(input_path).resolve() if input_path else None
    swc_path = Path(swc_path).resolve()
    for path in ((input_path, swc_path) if input_path else (swc_path,)):
        if not path.is_file():
            raise FileNotFoundError(path)
    if input_path and (input_path.suffix.lower() != ".npy" or input_path.stat().st_size > 256 * 1024 * 1024):
        raise ValueError("input must be a local .npy image of at most 256 MiB")
    if input_path is None and not sample:
        raise ValueError("configured image source requires --sample")
    if input_path is None:
        from .config import load
        cfg = load(config_path)
        if str(sample) not in cfg.get("samples", {}):
            raise ValueError(f"sample {sample} is absent from the configured source catalog")
    if not coordinate_frame or table_source not in ("vispa", "remap", "portal"):
        raise ValueError("declare a coordinate frame and table source vispa/remap/portal")
    if remap_one_neuron_path and table_path:
        raise ValueError("select either a normalized table or ReMAP one-neuron JSON")
    if remap_workbook_path and not sample:
        raise ValueError("ReMAP workbook requires exact sample identity")
    if leaf_scope not in ("axon", "all"):
        raise ValueError("leaf scope must be axon or all")
    subject, soma = _name(subject), _name(soma)
    if input_path is None and subject != str(sample):
        raise ValueError("configured subject must equal the exact sample ID")
    monkey_id = (str(cfg["samples"][str(sample)].get("monkey") or "")
                 if input_path is None else "")
    if input_path is None and not monkey_id and not subject_folder:
        raise ValueError("configured sample lacks monkey ID; declare --subject-folder")
    folder_name = (_subject_folder(subject_folder) if subject_folder else
                   _subject_folder(f"{subject}({monkey_id or subject})_vispa"))
    if input_path is None and subject_folder and monkey_id and folder_name != f"{subject}({monkey_id})_vispa":
        raise ValueError("explicit subject folder differs from configured sample/monkey identity")
    neuron_folder = f"neuron_swc_{soma}"
    origin = _triple(origin, "origin") if origin is not None else None
    resolution = _triple(resolution, "resolution") if resolution is not None else None
    if input_path and (origin is None or resolution is None):
        raise ValueError("local input requires origin and resolution")
    if input_path is None and (origin is not None or resolution is not None):
        raise ValueError("configured source determines origin and resolution")
    if resolution is not None and any(v <= 0 for v in resolution):
        raise ValueError("resolution must be positive")
    from .config import resolve_settings as resolve_review_settings
    review = resolve_review_settings("review", config=cfg if input_path is None else None)
    resolved = resolve_settings(settings, review)
    tree = read_swc(swc_path)
    ids = ([row.node_id for row in list_terminal_rows(tree)] if leaf_scope == "axon"
           else all_leaf_ids(tree))
    if node_id not in ids:
        raise ValueError(f"node {node_id} is not a selected childless non-root {leaf_scope} site")
    nodes = {node.id: node for node in tree.points}
    target = nodes[node_id].xyz
    table_path = Path(table_path).resolve() if table_path else None
    remap_provenance = None
    workbook_provenance = (_remap_workbook_regions(remap_workbook_path, sample, soma)
                           if remap_workbook_path else None)
    if remap_one_neuron_path:
        if sample is None:
            raise ValueError("ReMAP one-neuron input requires a sample identity")
        if processed_swc_path is None:
            from .config import load
            cfg = load(config_path)
            root = (cfg.get("sources", {}).get("brain_view") or {}).get("processed_swc_root")
            if root is None:
                raise ValueError("ReMAP one-neuron input requires --processed-swc or configured processed_swc_root")
            processed_swc_path = Path(root) / str(sample) / f"{soma}.swc"
        processed_swc_path = Path(processed_swc_path).resolve()
        sites, remap_provenance = _remap_sites(remap_one_neuron_path, tree,
                                               processed_swc_path, sample, soma)
        table_source = "remap"
    else:
        sites = (_table_sites(table_path, table_source, coordinate_frame) if table_path else
                 [{"node_id": row.node_id, "xyz_um": row.xyz()} for row in list_terminal_rows(tree)])
    matching = next((site for site in sites if site["node_id"] == node_id), None)
    if matching is not None and math.dist(matching["xyz_um"], target) > 1e-3:
        raise ValueError("selected terminal table coordinate differs from raw SWC node")
    terminal_region = _region_from_table(sites, node_id)
    if workbook_provenance and terminal_region["status"] == "provisional":
        membership = terminal_region["label"] in workbook_provenance["regions"]
        terminal_region["remap_workbook_membership"] = membership
    out_dir = Path(output_root).resolve() / folder_name / neuron_folder / "terminals"
    png = out_dir / f"terminal_{node_id:06d}.png"
    receipt = png.with_suffix(".json")
    soma_metadata = out_dir.parent / "metadata.json"
    plan = {"schema": "vispa.terminal_inspection.v1", "created_at_utc": None,
            "subject": subject, "soma": soma, "node_id": node_id,
            "monkey_id": monkey_id, "subject_folder": folder_name,
            "neuron_folder": neuron_folder,
            "candidate_count": len(ids), "leaf_scope": leaf_scope,
            "target_xyz_um": target, "coordinate_frame": coordinate_frame,
            "coordinate_units": "um", "image_order": "ZYX", "origin_xyz_um": origin,
            "resolution_xyz_um": resolution, "settings": resolved,
            "input": str(input_path) if input_path else None, "sample": sample,
            "config_path": str(config_path) if config_path else None,
            "raw_swc": str(swc_path),
            "table": str(table_path) if table_path else None, "table_source": table_source,
            "remap_one_neuron": remap_provenance,
            "remap_workbook": workbook_provenance,
            "recorded_sites": sites,
            "terminal_region": terminal_region,
            "recorded_sites_origin": ("remap_one_neuron_unique_voxel_join" if remap_provenance else
                "external_normalized_table" if table_path else "generated_from_current_raw_swc"),
            "output_png": str(png), "receipt": str(receipt),
            "soma_metadata": str(soma_metadata),
            "dry_run": dry_run, "status": "candidate_visualization"}
    from ._version import __version__
    plan["vispa_version"] = __version__
    plan["operator_sha256"] = _sha(Path(__file__))
    plan["renderer_sha256"] = _sha(Path(__file__).parent / "renderers" / "microscopy_panels.py")
    plan["config_sha256"] = _sha(config_path) if config_path else None
    if input_path is None:
        plan["review_settings"] = review
        plan["review_settings"]["context"]["width_um"] = resolved["width_um"]
        plan["review_settings"]["context"]["height_um"] = resolved["height_um"]
        plan["review_settings"]["context"]["depth_um"] = resolved["depth_um"]
        plan["review_settings"]["context"]["swc_overlay_depth_um"] = resolved["overlay_depth_um"]
        plan["review_settings"]["scale_bar_um"]["context"] = resolved["scale_bar_um"]
        plan["review_settings"]["figure"]["review_dpi"] = resolved["dpi"]
    if soma_metadata.exists():
        _write_soma_metadata(soma_metadata, subject, soma, coordinate_frame,
                             tree.root.xyz, swc_path, sample, folder_name, monkey_id)
    if png.exists() or receipt.exists():
        raise FileExistsError(f"terminal output exists: {png}")
    if dry_run:
        return plan
    input_hash, swc_hash = _sha(input_path) if input_path else None, _sha(swc_path)
    table_hash = _sha(table_path) if table_path else None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if input_path:
        image = np.load(input_path, allow_pickle=False)
    else:
        from .config import load
        from . import toolkit as tk
        cfg = load(config_path)
        tk.configure_data_sources(config_path, cfg)
        Path(output_root).resolve().mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="terminal_source_", dir=Path(output_root).resolve()) as cache:
            tool = tk.VisPa(str(sample), cache_dir=cache)
            width = resolved["width_um"]
            height = resolved["height_um"]
            depth = resolved["depth_um"]
            image, origin, resolution = tool.get_low_res_widefield(
                target, width_um=width, height_um=height, depth_um=depth,
                allow_partial=False)
            plan["source_metadata"] = tool.last_low_res_metadata
            section_records = []
            for entry in plan["source_metadata"]["source_paths"]:
                section = Path(entry["path"])
                section_records.append({"z_index": entry["z_index"],
                    "path": entry["path"],
                    "sha256": _sha(section) if section.is_file() else None,
                    "provenance_status": ("source_hash_recorded" if section.is_file()
                                          else "source_identity_unavailable")})
            plan["source_section_provenance"] = section_records
            tool.close()
        plan["origin_xyz_um"] = origin
        plan["resolution_xyz_um"] = resolution
    if image.ndim != 3 or not image.size or image.size > MAX_VOXELS or not np.issubdtype(image.dtype, np.number) or not np.isfinite(image).all():
        raise ValueError(f"image must be finite numeric ZYX with at most {MAX_VOXELS:,} voxels")
    t = tuple((target[i] - origin[i]) / resolution[i] for i in range(3))
    if any(t[i] < 0 or t[i] >= image.shape[2-i] for i in range(3)):
        raise ValueError("terminal lies outside image bounds")
    if input_path is None:
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"terminal_{node_id}_", dir=out_dir) as stage:
            rendered, sagittal_provenance = _configured_panels(
                image, origin, resolution, tree, target, sites, sample, soma,
                node_id, swc_path, Path(stage), config_path, resolved,
                terminal_region=terminal_region)
            if (_sha(swc_path), _sha(table_path) if table_path else None) != (swc_hash, table_hash):
                raise RuntimeError("SWC or table changed while rendering")
            os.replace(rendered, png)
        _write_soma_metadata(soma_metadata, subject, soma, coordinate_frame,
                             tree.root.xyz, swc_path, sample, folder_name, monkey_id)
        plan.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
                    raw_swc_sha256=swc_hash, table_sha256=table_hash,
                    source_sagittal=sagittal_provenance,
                    output_sha256=_sha(png), image_shape_zyx=list(image.shape))
        receipt.write_text(json.dumps(plan, indent=2, default=str)+"\n", encoding="utf-8")
        return plan
    half = max(1, round(resolved["overlay_depth_um"] / (2 * resolution[2])))
    z = min(image.shape[0]-1, round(t[2])); x = min(image.shape[2]-1, round(t[0]))
    context = image[max(0,z-half):min(image.shape[0],z+half+1)].max(axis=0)
    sagittal = image[:, :, x]
    from matplotlib.collections import LineCollection
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=resolved["dpi"], facecolor="black")
    for ax, plane, coords, labels, radius in (
        (axes[0], context, (t[0],t[1]), ("X", "Y"), resolved["width_um"] / 2),
        (axes[1], sagittal, (t[1],t[2]), ("Y", "Z"), resolved["depth_um"] / 2)):
        lo, hi = np.percentile(plane, (1, 99.5))
        ax.set_facecolor("black")
        ax.imshow(plane, cmap="gray", origin="upper", vmin=lo, vmax=max(hi,lo+1e-9))
        segments = []
        for node in tree.points:
            if node.parent_id == -1:
                continue
            parent = nodes[node.parent_id]
            p = tuple((node.xyz[i]-origin[i])/resolution[i] for i in range(3))
            q = tuple((parent.xyz[i]-origin[i])/resolution[i] for i in range(3))
            if ax is axes[0]:
                if max(abs(p[2]-t[2]), abs(q[2]-t[2]))*resolution[2] > resolved["overlay_depth_um"] / 2:
                    continue
                segment = ((p[0],p[1]),(q[0],q[1]))
            else:
                if max(abs(p[0]-t[0]), abs(q[0]-t[0]))*resolution[0] > resolved["overlay_depth_um"] / 2:
                    continue
                segment = ((p[1],p[2]),(q[1],q[2]))
            segments.append(segment)
        ax.add_collection(LineCollection(segments, colors="#54d569", linewidths=.55, alpha=.85))
        ax.scatter(*coords, s=60, marker="x", color="yellow", linewidths=2, label="Selected SWC leaf")
        for site in sites:
            pos = tuple((site["xyz_um"][i]-origin[i])/resolution[i] for i in range(3))
            xy = (pos[0],pos[1]) if ax is axes[0] else (pos[1],pos[2])
            if ax is axes[1] or abs(pos[2]-t[2])*resolution[2] <= resolved["overlay_depth_um"] / 2:
                ax.scatter(*xy, s=42, marker="o", facecolors="none", edgecolors="cyan", linewidths=1.5)
        ax.set_xlabel(f"{labels[0]} pixel ({resolution[0 if ax is axes[0] else 1]:g} µm)")
        ax.set_ylabel(f"{labels[1]} pixel ({resolution[1 if ax is axes[0] else 2]:g} µm)")
        ax.set_xlim(0, plane.shape[1]-1); ax.set_ylim(plane.shape[0]-1, 0)
        ax.tick_params(colors="white", labelsize=8)
        ax.xaxis.label.set_color("white"); ax.yaxis.label.set_color("white")
        for spine in ax.spines.values():
            spine.set_visible(False)
        bar_px = resolved["scale_bar_um"] / resolution[0 if ax is axes[0] else 1]
        if bar_px < plane.shape[1]*.45:
            left = plane.shape[1]*.06; bottom = plane.shape[0]*.92
            ax.plot([left,left+bar_px], [bottom,bottom], color="white", lw=2)
            ax.text(left, bottom-plane.shape[0]*.025, f'{resolved["scale_bar_um"]:g} µm',
                    color="white", fontsize=8, va="bottom")
    axes[0].set_title("XY context · local Z slab · full image extent")
    axes[1].set_title("YZ sagittal · target X plane · recorded sites projected along X")
    for ax in axes:
        ax.title.set_color("white")
    from matplotlib.lines import Line2D
    legend = fig.legend(handles=[Line2D([],[],color="#54d569",linewidth=.8,label="SWC trace in slab"),
                        Line2D([],[],marker="x",color="yellow",linestyle="None",label="Selected SWC leaf"),
                        Line2D([],[],marker="o",markerfacecolor="none",color="cyan",linestyle="None",label=f"Recorded table site ({table_source})")],
               loc="lower center", ncol=3, facecolor="black", edgecolor="black")
    for label in legend.get_texts(): label.set_color("white")
    fig.suptitle(f"{subject} / soma {soma} / Terminal {node_id} | Provisional region: "
                 f"{terminal_region['label']} | {coordinate_frame}")
    fig._suptitle.set_color("white")
    fig.tight_layout(rect=(0, .07, 1, .94))
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_soma_metadata(soma_metadata, subject, soma, coordinate_frame,
                         tree.root.xyz, swc_path, sample, folder_name, monkey_id)
    fd, temp = tempfile.mkstemp(suffix=".png", dir=out_dir); os.close(fd)
    try:
        fig.savefig(temp)
        plt.close(fig)
        os.replace(temp, png)
        if (_sha(input_path) if input_path else None, _sha(swc_path), _sha(table_path) if table_path else None) != (input_hash, swc_hash, table_hash):
            raise RuntimeError("input changed while rendering")
        plan.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
                    input_sha256=input_hash, raw_swc_sha256=swc_hash,
                    table_sha256=table_hash,
                    output_sha256=_sha(png), image_shape_zyx=list(image.shape), dry_run=False)
        receipt.write_text(json.dumps(plan, indent=2, default=str)+"\n", encoding="utf-8")
    except Exception:
        Path(temp).unlink(missing_ok=True); png.unlink(missing_ok=True)
        raise
    return plan
