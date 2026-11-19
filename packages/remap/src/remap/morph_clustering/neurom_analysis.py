"""NeuroM morphology analysis inside morph_clustering (Blue Brain NeuroM + MorphIO).

This module sits with the FNT workflow under ``morph_clustering``. It does not
run inside the population workbook path. ``neurom>=4.0.0`` is a core ReMAP
dependency (MorphIO comes with NeuroM).

The crop and feature set follow the local Liu→fMOST dendritic bridge conventions
(axon dropped, soma-centred ``r_local`` ball, optional polarity inference when
type-4 apical tags are absent). Feature values are morphometrics only; they do
not establish anatomical or molecular identity.

Version: 0.1.0.dev44 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-09: NeuroM dendritic features beside the region workbook.
- 2026-11-10: Moved under morph_clustering/. No package-root copy.
Status: candidate
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np

DEFAULT_R_LOCAL = 800.0

FEATURE_SCORE_COLS = (
    "n_dendrite_neurites",
    "total_dendrite_length",
    "basal_max_path",
    "apical_max_path",
    "apical_basal_path_ratio",
    "bipolar_path_symmetry",
    "bipolar_length_symmetry",
    "stem_opposition",
    "long_pole_max_path",
    "short_pole_max_path",
    "max_radial_distance_dend",
)


def available() -> bool:
    """True when NeuroM and MorphIO import successfully."""
    try:
        import neurom  # noqa: F401
        import morphio  # noqa: F401
    except ImportError:
        return False
    return True


def require_neurom():
    """Import NeuroM/MorphIO or raise a clear install hint."""
    try:
        import neurom as nm
        from morphio import SectionType, set_maximum_warnings
        from morphio.mut import Morphology as MutMorph
    except ImportError as exc:
        raise ImportError(
            "NeuroM morphology analysis requires neurom>=4.0.0 "
            "(declared in remap package dependencies)"
        ) from exc
    try:
        set_maximum_warnings(0)
    except Exception:
        pass
    return nm, SectionType, MutMorph


def _iter_sections(morph):
    stack = list(morph.root_sections)
    while stack:
        section = stack.pop()
        yield section
        stack.extend(list(section.children))


def crop_morphology(src: Path, r_local: float = DEFAULT_R_LOCAL):
    """Drop axon; keep dendrite inside a soma-centred ball; sanitize unifurcations."""
    _, SectionType, MutMorph = require_neurom()
    mm = MutMorph(str(src))
    for section in list(mm.root_sections):
        if section.type == SectionType.axon:
            mm.delete_section(section, recursive=True)

    center = np.asarray(mm.soma.center, dtype=float)
    changed = True
    while changed:
        changed = False
        for section in list(_iter_sections(mm)):
            p0 = np.asarray(section.points[0][:3], dtype=float)
            if float(np.linalg.norm(p0 - center)) > r_local:
                mm.delete_section(section, recursive=True)
                changed = True
                break

    for section in list(_iter_sections(mm)):
        pts = np.asarray(section.points, dtype=float)
        diams = np.asarray(section.diameters, dtype=float)
        if pts.ndim != 2 or len(pts) == 0:
            continue
        keep_idx: list[int] = []
        cut_at = None
        for i, point in enumerate(pts):
            rd = float(np.linalg.norm(point[:3] - center))
            if rd <= r_local:
                keep_idx.append(i)
            else:
                cut_at = i
                break
        if cut_at is None:
            continue
        if not keep_idx:
            mm.delete_section(section, recursive=True)
            continue
        for child in list(section.children):
            mm.delete_section(child, recursive=True)
        p_in = pts[keep_idx[-1]]
        p_out = pts[cut_at]
        d_in = float(np.linalg.norm(p_in[:3] - center))
        d_out = float(np.linalg.norm(p_out[:3] - center))
        t = float(np.clip((r_local - d_in) / (d_out - d_in + 1e-12), 0.0, 1.0))
        pb = p_in + t * (p_out - p_in)
        db = float(diams[keep_idx[-1]] + t * (diams[cut_at] - diams[keep_idx[-1]]))
        section.points = np.vstack([pts[keep_idx], pb[None, :]])[:, :3]
        section.diameters = np.concatenate([diams[keep_idx], [db]])

    try:
        mm.remove_unifurcations()
    except Exception:
        pass
    return mm


def _neurite_max_path(nm, neurite) -> float:
    try:
        paths = np.asarray(nm.features.get("section_path_distances", neurite), dtype=float)
        return float(paths.max()) if paths.size else float(neurite.length)
    except Exception:
        return float(neurite.length)


def _neurite_root_dir(morph, neurite) -> np.ndarray:
    root = np.asarray(neurite.root_node.points[0][:3], dtype=float)
    soma = np.asarray(morph.soma.center, dtype=float)
    vector = root - soma
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 1e-9 else np.zeros(3)


def _section_cable(section) -> float:
    pts = np.asarray(section.points, dtype=float)
    if pts.ndim != 2 or len(pts) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(pts[:, :3], axis=0), axis=1)))


def _section_max_path(section) -> float:
    pts = np.asarray(section.points, dtype=float)
    here = 0.0
    if pts.ndim == 2 and len(pts) >= 2:
        here = float(np.sum(np.linalg.norm(np.diff(pts[:, :3], axis=0), axis=1)))
    if not section.children:
        return here
    return max(_section_max_path(child) for child in section.children) + here


def _section_root_dir(mm, section) -> np.ndarray:
    root = np.asarray(section.points[0][:3], dtype=float)
    soma = np.asarray(mm.soma.center, dtype=float)
    vector = root - soma
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 1e-9 else np.zeros(3)


def _pick_ven_poles(items: list[dict]) -> tuple[dict | None, dict | None, float]:
    if len(items) < 2:
        return (items[0] if items else None), None, float("nan")
    ranked = sorted(items, key=lambda item: item["max_path"], reverse=True)
    basal = ranked[0]
    best, best_cos = ranked[1], float(np.dot(basal["dir"], ranked[1]["dir"]))
    for item in ranked[1:]:
        cos = float(np.dot(basal["dir"], item["dir"]))
        if cos < best_cos:
            best, best_cos = item, cos
    return basal, best, best_cos


def _has_complete_morph_labels(mm, SectionType) -> bool:
    return any(section.type == SectionType.apical_dendrite for section in _iter_sections(mm))


def _infer_polarity_tags(mm, SectionType) -> None:
    roots = [section for section in mm.root_sections if section.type != SectionType.axon]
    if len(roots) < 2:
        return
    items = [
        {
            "section": section,
            "max_path": _section_max_path(section),
            "dir": _section_root_dir(mm, section),
            "cable": _section_cable(section),
        }
        for section in roots
    ]
    basal, apical, _ = _pick_ven_poles(items)
    if basal is None or apical is None:
        return
    basal["section"].type = SectionType.basal_dendrite
    apical["section"].type = SectionType.apical_dendrite


def extract_features(path, *, r_local: float = DEFAULT_R_LOCAL, source: str = "") -> dict:
    """Crop one ASC/SWC and return the dendritic NeuroM feature row."""
    nm, SectionType, _MutMorph = require_neurom()
    path = Path(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mm = crop_morphology(path, r_local=r_local)
        complete = _has_complete_morph_labels(mm, SectionType)
        if not complete:
            _infer_polarity_tags(mm, SectionType)
        morph = nm.load_morphology(mm)

    dend_types = {nm.BASAL_DENDRITE, nm.APICAL_DENDRITE}
    neurites = [neurite for neurite in morph.neurites if neurite.type in dend_types]
    stems = [
        {
            "type": neurite.type,
            "cable": float(neurite.length),
            "max_path": _neurite_max_path(nm, neurite),
            "dir": _neurite_root_dir(morph, neurite),
        }
        for neurite in neurites
    ]

    basal_len = float(np.sum(nm.features.get("total_length", morph, neurite_type=nm.BASAL_DENDRITE)))
    apical_len = float(np.sum(nm.features.get("total_length", morph, neurite_type=nm.APICAL_DENDRITE)))
    pd_b = np.asarray(nm.features.get("section_path_distances", morph, neurite_type=nm.BASAL_DENDRITE), dtype=float)
    pd_a = np.asarray(nm.features.get("section_path_distances", morph, neurite_type=nm.APICAL_DENDRITE), dtype=float)
    basal_max = float(pd_b.max()) if pd_b.size else 0.0
    apical_max = float(pd_a.max()) if pd_a.size else 0.0
    total_len = basal_len + apical_len

    stem_opposition = float("nan")
    if len(stems) >= 2:
        _, _, stem_opposition = _pick_ven_poles(stems)

    pole_paths = sorted([apical_max, basal_max], reverse=True)
    pole_cables = sorted([apical_len, basal_len], reverse=True)
    long_path = float(pole_paths[0]) if pole_paths else 0.0
    short_path = float(pole_paths[1]) if len(pole_paths) > 1 else 0.0
    long_cable = float(pole_cables[0]) if pole_cables else 0.0
    short_cable = float(pole_cables[1]) if len(pole_cables) > 1 else 0.0
    path_sym = short_path / long_path if long_path > 1e-6 else float("nan")
    len_sym = short_cable / long_cable if long_cable > 1e-6 else float("nan")
    ratio_len = apical_len / basal_len if basal_len > 1e-6 else float("nan")
    ratio_path = apical_max / basal_max if basal_max > 1e-6 else float("nan")

    rd_b = np.asarray(nm.features.get("section_radial_distances", morph, neurite_type=nm.BASAL_DENDRITE), dtype=float)
    rd_a = np.asarray(nm.features.get("section_radial_distances", morph, neurite_type=nm.APICAL_DENDRITE), dtype=float)
    rd_d = np.concatenate([x for x in (rd_b, rd_a) if x.size]) if (rd_b.size or rd_a.size) else np.array([])
    max_rd = float(rd_d.max()) if rd_d.size else 0.0
    n_bif = int(nm.features.get("number_of_bifurcations", morph, neurite_type=nm.BASAL_DENDRITE)) + int(
        nm.features.get("number_of_bifurcations", morph, neurite_type=nm.APICAL_DENDRITE)
    )

    def _finite(value):
        return float(value) if value == value else float("nan")

    return {
        "path": str(path),
        "source": source,
        "backend": f"neurom-{getattr(nm, '__version__', '?')}",
        "r_local_um": r_local,
        "units_um": True,
        "complete_morph_labels": bool(complete),
        "n_dendrite_neurites": int(len(stems)),
        "n_stems": int(len(stems)),
        "total_dendrite_length": float(total_len),
        "apical_length": float(apical_len),
        "basal_length": float(basal_len),
        "apical_max_path": float(apical_max),
        "basal_max_path": float(basal_max),
        "apical_basal_length_ratio": _finite(ratio_len),
        "apical_basal_path_ratio": _finite(ratio_path),
        "long_pole_max_path": long_path,
        "short_pole_max_path": short_path,
        "bipolar_path_symmetry": _finite(path_sym),
        "bipolar_length_symmetry": _finite(len_sym),
        "stem_opposition": _finite(stem_opposition),
        "max_radial_distance_dend": max_rd,
        "n_bifurcations_dend": n_bif,
        "basal_gt_500": bool(basal_max > 500),
    }


def features_table(paths, *, source: str = "", r_local: float = DEFAULT_R_LOCAL):
    """Extract features for many morphology files; failures become error rows."""
    import pandas as pd

    rows = []
    for path in paths:
        try:
            rows.append(extract_features(path, r_local=r_local, source=source))
        except Exception as exc:
            rows.append({"path": str(path), "source": source, "error": str(exc)})
    return pd.DataFrame(rows)
