"""Generic DS00 five-view volume renderer, extracted without changing its defaults.

Version: 1.12.0.dev1 (local/unreleased)
Last updated: 2026-10-29
Change history: ../../CHANGELOG.md
Status: candidate

The renderer accepts an explicit LPS NIfTI input. It does not select cohorts,
resolve project paths, or apply a transform beyond the input NIfTI affine.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

VIEW_KEYS = ("frontal", "superior", "back", "bottom", "coronal")
VIEW_TITLES = ("Frontal", "Superior", "Posterior", "Inferior", "Coronal")

from ..config import (MONTAGE_DEFAULT_SETTINGS as DEFAULT_SETTINGS,
                     MONTAGE_SETTING_SPECS as SETTING_SPECS,
                     resolve_montage_settings as resolve_settings)


def _require_nibabel():
    try:
        import nibabel
    except ImportError as exc:
        raise RuntimeError("NIfTI montage rendering requires the 'nifti' optional dependency (nibabel)") from exc
    return nibabel


def unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0.0:
        raise ValueError("zero vector")
    return v / n


def otsu_threshold(values: np.ndarray, settings: Mapping[str, Any] | None = None) -> float:
    settings = resolve_settings(settings)
    hi = np.percentile(values, settings["otsu_clip_percentile"])
    x = values[values < hi]
    if x.size < 100:
        return float(np.percentile(values, 70))
    hist, edges = np.histogram(x, bins=256)
    prob = hist.astype(np.float64)
    total = prob.sum()
    if total <= 0:
        return float(np.percentile(values, 70))
    prob /= total
    omega = np.cumsum(prob)
    centers = (edges[:-1] + edges[1:]) * 0.5
    mu = np.cumsum(prob * centers)
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    sigma = np.zeros_like(mu)
    ok = denom > 1e-12
    sigma[ok] = (mu_t * omega[ok] - mu[ok]) ** 2 / denom[ok]
    return float(centers[int(np.argmax(sigma))])


def anatomical_axes(affine: np.ndarray) -> dict[str, np.ndarray]:
    """Directions from the NIfTI affine; require the original LPS convention."""
    nib = _require_nibabel()
    codes = nib.aff2axcodes(affine)
    if codes != ("L", "P", "S"):
        raise RuntimeError(f"expected LPS axcodes, got {codes}")
    col = affine[:3, :3]
    left = unit(col[:, 0])
    posterior = unit(col[:, 1])
    superior = unit(col[:, 2])
    return {
        "left": left,
        "right": -left,
        "posterior": posterior,
        "anterior": -posterior,
        "superior": superior,
        "inferior": -superior,
    }


def view_forward_up(axes: dict[str, np.ndarray], name: str) -> tuple[np.ndarray, np.ndarray]:
    """Return the preserved camera basis for one named view."""
    if name == "frontal":
        forward, up = axes["posterior"], axes["superior"]
    elif name == "superior":
        forward, up = axes["inferior"], axes["anterior"]
    elif name == "back":
        forward, up = axes["anterior"], axes["superior"]
    elif name == "bottom":
        forward, up = axes["superior"], axes["anterior"]
    elif name == "coronal":
        forward = unit(0.72 * axes["posterior"] + 1.05 * axes["left"])
        up = axes["superior"]
    else:
        raise KeyError(name)
    forward = unit(forward)
    up = up - np.dot(up, forward) * forward
    up = unit(up)
    return forward, up


def view_axis_labels(affine: np.ndarray, name: str) -> tuple[str, str]:
    """Describe increasing projected coordinates using their LPS directions."""
    axes = anatomical_axes(affine)
    forward, up = view_forward_up(axes, name)
    right = unit(np.cross(up, forward))
    up = unit(np.cross(forward, right))
    cardinals = (
        ("Left", np.array([-1.0, 0.0, 0.0])),
        ("Right", np.array([1.0, 0.0, 0.0])),
        ("Posterior", np.array([0.0, -1.0, 0.0])),
        ("Anterior", np.array([0.0, 1.0, 0.0])),
        ("Inferior", np.array([0.0, 0.0, -1.0])),
        ("Superior", np.array([0.0, 0.0, 1.0])),
    )

    def direction(vector: np.ndarray) -> tuple[str, str, bool]:
        components = [(label, float(np.dot(vector, basis))) for label, basis in cardinals]
        cutoff = max(abs(value) for _, value in components) * 0.05
        start = [label for label, value in components if value < -cutoff]
        end = [label for label, value in components if value > cutoff]
        if not start or not end:
            raise RuntimeError("could not derive projected anatomical axis labels")
        oblique = len(start) > 1 or len(end) > 1
        return " + ".join(start), " + ".join(end), oblique

    labels = []
    for vector in (right, up):
        start, end, oblique = direction(vector)
        if oblique:
            labels.append(f"{start} →\n{end} (oblique; RAS+ mm)")
        else:
            labels.append(f"{start} → {end} (RAS+ mm)")
    return labels[0], labels[1]


def load_windowed(path: Path, settings: Mapping[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray, float, float]:
    settings = resolve_settings(settings)
    nib = _require_nibabel()
    try:
        from scipy.ndimage import gaussian_filter
    except ImportError as exc:
        raise RuntimeError("NIfTI montage rendering requires the 'montage' optional dependency (scipy)") from exc
    img = nib.load(str(path))
    affine = np.asarray(img.affine, dtype=np.float64)
    anatomical_axes(affine)
    stride = max(1, int(np.ceil(max(img.shape) / settings["max_dimension"])))
    full = np.asarray(img.dataobj, dtype=np.float32)
    data = full[::stride, ::stride, ::stride].copy()
    del full
    aff = affine.copy()
    aff[:3, :3] *= stride
    thr = otsu_threshold(data.ravel()[::settings["otsu_sample_stride"]], settings)
    hi = float(np.percentile(data, settings["intensity_high_percentile"]))
    if hi <= thr + settings["minimum_intensity_span"]:
        hi = thr + settings["minimum_intensity_span"]
    vol = np.clip((data - thr) / (hi - thr), 0.0, 1.0)
    vol = gaussian_filter(vol, sigma=settings["blur_sigma_voxels"])
    print(
        f"{Path(path).name} shape={img.shape} stride={stride} down={vol.shape} "
        f"thr={thr:.1f} hi={hi:.1f}",
        flush=True,
    )
    return vol, aff, thr, hi


def foreground_world(vol: np.ndarray, aff: np.ndarray, settings: Mapping[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray]:
    settings = resolve_settings(settings)
    mask = vol > settings["foreground_threshold"]
    sel = np.flatnonzero(mask)
    if sel.size < settings["min_foreground_voxels"]:
        raise RuntimeError("foreground too small")
    if sel.size > settings["max_foreground_points"]:
        step = int(np.ceil(sel.size / settings["max_foreground_points"]))
        sel = sel[::step]
    ii, jj, kk = np.unravel_index(sel, vol.shape)
    hom = np.stack(
        [ii.astype(np.float64), jj.astype(np.float64), kk.astype(np.float64), np.ones(ii.shape[0])],
        axis=0,
    )
    world = (aff @ hom)[:3]
    w = vol[ii, jj, kk].astype(np.float64)
    centroid = (world * w[None, :]).sum(axis=1) / w.sum()
    return world, centroid


def full_volume_projection_bounds(
    shape: tuple[int, int, int], aff: np.ndarray, centroid: np.ndarray,
    forward: np.ndarray, up: np.ndarray,
) -> tuple[float, float, float, float, float, float]:
    """Project all source voxel-cell corners, including the outer half voxels."""
    right = unit(np.cross(up, forward))
    up = unit(np.cross(forward, right))
    corners = np.array([[i, j, k, 1.0]
                        for i in (-0.5, shape[0] - 0.5)
                        for j in (-0.5, shape[1] - 0.5)
                        for k in (-0.5, shape[2] - 0.5)], dtype=np.float64).T
    delta = (aff @ corners)[:3] - centroid[:, None]
    u, v, depth = right @ delta, up @ delta, forward @ delta
    return (float(u.min()), float(u.max()), float(v.min()), float(v.max()),
            float(depth.min()), float(depth.max()))


def composite_view(
    vol: np.ndarray,
    aff: np.ndarray,
    world: np.ndarray,
    centroid: np.ndarray,
    forward: np.ndarray,
    up: np.ndarray,
    projection_bounds: tuple[float, float, float, float, float, float] | None = None,
    settings: Mapping[str, Any] | None = None,
    return_metadata: bool = False,
) -> np.ndarray | tuple[np.ndarray, dict[str, Any]]:
    settings = resolve_settings(settings)
    try:
        from scipy.ndimage import map_coordinates
    except ImportError as exc:
        raise RuntimeError("NIfTI montage rendering requires the 'montage' optional dependency (scipy)") from exc
    right = unit(np.cross(up, forward))
    up = unit(np.cross(forward, right))
    delta = world - centroid[:, None]
    u = right @ delta
    v = up @ delta
    depth = forward @ delta
    if projection_bounds is None:
        u0, u1 = np.percentile(u, settings["view_extent_percentiles"])
        v0, v1 = np.percentile(v, settings["view_extent_percentiles"])
        d0, d1 = np.percentile(depth, settings["depth_percentiles"])
        pad_u = settings["projection_padding_fraction"] * (u1 - u0)
        pad_v = settings["projection_padding_fraction"] * (v1 - v0)
        u0, u1 = u0 - pad_u, u1 + pad_u
        v0, v1 = v0 - pad_v, v1 + pad_v
    else:
        u0, u1, v0, v1, d0, d1 = projection_bounds
    if min(u1 - u0, v1 - v0, d1 - d0) < settings["minimum_extent_mm"]:
        raise RuntimeError("degenerate view extent")

    bin_mm = settings["projection_bin_mm"]
    h_min, h_max = settings["horizontal_bins_px"]
    v_min, v_max = settings["vertical_bins_px"]
    d_min, d_max = settings["depth_bins"]
    nu = int(np.clip(np.round((u1 - u0) / bin_mm), h_min, h_max))
    nv = int(np.clip(np.round((v1 - v0) / bin_mm), v_min, v_max))
    nd = int(np.clip(np.round((d1 - d0) / settings["depth_step_mm"]), d_min, d_max))
    us = np.linspace(u0, u1, nu)
    vs = np.linspace(v0, v1, nv)
    ds = np.linspace(d0, d1, nd)
    uu, vv = np.meshgrid(us, vs, indexing="xy")
    inv_aff = np.linalg.inv(aff)

    grid = np.empty((nd, nv, nu), dtype=np.float32)
    ones = np.ones(uu.shape, dtype=np.float64)
    for zi, dist in enumerate(ds):
        world_slab = (
            centroid[0] + uu * right[0] + vv * up[0] + dist * forward[0],
            centroid[1] + uu * right[1] + vv * up[1] + dist * forward[1],
            centroid[2] + uu * right[2] + vv * up[2] + dist * forward[2],
        )
        hom = np.stack([world_slab[0], world_slab[1], world_slab[2], ones], axis=-1)
        ijk = hom @ inv_aff.T
        coords = np.stack([ijk[..., 0], ijk[..., 1], ijk[..., 2]], axis=0)
        grid[zi] = map_coordinates(vol, coords.reshape(3, -1), order=1, cval=0.0).reshape(nv, nu)

    shade = np.linspace(1.0, 0.42, nd, dtype=np.float32)[:, None, None]
    acc = np.zeros((nv, nu), dtype=np.float32)
    trans = np.ones((nv, nu), dtype=np.float32)
    for zi in range(nd):
        dens = grid[zi]
        alpha = 1.0 - np.exp(-dens * settings["ray_extinction"])
        acc += trans * alpha * dens * shade[zi]
        trans *= 1.0 - np.clip(alpha, 0.0, settings["layer_alpha_cap"])
    acc = np.nan_to_num(acc, nan=0.0, posinf=0.0, neginf=0.0)
    positive = acc[acc > 0]
    if positive.size < settings["min_positive_pixels"]:
        raise RuntimeError("blank view")
    peak = float(np.percentile(positive, settings["normalization_percentile"]))
    if peak <= 0:
        raise RuntimeError("zero peak")
    acc = np.clip(acc / peak, 0.0, 1.0)
    acc = np.power(acc, settings["display_gamma"])
    acc[acc < settings["background_cutoff"]] = 0.0
    acc = acc[::-1, :]
    filled = float((acc > 0.02).mean())
    print(
        f"  extent u={u1 - u0:.1f} v={v1 - v0:.1f} d={d1 - d0:.1f} mm  "
        f"bins={nu}x{nv}x{nd} fill={filled:.3f}",
        flush=True,
    )
    if filled < settings["min_filled_fraction"]:
        raise RuntimeError("view nearly blank")
    frame = np.stack([acc, acc * settings["green_channel_scale"], acc * settings["blue_channel_scale"]], axis=-1)
    if return_metadata:
        return frame, {"extent_mm": [float(u0), float(u1), float(v0), float(v1)], "shape_px": [int(nu), int(nv)]}
    return frame


def render_volume(path: Path, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Render one explicit NIfTI volume, returning five frames and projected extents."""
    settings = resolve_settings(settings)
    path = Path(path)
    nib = _require_nibabel()
    source_image = nib.load(str(path))
    source_affine = np.asarray(source_image.affine, dtype=np.float64).copy()
    source_shape = tuple(int(value) for value in source_image.shape)
    spatial_units, temporal_units = source_image.header.get_xyzt_units()
    voxel_axis_codes = tuple(str(code) for code in _require_nibabel().aff2axcodes(source_affine))
    del source_image
    vol, aff, thr, hi = load_windowed(path, settings)
    axes = anatomical_axes(aff)
    world, centroid = foreground_world(vol, aff, settings)
    frames = []
    extents = []
    for name in VIEW_KEYS:
        forward, up = view_forward_up(axes, name)
        print(f"  {name}", flush=True)
        bounds = full_volume_projection_bounds(source_shape, source_affine, centroid, forward, up)
        frame, info = composite_view(vol, aff, world, centroid, forward, up,
                                     projection_bounds=bounds, settings=settings, return_metadata=True)
        frames.append(frame)
        extents.append(info["extent_mm"])
    return {
        "frames": frames,
        "extents_mm": extents,
        "affine": source_affine.tolist(),
        "voxel_axis_codes": list(voxel_axis_codes),
        "world_axis_convention": "RAS+",
        "render_affine": np.asarray(aff).tolist(),
        "source_shape": list(source_shape),
        "spatial_units": spatial_units,
        "temporal_units": temporal_units,
        "threshold": float(thr),
        "high": float(hi),
        "settings": settings,
        "downsampled_shape": list(vol.shape),
        "projection_origin_ras_world_mm": centroid.tolist(),
        "projection_bounds_source": "full input voxel-cell bounds; source affine; eight corners",
    }


