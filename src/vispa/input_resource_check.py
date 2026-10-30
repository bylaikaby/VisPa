"""Check whether one VisPa review identity has its configured resources.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import tempfile
from typing import Callable, Mapping


SCHEMA = "vispa.data-check.v1"
_READY_STATES = {"ready", "configured"}


def _path_item(role, label, path, *, kind="file", required=True):
    item = {
        "role": role,
        "label": label,
        "path": str(path) if path else None,
        "required": bool(required),
        "status": "not_configured",
        "detail": "Not configured",
    }
    if not path:
        return item
    candidate = Path(path)
    try:
        exists = candidate.is_file() if kind == "file" else candidate.is_dir()
    except OSError as exc:
        item.update(status="unverified", detail=str(exc))
        return item
    item["status"] = "ready" if exists else "missing"
    item["detail"] = "Found" if exists else f"Missing {kind}"
    return item


def _dependency_item(module, label, *, fallback=None):
    available = importlib.util.find_spec(module) is not None
    if available:
        detail = "Installed"
    elif fallback:
        detail = fallback
    else:
        detail = "Required package is not installed"
    return {
        "role": f"dependency:{module}",
        "label": label,
        "path": None,
        "required": True,
        "status": "ready" if available or fallback else "missing",
        "detail": detail,
    }


def _cache_item(path):
    root = Path(path)
    item = {
        "role": "download_cache",
        "label": "Download cache",
        "path": str(root),
        "required": True,
        "status": "missing",
        "detail": "Cache parent is unavailable",
    }
    probe_root = root
    while not probe_root.exists() and probe_root.parent != probe_root:
        probe_root = probe_root.parent
    try:
        probe_root.mkdir(parents=True, exist_ok=True) if probe_root == root else None
        with tempfile.NamedTemporaryFile(
                prefix=".vispa_data_check_", dir=probe_root, delete=True):
            pass
    except OSError as exc:
        item["detail"] = f"Write check failed: {exc}"
    else:
        item.update(
            status="ready",
            detail="Writable" if root.exists() else f"Writable; will create {root}",
        )
    return item


def _configured_item(role, label, value, detail):
    return {
        "role": role,
        "label": label,
        "path": str(value) if value else None,
        "required": True,
        "status": "configured" if value else "not_configured",
        "detail": detail if value else "Not configured",
    }


def data_check(config=None, sample_id=None, neuron_id=None,
               progress: Callable[[int, int], None] | None = None) -> dict:
    """Return a deterministic, read-only readiness report for one identity."""
    if config is None or isinstance(config, (str, os.PathLike)):
        from .config import load
        config = load(config)
    if not isinstance(config, Mapping):
        raise TypeError("config must be a loaded VisPa mapping or JSON/YAML path")

    ui = config.get("visual_toolkit") or {}
    sample = str(sample_id or ui.get("default_sample") or "").strip()
    neuron = str(neuron_id or ui.get("default_neuron") or "").strip()
    if neuron and not neuron.lower().endswith(".swc"):
        neuron += ".swc"
    sample_row = (config.get("samples") or {}).get(sample) or {}
    defaults = config.get("defaults") or {}
    sources = config.get("sources") or {}
    brain = sources.get("brain_view") or {}
    fnt = ui.get("fnt_tracer") or {}

    items = []
    total = 15 + int(brain.get("region_mesh_root") is not None) \
        + int(brain.get("region_manifest") is not None)

    def add(item):
        items.append(item)
        if progress is not None:
            progress(len(items), total)

    add({
            "role": "config",
            "label": "Configuration",
            "path": str(config.get("path") or ""),
            "required": True,
            "status": "ready" if config.get("path") else "ready",
            "detail": "Loaded and validated",
        })
    add(_dependency_item("numpy", "NumPy"))
    add(_dependency_item("matplotlib", "Matplotlib"))
    add(_dependency_item("PIL", "Pillow"))
    add(_dependency_item("tifffile", "TIFF reader", fallback="Pillow fallback available"))
    add(_dependency_item("imagecodecs", "Extended TIFF codecs", fallback="Pillow fallback available"))

    manifest_path = sources.get("dataset_manifest")
    if manifest_path:
        from .data_input_adaptor import plan_manifest_selected_ds00
        selected_path = None
        try:
            selection = plan_manifest_selected_ds00(
                sample, manifest_path, defaults.get("ds00_root"))
            selected_path = selection["source"]["path"]
            ds00_item = _path_item("ds00", "DS00 image", selected_path)
            ds00_item["detail"] = ("Manifest selected source present; image checksum declared, "
                                   "not verified by metadata-only readiness")
            ds00_item["manifest_path"] = selection["manifest_path"]
            ds00_item["selection_basis"] = "dataset manifest"
            ds00_item["configured_reference_path"] = (
                str(sample_row["ds00_processed"]) if sample_row.get("ds00_processed") else None)
            ds00_item["declared_sha256"] = selection["declared_sha256"]
            ds00_item["checksum_verified"] = False
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            ds00_item = {"role": "ds00", "label": "DS00 image", "path": selected_path,
                         "required": True, "status": "missing",
                         "detail": f"Manifest selected DS00 unavailable: {exc}",
                         "manifest_path": str(manifest_path), "checksum_verified": False}
        add(ds00_item)
    else:
        add(_path_item("ds00", "DS00 image", sample_row.get("ds00_processed")))
    add(_path_item(
        "resample_5um", "5 um Context sections", sample_row.get("resample_5um"), kind="dir"))

    highres_cache = Path(defaults.get("cache_root") or "") / sample / "high_res_http" if defaults.get("cache_root") else None
    highres_cache_ready = bool(highres_cache and highres_cache.is_dir())
    highres_host = sources.get("http_base_url") or sources.get("http_host")
    add(_configured_item(
        "highres_source", "High-resolution Soma source",
        highres_host or highres_cache,
        "HTTP source configured; online reachability is checked on acquisition"
        if highres_host else "Local high-resolution cache configured",
    ))

    raw_root = sources.get("legacy_raw_swc_root")
    raw_local = Path(raw_root) / sample if raw_root and sample else None
    raw_file = raw_local / neuron if raw_local and neuron else None
    portal_swc = bool(sources.get("http_host") and sources.get("raw_swc_base"))
    if raw_file and raw_file.is_file():
        add(_path_item("raw_swc", "Raw SWC", raw_file))
    elif portal_swc:
        add({"role": "raw_swc_retrieval", "label": "Raw SWC retrieval",
             "path": str(raw_file) if raw_file else None, "required": True,
             "status": "missing", "detail":
             f"Portal configured but native raw SWC {neuron or 'neuron'} is not cached; retrieval required"})
    else:
        add(_path_item("raw_swc", "Raw SWC", raw_file))

    cache_root = defaults.get("cache_root")
    if cache_root:
        add(_cache_item(cache_root))
    else:
        user_data = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
        add(_cache_item(user_data / "VisPa" / "cache"))

    add(_path_item("brain_mesh", "Brain-view mesh", brain.get("mesh_path")))
    if brain.get("region_mesh_root") is not None:
        add(_path_item("region_mesh_root", "Brain-view region meshes",
                       brain.get("region_mesh_root"), kind="directory"))
    if brain.get("region_manifest") is not None:
        add(_path_item("region_manifest", "Brain-view region manifest",
                       brain.get("region_manifest")))
    swc_root = brain.get("processed_swc_root")
    processed_swc = Path(swc_root) / sample / neuron if swc_root and sample and neuron else None
    add(_path_item("processed_swc", "Brain-view processed SWC", processed_swc))
    add(_path_item("fnt_executable", "FNT executable", fnt.get("executable")))
    from .fnt_tracer_launcher import swc_fnt_tracer
    try:
        route = swc_fnt_tracer(config, sample, neuron, dry_run=True) if sample and neuron else None
        fnt_error = None
    except (OSError, ValueError) as exc:
        route, fnt_error = None, str(exc)
    add({"role": "fnt_native", "label": "FNT tools",
         "path": route["converter"] if route else None,
         "launch_mode": "legacy_fnt_tools", "required": True,
         "status": "configured" if route else "missing",
         "detail": "Legacy FNT tools configured; fresh raw SWC can be prepared at launch (network/pixels unverified)"
                   if route else fnt_error or "Select a sample and neuron"})

    issues = [item for item in items if item["required"] and item["status"] not in _READY_STATES]
    ready = not issues
    lines = [
        f"[{'OK' if item['status'] in _READY_STATES else 'MISSING'}] {item['label']}: "
        f"{item['detail']}" + (f" | {item['path']}" if item.get("path") else "")
        for item in items
    ]
    return {
        "schema": SCHEMA,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "sample_id": sample or None,
        "neuron_id": neuron or None,
        "ready": ready,
        "checked": total,
        "issues": len(issues),
        "checks": items,
        "checklist": lines,
        "summary": (
            f"All configured resources ready ({total}/{total})\n"
            "Remote services are verified when their data is first requested."
            if ready else
            f"{len(issues)} required resource(s) need attention"
        ),
        "limits": [
            "Readiness checks local existence, configuration and cache writability.",
            "Remote image, catalog and FNT availability is not contacted by this check.",
            "Resource readiness does not establish anatomical or scientific acceptance.",
        ],
    }


check = data_check
