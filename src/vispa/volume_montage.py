"""Generic DS00 five-view volume renderer, extracted without changing its defaults.

Version: 1.11.0.dev4 (local/unreleased)
Last updated: 2026-10-22
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

DEFAULT_SETTINGS: dict[str, Any] = {
    "figure_size_inches": (18.2, 4.4),
    "figure_dpi": 120,
    "max_dimension": 210,
    "otsu_sample_stride": 8,
    "otsu_clip_percentile": 99.5,
    "intensity_high_percentile": 99.3,
    "minimum_intensity_span": 1.0,
    "blur_sigma_voxels": (0.45, 0.45, 0.95),
    "foreground_threshold": 0.08,
    "min_foreground_voxels": 1000,
    "max_foreground_points": 300000,
    "view_extent_percentiles": (0.6, 99.4),
    "depth_percentiles": (0.3, 99.7),
    "projection_padding_fraction": 0.07,
    "minimum_extent_mm": 5.0,
    "projection_bin_mm": 0.36,
    "horizontal_bins_px": (150, 260),
    "vertical_bins_px": (150, 280),
    "depth_step_mm": 0.55,
    "depth_bins": (56, 110),
    "ray_extinction": 8.0,
    "layer_alpha_cap": 0.88,
    "normalization_percentile": 99.5,
    "display_gamma": 0.88,
    "background_cutoff": 0.012,
    "min_positive_pixels": 200,
    "min_filled_fraction": 0.04,
    "green_channel_scale": 0.985,
    "blue_channel_scale": 0.94,
}

# A compact operator-facing schema. Ranges constrain display parameters only;
# values do not declare anatomy, registration, or scientific acceptance.
_SETTING_METADATA: dict[str, dict[str, Any]] = {
    "figure_size_inches": {"default": [18.2, 4.4], "units": "inches", "range": [1, 100], "effect": "single-volume figure width and height"},
    "figure_dpi": {"default": 120, "units": "dots per inch", "range": [36, 600], "effect": "single-volume PNG output resolution"},
    "max_dimension": {"default": 210, "units": "voxels", "range": [1, 4096], "effect": "maximum downsampled array dimension"},
    "otsu_sample_stride": {"default": 8, "units": "samples", "range": [1, 4096], "effect": "stride used for the Otsu histogram input"},
    "otsu_clip_percentile": {"default": 99.5, "units": "%", "range": [0, 100], "effect": "upper clipping percentile for Otsu values"},
    "intensity_high_percentile": {"default": 99.3, "units": "%", "range": [0, 100], "effect": "high intensity used to normalize display volume"},
    "minimum_intensity_span": {"default": 1.0, "units": "input intensity", "range": [1e-12, None], "effect": "minimum separation between low and high display intensities"},
    "blur_sigma_voxels": {"default": [0.45, 0.45, 0.95], "units": "voxels per array axis", "range": [0, 1000], "effect": "Gaussian smoothing applied to the downsampled display volume"},
    "foreground_threshold": {"default": 0.08, "units": "normalized intensity", "range": [0, 1], "effect": "threshold for foreground samples used to set view bounds"},
    "min_foreground_voxels": {"default": 1000, "units": "voxels", "range": [1, None], "effect": "minimum foreground count before rendering"},
    "max_foreground_points": {"default": 300000, "units": "points", "range": [1, None], "effect": "maximum foreground samples used for geometry bounds"},
    "view_extent_percentiles": {"default": [0.6, 99.4], "units": "%", "range": [0, 100], "effect": "lower and upper projected image extent percentiles"},
    "depth_percentiles": {"default": [0.3, 99.7], "units": "%", "range": [0, 100], "effect": "lower and upper ray depth percentiles"},
    "projection_padding_fraction": {"default": 0.07, "units": "fraction", "range": [0, 1], "effect": "padding added to each projected image extent"},
    "minimum_extent_mm": {"default": 5.0, "units": "mm", "range": [1e-12, None], "effect": "minimum width, height, and depth accepted for a view"},
    "projection_bin_mm": {"default": 0.36, "units": "mm per pixel", "range": [1e-12, None], "effect": "nominal projected image sampling interval"},
    "horizontal_bins_px": {"default": [150, 260], "units": "pixels", "range": [1, 4096], "effect": "minimum and maximum projected image width"},
    "vertical_bins_px": {"default": [150, 280], "units": "pixels", "range": [1, 4096], "effect": "minimum and maximum projected image height"},
    "depth_step_mm": {"default": 0.55, "units": "mm per ray step", "range": [1e-12, None], "effect": "nominal sampling interval through the volume"},
    "depth_bins": {"default": [56, 110], "units": "samples", "range": [1, 1024], "effect": "minimum and maximum ray sample count"},
    "ray_extinction": {"default": 8.0, "units": "unitless", "range": [1e-12, None], "effect": "opacity growth rate for each ray sample"},
    "layer_alpha_cap": {"default": 0.88, "units": "fraction", "range": [0, 1], "effect": "maximum opacity of one ray layer"},
    "normalization_percentile": {"default": 99.5, "units": "%", "range": [0, 100], "effect": "positive composite intensity percentile mapped to full display range"},
    "display_gamma": {"default": 0.88, "units": "unitless", "range": [1e-12, None], "effect": "gamma applied to normalized composite intensity"},
    "background_cutoff": {"default": 0.012, "units": "normalized intensity", "range": [0, 1], "effect": "values below this display level become black"},
    "min_positive_pixels": {"default": 200, "units": "pixels", "range": [1, None], "effect": "minimum nonzero composite pixel count"},
    "min_filled_fraction": {"default": 0.04, "units": "fraction", "range": [0, 1], "effect": "minimum fraction of pixels above the fill threshold"},
    "green_channel_scale": {"default": 0.985, "units": "fraction", "range": [0, 1], "effect": "green channel tint multiplier"},
    "blue_channel_scale": {"default": 0.94, "units": "fraction", "range": [0, 1], "effect": "blue channel tint multiplier"},
}


def _setting_type(value: Any) -> str:
    if isinstance(value, (tuple, list)):
        item_type = "integer" if value and all(isinstance(item, int) and not isinstance(item, bool) for item in value) else "float"
        return f"{item_type}[{len(value)}]"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    return "float"

SETTING_SPECS: dict[str, dict[str, Any]] = {
    key: {
        "type": _setting_type(spec["default"]),
        "default": copy.deepcopy(spec["default"]),
        "effect": spec["effect"],
        "unit": spec["units"],
        "min": spec["range"][0],
        "max": spec["range"][1],
    }
    for key, spec in _SETTING_METADATA.items()
}


def resolve_settings(
    overrides: Mapping[str, Any] | None = None,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deep-copied validated settings; never mutate inputs or globals."""
    values = copy.deepcopy(DEFAULT_SETTINGS)
    for layer in (base, overrides):
        if layer is None:
            continue
        unknown = sorted(set(layer) - set(values))
        if unknown:
            raise ValueError(f"unknown montage setting(s): {', '.join(unknown)}")
        values.update(copy.deepcopy(dict(layer)))

    def number(key: str, low: float, high: float | None) -> None:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{key} must be a finite number")
        if value < low or (high is not None and value > high):
            raise ValueError(f"{key} must be in [{low}, {high if high is not None else 'infinity'}]")

    def integer(key: str, low: int, high: int | None = None) -> None:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        if value < low or (high is not None and value > high):
            raise ValueError(f"{key} must be in [{low}, {high if high is not None else 'infinity'}]")

    vals = values["figure_size_inches"]
    if not isinstance(vals, (list, tuple)) or len(vals) != 2 or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or not 1 <= v <= 100
        for v in vals
    ):
        raise ValueError("figure_size_inches must contain two finite values in [1, 100]")
    values["figure_size_inches"] = tuple(float(v) for v in vals)
    integer("figure_dpi", 36, 600)
    integer("max_dimension", 1, 4096)
    integer("otsu_sample_stride", 1, 4096)
    number("otsu_clip_percentile", 0, 100)
    number("intensity_high_percentile", 0, 100)
    number("minimum_intensity_span", 1e-12, None)
    for key in ("blur_sigma_voxels",):
        vals = values[key]
        if not isinstance(vals, (list, tuple)) or len(vals) != 3:
            raise ValueError(f"{key} must contain three values")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or v < 0 or v > 1000 for v in vals):
            raise ValueError(f"{key} values must be finite and in [0, 1000]")
        values[key] = tuple(float(v) for v in vals)
    number("foreground_threshold", 0, 1)
    integer("min_foreground_voxels", 1)
    integer("max_foreground_points", 1)
    for key in ("view_extent_percentiles", "depth_percentiles"):
        vals = values[key]
        if not isinstance(vals, (list, tuple)) or len(vals) != 2:
            raise ValueError(f"{key} must contain two ordered percentiles")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in vals) or not 0 <= vals[0] < vals[1] <= 100:
            raise ValueError(f"{key} must satisfy 0 <= lower < upper <= 100")
        values[key] = tuple(float(v) for v in vals)
    number("projection_padding_fraction", 0, 1)
    number("minimum_extent_mm", 1e-12, None)
    number("projection_bin_mm", 1e-12, None)
    for key in ("horizontal_bins_px", "vertical_bins_px", "depth_bins"):
        vals = values[key]
        maximum = 1024 if key == "depth_bins" else 4096
        if not isinstance(vals, (list, tuple)) or len(vals) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= maximum for v in vals) or vals[0] > vals[1]:
            raise ValueError(f"{key} must contain ordered integers in [1, {maximum}]")
        values[key] = tuple(vals)
    for key in ("depth_step_mm", "ray_extinction", "display_gamma"):
        number(key, 1e-12, None)
    for key in ("layer_alpha_cap", "background_cutoff", "min_filled_fraction", "green_channel_scale", "blue_channel_scale"):
        number(key, 0, 1)
    number("normalization_percentile", 0, 100)
    integer("min_positive_pixels", 1)
    return values


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
        frame, info = composite_view(vol, aff, world, centroid, forward, up, settings=settings, return_metadata=True)
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
    "view_forward_up", "view_axis_labels", "load_windowed", "foreground_world", "composite_view",
    "render_animal", "render_volume", "save_single_volume_montage",
]