def render_animal(path: Path) -> list[np.ndarray]:
    """Compatibility name for the original projectome single-volume API."""
    return render_volume(path)["frames"]


def save_single_volume_montage(
    frames: list[np.ndarray],
    extents_mm: list[list[float]],
    dest: Path,
    title: str,
    affine: np.ndarray | None = None,
    settings: Mapping[str, Any] | None = None,
) -> None:
    """Save a compact single-volume five-view PNG with plane labels and image swatch."""
    if len(frames) != 5 or len(extents_mm) != 5:
        raise ValueError("a single-volume montage requires five rendered views and extents")
    settings = resolve_settings(settings)
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    fig, axes = plt.subplots(1, 5, figsize=settings["figure_size_inches"], squeeze=False)
    fig.patch.set_facecolor("black")
    fig.suptitle(title, color="white", fontsize=13, y=0.99)
    for index, (name, panel_title, frame, extent) in enumerate(zip(VIEW_KEYS, VIEW_TITLES, frames, extents_mm)):
        ax = axes[0, index]
        ax.set_facecolor("black")
        ax.imshow(frame, origin="upper", interpolation="bilinear", aspect="equal", extent=extent)
        ax.set_title(panel_title, color="white", fontsize=10)
        if affine is None:
            x_label, y_label = "Projected u (LPS mm)", "Projected v (LPS mm)"
        else:
            x_label, y_label = view_axis_labels(affine, name)
        ax.set_xlabel(x_label, color="white", fontsize=7.5)
        ax.set_ylabel(y_label, color="white", fontsize=7.5)
        ax.tick_params(colors="white", labelsize=6)
        for spine in ax.spines.values():
            spine.set_color("#666666")
    fig.legend(handles=[Patch(facecolor="#cccccc", edgecolor="white", label="NIfTI intensity · ray composite")],
               loc="lower center", frameon=False, labelcolor="white", fontsize=8)
    fig.subplots_adjust(left=0.035, right=0.995, top=0.84, bottom=0.22, wspace=0.22)
    destination = Path(dest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=settings["figure_dpi"], facecolor=fig.get_facecolor())
    plt.close(fig)


__all__ = [
    "VIEW_KEYS", "VIEW_TITLES", "DEFAULT_SETTINGS", "SETTING_SPECS",
    "resolve_settings", "unit", "otsu_threshold", "anatomical_axes",
    "view_forward_up", "view_axis_labels", "load_windowed", "foreground_world",
    "full_volume_projection_bounds", "composite_view",
    "render_animal", "render_volume", "save_single_volume_montage",
]
