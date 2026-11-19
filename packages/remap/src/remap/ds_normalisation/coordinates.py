"""Explicit point-coordinate conversions for a declared DS00 route.

``CoordinateRoute`` is the older three-grid route. ``ProinsDs00Route`` follows
the Pro_INS spatial stages: raw SWC, native NIfTI, N4 (no point move), the
DS00 case rigid frame, sharedPitch10, then the selected NMT registration.
Image resampling and registration fitting stay in Pro_INS; this module only
moves declared points through those saved transforms.

Version: 0.2.0 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-03: CoordinateRoute for raw, native, pitch, and NMT points.
- 2026-11-10: ProinsDs00Route follows the Pro_INS stages. The rigid frame is supplied per DS00 case.
- 2026-11-10: Moved into ds_normalisation/.
Status: candidate
"""
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np


@dataclass(frozen=True)
class Points:
    xyz: np.ndarray
    frame: str
    unit: str

    def __post_init__(self):
        value = np.asarray(self.xyz, dtype=float)
        if value.ndim != 2 or value.shape[1] != 3 or not np.isfinite(value).all():
            raise ValueError("points must be a finite N x 3 array")
        if not self.frame or not self.unit:
            raise ValueError("frame and unit must be declared")
        object.__setattr__(self, "xyz", value)


def _require(points: Points, frame: str, unit: str) -> None:
    if (points.frame, points.unit) != (frame, unit):
        raise ValueError(f"expected {frame} [{unit}], got {points.frame} [{points.unit}]")


def raw_candidate_a_to_native(points: Points, *, native_frame: str,
                              shape: Sequence[int], spacing_um: Sequence[float]) -> Points:
    """Provisional raw XYZ um to corrected native IJK; caller supplies sample metadata.

    The raw-axis origin/calibration assumption has not been independently verified.
    No sample, including 747, receives a guessed default spacing or shape.
    """
    return raw_to_native(points, native_frame=native_frame, shape=shape,
                         spacing_um=spacing_um, candidate="A", converter="generic")


def raw_to_native(points: Points, *, native_frame: str, shape: Sequence[int],
                  spacing_um: Sequence[float], candidate: str, converter: str) -> Points:
    """Provisional raw axis candidate through an explicitly selected converter.

    ``converter='special_747'`` encodes the verified converter voxel permutation
    for sample 250432. It does not verify raw SWC origin or axis calibration.
    """
    _require(points, "raw_swc_xyz", "um")
    size = np.asarray(shape)
    spacing = np.asarray(spacing_um, dtype=float)
    if size.shape != (3,) or not np.issubdtype(size.dtype, np.integer) or np.any(size <= 0) or spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("native shape and anisotropic spacing must be three positive values")
    if candidate not in {"A", "B"} or converter not in {"generic", "special_747"}:
        raise ValueError("candidate must be A/B and converter generic/special_747")
    x = points.xyz
    if converter == "generic":
        middle = x[:, 2] if candidate == "A" else x[:, 1]
        last = x[:, 1] if candidate == "A" else x[:, 2]
        ijk = np.column_stack((x[:, 0] / spacing[0], middle / spacing[1],
                               size[2] - 1 - last / spacing[2]))
    else:
        first = x[:, 1] if candidate == "A" else x[:, 2]
        middle = x[:, 2] if candidate == "A" else x[:, 1]
        ijk = np.column_stack((size[0] - 1 - first / spacing[0],
                               middle / spacing[1], size[2] - 1 - x[:, 0] / spacing[2]))
    return Points(ijk, native_frame, "voxel")


def native_to_raw(points: Points, *, native_frame: str, shape: Sequence[int],
                  spacing_um: Sequence[float], candidate: str, converter: str) -> Points:
    """Algebraic inverse of the declared provisional raw-axis mapping."""
    _require(points, native_frame, "voxel")
    size = np.asarray(shape)
    spacing = np.asarray(spacing_um, dtype=float)
    if size.shape != (3,) or not np.issubdtype(size.dtype, np.integer) or np.any(size <= 0) or spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("native shape and anisotropic spacing must be three positive values")
    if candidate not in {"A", "B"} or converter not in {"generic", "special_747"}:
        raise ValueError("candidate must be A/B and converter generic/special_747")
    i, j, k = points.xyz.T
    if converter == "generic":
        x = i * spacing[0]
        middle = j * spacing[1]
        last = (size[2] - 1 - k) * spacing[2]
        xyz = np.column_stack((x, last, middle) if candidate == "A" else (x, middle, last))
    else:
        first = (size[0] - 1 - i) * spacing[0]
        middle = j * spacing[1]
        x = (size[2] - 1 - k) * spacing[2]
        xyz = np.column_stack((x, first, middle) if candidate == "A" else (x, middle, first))
    return Points(xyz, "raw_swc_xyz", "um")


def legacy_divide_250(points: Points, *, target_frame: str) -> Points:
    """Historical ReMAP mapping, kept explicitly separate from candidate A."""
    if points.frame != "legacy_swc_xyz":
        raise ValueError("historical /250 requires explicitly declared legacy_swc_xyz frame")
    return Points(points.xyz / 250.0, target_frame, "voxel")


def legacy_multiply_250(points: Points, *, source_frame: str) -> Points:
    """Reverse historical numeric mapping; physical source unit stays unknown."""
    _require(points, source_frame, "voxel")
    return Points(points.xyz * 250.0, "legacy_swc_xyz", "unknown")


def raw_to_5um_grid(points: Points, *, grid_frame: str, raw_um_to_grid_voxel: np.ndarray) -> Points:
    """Use a supplied, evidence-backed raw SWC to 5µm image-grid calibration."""
    _require(points, "raw_swc_xyz", "um")
    matrix = np.asarray(raw_um_to_grid_voxel, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1]) or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("raw/5um calibration must be an invertible 4 x 4 matrix")
    return Points(points.xyz @ matrix[:3, :3].T + matrix[:3, 3], grid_frame, "voxel")


def grid_5um_to_raw(points: Points, *, grid_frame: str, raw_um_to_grid_voxel: np.ndarray) -> Points:
    _require(points, grid_frame, "voxel")
    matrix = np.asarray(raw_um_to_grid_voxel, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1]) or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("raw/5um calibration must be an invertible 4 x 4 matrix")
    inverse = np.linalg.inv(matrix)
    return Points(points.xyz @ inverse[:3, :3].T + inverse[:3, 3], "raw_swc_xyz", "um")


def convert_length_unit(points: Points, *, to_unit: str) -> Points:
    if points.unit not in {"mm", "um"} or to_unit not in {"mm", "um"}:
        raise ValueError("length units must be mm or um")
    factor = 1.0 if points.unit == to_unit else (0.001 if to_unit == "mm" else 1000.0)
    return Points(points.xyz * factor, points.frame, to_unit)


def voxel_to_ras_mm(points: Points, *, voxel_frame: str, ras_frame: str,
                    affine: np.ndarray) -> Points:
    _require(points, voxel_frame, "voxel")
    matrix = np.asarray(affine, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1]) or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("affine must be a finite invertible 4 x 4 matrix")
    return Points(points.xyz @ matrix[:3, :3].T + matrix[:3, 3], ras_frame, "mm")


def ras_mm_to_voxel(points: Points, *, ras_frame: str, voxel_frame: str,
                    affine: np.ndarray) -> Points:
    _require(points, ras_frame, "mm")
    matrix = np.asarray(affine, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1]) or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("affine must be a finite invertible 4 x 4 matrix")
    inverse = np.linalg.inv(matrix)
    return Points(points.xyz @ inverse[:3, :3].T + inverse[:3, 3], voxel_frame, "voxel")


def ras_to_lps_mm(points: Points, *, ras_frame: str, lps_frame: str) -> Points:
    _require(points, ras_frame, "mm")
    return Points(points.xyz * (-1, -1, 1), lps_frame, "mm")


def lps_to_ras_mm(points: Points, *, lps_frame: str, ras_frame: str) -> Points:
    _require(points, lps_frame, "mm")
    return Points(points.xyz * (-1, -1, 1), ras_frame, "mm")


def apply_saved_point_chain(points: Points, *, source_frame: str, target_frame: str,
                            transforms: Sequence[object],
                            apply: Callable[[np.ndarray, Sequence[object]], np.ndarray]) -> Points:
    """Apply a caller-verified ANTs point chain in its declared order.

    ``apply`` owns tool execution and transform/hash validation. This function
    checks frames and result shape; it does not infer image-pull directions.
    """
    _require(points, source_frame, "mm")
    if not transforms or not target_frame or source_frame == target_frame:
        raise ValueError("declare a nonempty point chain between distinct frames")
    result = Points(apply(points.xyz, transforms), target_frame, "mm")
    if result.xyz.shape != points.xyz.shape:
        raise ValueError("point chain changed point count")
    return result


@dataclass(frozen=True)
class SavedBridge:
    """Two explicit ANTs point chains, each in point application order.

    A nonlinear inverse must name its saved inverse warp. Reversing or negating
    the forward warp is never inferred here.
    """
    source_lps: str
    target_lps: str
    forward: tuple
    reverse: tuple

    def __post_init__(self):
        if not self.source_lps or not self.target_lps or self.source_lps == self.target_lps:
            raise ValueError("bridge requires distinct named LPS frames")
        if not self.forward or not self.reverse:
            raise ValueError("both saved point directions are required")


@dataclass(frozen=True)
class CoordinateRoute:
    """Declared geometry between raw SWC and three sampled image grids.

    Image processing that changes intensities but preserves its grid needs no
    coordinate step. Image resampling is outside this point-only API.
    """
    native_frame: str
    native_shape: tuple
    native_spacing_um: tuple
    native_affine: np.ndarray
    pitch_frame: str
    pitch_affine: np.ndarray
    nmt_frame: str
    nmt_affine: np.ndarray
    candidate: str
    converter: str
    native_pitch: SavedBridge
    pitch_nmt: SavedBridge
    grid_5um_frame: str = ""
    raw_um_to_5um_voxel: np.ndarray = None
    processed_swc_frame: str = ""
    processed_to_nmt_voxel: np.ndarray = None
    processed_unit: str = "stored"

    def __post_init__(self):
        if len({self.native_frame, self.pitch_frame, self.nmt_frame, "raw_swc_xyz"}) != 4:
            raise ValueError("route frames must be distinct")
        if self.native_pitch.source_lps != self.native_frame + "_lps" or self.native_pitch.target_lps != self.pitch_frame + "_lps":
            raise ValueError("native/pitch bridge frame mismatch")
        if self.pitch_nmt.source_lps != self.pitch_frame + "_lps" or self.pitch_nmt.target_lps != self.nmt_frame + "_lps":
            raise ValueError("pitch/NMT bridge frame mismatch")
        for affine in (self.native_affine, self.pitch_affine, self.nmt_affine):
            matrix = np.asarray(affine, dtype=float)
            if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1]) or abs(np.linalg.det(matrix)) < 1e-12:
                raise ValueError("route image affines must be invertible 4 x 4 matrices")
        if self.grid_5um_frame and self.grid_5um_frame in {self.native_frame, self.pitch_frame, self.nmt_frame, "raw_swc_xyz"}:
            raise ValueError("5um frame must be distinct")
        if self.processed_swc_frame and self.processed_swc_frame in {self.native_frame, self.pitch_frame, self.nmt_frame, self.grid_5um_frame, "raw_swc_xyz"}:
            raise ValueError("processed SWC frame must be distinct")

    def convert(self, points: Points, target_frame: str,
                *, apply: Callable[[np.ndarray, Sequence[object]], np.ndarray]) -> Points:
        """Convert points between any two route frames using declared bridges."""
        requested = target_frame
        if points.frame == self.grid_5um_frame and self.grid_5um_frame:
            if self.raw_um_to_5um_voxel is None:
                raise ValueError("5um image calibration is unverified or missing")
            points = grid_5um_to_raw(points, grid_frame=self.grid_5um_frame,
                                     raw_um_to_grid_voxel=self.raw_um_to_5um_voxel)
        if points.frame == self.processed_swc_frame and self.processed_swc_frame:
            if self.processed_to_nmt_voxel is None:
                raise ValueError("processed SWC to NMT grid binding is unverified or missing")
            points = _apply_grid_matrix(points, self.processed_swc_frame, self.nmt_frame,
                                        self.processed_to_nmt_voxel, source_unit=self.processed_unit)
        if target_frame == self.grid_5um_frame and self.grid_5um_frame:
            if self.raw_um_to_5um_voxel is None:
                raise ValueError("5um image calibration is unverified or missing")
            target_frame = "raw_swc_xyz"
        if target_frame == self.processed_swc_frame and self.processed_swc_frame:
            if self.processed_to_nmt_voxel is None:
                raise ValueError("processed SWC to NMT grid binding is unverified or missing")
            target_frame = self.nmt_frame
        frames = ("raw_swc_xyz", self.native_frame, self.pitch_frame, self.nmt_frame)
        if points.frame not in frames or target_frame not in frames:
            raise ValueError("source and target must belong to this route")
        units = ("um", "voxel", "voxel", "voxel")
        _require(points, points.frame, units[frames.index(points.frame)])
        current = points
        source = frames.index(points.frame)
        target = frames.index(target_frame)
        if source == target:
            return self._finish(current, requested)
        step = 1 if target > source else -1
        for index in range(source, target, step):
            if step == 1 and index == 0:
                current = raw_to_native(current, native_frame=self.native_frame,
                                        shape=self.native_shape, spacing_um=self.native_spacing_um,
                                        candidate=self.candidate, converter=self.converter)
            elif step == -1 and index == 1:
                current = native_to_raw(current, native_frame=self.native_frame,
                                        shape=self.native_shape, spacing_um=self.native_spacing_um,
                                        candidate=self.candidate, converter=self.converter)
            else:
                left = index if step == 1 else index - 1
                bridge = (self.native_pitch, self.pitch_nmt)[left - 1]
                from_frame = frames[index]
                to_frame = frames[index + step]
                from_affine = (self.native_affine, self.pitch_affine, self.nmt_affine)[index - 1]
                to_affine = (self.native_affine, self.pitch_affine, self.nmt_affine)[index + step - 1]
                ras = voxel_to_ras_mm(current, voxel_frame=from_frame, ras_frame=from_frame + "_ras", affine=from_affine)
                lps = ras_to_lps_mm(ras, ras_frame=from_frame + "_ras", lps_frame=from_frame + "_lps")
                mapped = apply_saved_point_chain(lps, source_frame=lps.frame,
                                                 target_frame=to_frame + "_lps",
                                                 transforms=bridge.forward if step == 1 else bridge.reverse,
                                                 apply=apply)
                target_ras = lps_to_ras_mm(mapped, lps_frame=to_frame + "_lps", ras_frame=to_frame + "_ras")
                current = ras_mm_to_voxel(target_ras, ras_frame=to_frame + "_ras", voxel_frame=to_frame, affine=to_affine)
        return self._finish(current, requested)

    def _finish(self, points: Points, requested: str) -> Points:
        if requested == self.grid_5um_frame and self.grid_5um_frame:
            return raw_to_5um_grid(points, grid_frame=requested,
                                   raw_um_to_grid_voxel=self.raw_um_to_5um_voxel)
        if requested == self.processed_swc_frame and self.processed_swc_frame:
            inverse = np.linalg.inv(np.asarray(self.processed_to_nmt_voxel, dtype=float))
            return _apply_grid_matrix(points, self.nmt_frame, requested, inverse,
                                      target_unit=self.processed_unit)
        return points


def _apply_grid_matrix(points: Points, source_frame: str, target_frame: str,
                       matrix: np.ndarray, *, source_unit: str = "voxel",
                       target_unit: str = "voxel") -> Points:
    _require(points, source_frame, source_unit)
    value = np.asarray(matrix, dtype=float)
    if value.shape != (4, 4) or not np.isfinite(value).all() or not np.allclose(value[3], [0, 0, 0, 1]) or abs(np.linalg.det(value)) < 1e-12:
        raise ValueError("grid binding must be an invertible 4 x 4 matrix")
    return Points(points.xyz @ value[:3, :3].T + value[:3, 3], target_frame, target_unit)


def _apply_lps_matrix(points: Points, matrix: np.ndarray, target_frame: str) -> Points:
    _require(points, points.frame, "mm")
    value = np.asarray(matrix, dtype=float)
    if value.shape != (4, 4) or not np.isfinite(value).all() or not np.allclose(value[3], [0, 0, 0, 1]) or abs(np.linalg.det(value)) < 1e-12:
        raise ValueError("pitch matrix must be an invertible 4 x 4 LPS-mm transform")
    return Points(points.xyz @ value[:3, :3].T + value[:3, 3], target_frame, "mm")


def proins_ds00_stages(rigid_frame: str) -> tuple[str, ...]:
    """Point stages for one DS00 case. The rigid frame name comes from that case."""
    if not rigid_frame or rigid_frame in {"raw_swc_xyz", "native_nifti", "native_n4", "shared_pitch10", "nmt"}:
        raise ValueError("rigid_frame must be the DS00 case reference frame")
    return ("raw_swc_xyz", "native_nifti", "native_n4", rigid_frame, "shared_pitch10", "nmt")


@dataclass(frozen=True)
class ProinsDs00Route:
    """Point route with the same spatial order as the Pro_INS DS00 toolbox.

    ``rigid_frame`` and ``rigid`` are the saved rigid for this DS00 case.
    The present cohort often uses 936/251637 as that reference, but another
    DS00 selection supplies another frame and another transform. N4 keeps the
    native voxel coordinates. ``pitch_lps`` is the case pitch in the rigid LPS
    frame. The registration bridge is that case's sharedPitch10-to-NMT chain.
    """
    native_shape: tuple
    native_spacing_um: tuple
    native_affine: np.ndarray
    candidate: str
    converter: str
    rigid_frame: str
    rigid: SavedBridge
    pitch_lps: np.ndarray
    shared_pitch_affine: np.ndarray
    nmt_affine: np.ndarray
    registration: SavedBridge

    def __post_init__(self):
        stages = proins_ds00_stages(self.rigid_frame)
        object.__setattr__(self, "_stages", stages)
        if self.rigid.source_lps != "native_nifti_lps" or self.rigid.target_lps != f"{self.rigid_frame}_lps":
            raise ValueError(f"rigid bridge must run native_nifti_lps -> {self.rigid_frame}_lps")
        if self.registration.source_lps != "shared_pitch10_lps" or self.registration.target_lps != "nmt_lps":
            raise ValueError("registration bridge must run shared_pitch10_lps -> nmt_lps")
        for name, affine in (
            ("native", self.native_affine),
            ("shared_pitch", self.shared_pitch_affine),
            ("nmt", self.nmt_affine),
            ("pitch", self.pitch_lps),
        ):
            matrix = np.asarray(affine, dtype=float)
            if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
                raise ValueError(f"{name} matrix must be an invertible 4 x 4")

    def convert(self, points: Points, target_frame: str, *,
                apply: Callable[[np.ndarray, Sequence[object]], np.ndarray]) -> Points:
        stages = self._stages
        if points.frame not in stages or target_frame not in stages:
            raise ValueError("source and target must be this DS00 case's point stages")
        current = points
        source = stages.index(points.frame)
        target = stages.index(target_frame)
        if source == target:
            return current
        step = 1 if target > source else -1
        for index in range(source, target, step):
            current = self._step(current, index, step, apply)
        return current

    def _step(self, points: Points, index: int, step: int, apply) -> Points:
        stages = self._stages
        left = index if step == 1 else index - 1
        stage = stages[left]
        nxt = stages[left + 1]
        rigid_frame = self.rigid_frame
        if stage == "native_nifti" and nxt == "native_n4":
            _require(points, "native_nifti" if step == 1 else "native_n4", "voxel")
            return Points(points.xyz, nxt if step == 1 else "native_nifti", "voxel")
        if {stage, nxt} == {"raw_swc_xyz", "native_nifti"}:
            if step == 1:
                return raw_to_native(points, native_frame="native_nifti", shape=self.native_shape,
                                     spacing_um=self.native_spacing_um, candidate=self.candidate,
                                     converter=self.converter)
            return native_to_raw(points, native_frame="native_nifti", shape=self.native_shape,
                                 spacing_um=self.native_spacing_um, candidate=self.candidate,
                                 converter=self.converter)
        if {stage, nxt} == {"native_n4", rigid_frame}:
            if step == 1:
                _require(points, "native_n4", "voxel")
                native = Points(points.xyz, "native_nifti", "voxel")
                ras = voxel_to_ras_mm(native, voxel_frame="native_nifti", ras_frame="native_nifti_ras", affine=self.native_affine)
                lps = ras_to_lps_mm(ras, ras_frame="native_nifti_ras", lps_frame="native_nifti_lps")
                return apply_saved_point_chain(lps, source_frame="native_nifti_lps", target_frame=rigid_frame,
                                               transforms=self.rigid.forward, apply=apply)
            _require(points, rigid_frame, "mm")
            lps = apply_saved_point_chain(Points(points.xyz, f"{rigid_frame}_lps", "mm"),
                                          source_frame=f"{rigid_frame}_lps", target_frame="native_nifti_lps",
                                          transforms=self.rigid.reverse, apply=apply)
            ras = lps_to_ras_mm(lps, lps_frame="native_nifti_lps", ras_frame="native_nifti_ras")
            voxels = ras_mm_to_voxel(ras, ras_frame="native_nifti_ras", voxel_frame="native_nifti", affine=self.native_affine)
            return Points(voxels.xyz, "native_n4", "voxel")
        if {stage, nxt} == {rigid_frame, "shared_pitch10"}:
            if step == 1:
                _require(points, rigid_frame, "mm")
                pitched = _apply_lps_matrix(Points(points.xyz, rigid_frame, "mm"), self.pitch_lps, "shared_pitch10_lps")
                ras = lps_to_ras_mm(pitched, lps_frame="shared_pitch10_lps", ras_frame="shared_pitch10_ras")
                return ras_mm_to_voxel(ras, ras_frame="shared_pitch10_ras", voxel_frame="shared_pitch10", affine=self.shared_pitch_affine)
            _require(points, "shared_pitch10", "voxel")
            ras = voxel_to_ras_mm(points, voxel_frame="shared_pitch10", ras_frame="shared_pitch10_ras", affine=self.shared_pitch_affine)
            lps = ras_to_lps_mm(ras, ras_frame="shared_pitch10_ras", lps_frame="shared_pitch10_lps")
            inverse = np.linalg.inv(np.asarray(self.pitch_lps, dtype=float))
            return _apply_lps_matrix(lps, inverse, rigid_frame)
        if {stage, nxt} == {"shared_pitch10", "nmt"}:
            if step == 1:
                ras = voxel_to_ras_mm(points, voxel_frame="shared_pitch10", ras_frame="shared_pitch10_ras", affine=self.shared_pitch_affine)
                lps = ras_to_lps_mm(ras, ras_frame="shared_pitch10_ras", lps_frame="shared_pitch10_lps")
                mapped = apply_saved_point_chain(lps, source_frame="shared_pitch10_lps", target_frame="nmt_lps",
                                                 transforms=self.registration.forward, apply=apply)
                target_ras = lps_to_ras_mm(mapped, lps_frame="nmt_lps", ras_frame="nmt_ras")
                return ras_mm_to_voxel(target_ras, ras_frame="nmt_ras", voxel_frame="nmt", affine=self.nmt_affine)
            ras = voxel_to_ras_mm(points, voxel_frame="nmt", ras_frame="nmt_ras", affine=self.nmt_affine)
            lps = ras_to_lps_mm(ras, ras_frame="nmt_ras", lps_frame="nmt_lps")
            mapped = apply_saved_point_chain(lps, source_frame="nmt_lps", target_frame="shared_pitch10_lps",
                                             transforms=self.registration.reverse, apply=apply)
            target_ras = lps_to_ras_mm(mapped, lps_frame="shared_pitch10_lps", ras_frame="shared_pitch10_ras")
            return ras_mm_to_voxel(target_ras, ras_frame="shared_pitch10_ras", voxel_frame="shared_pitch10", affine=self.shared_pitch_affine)
        raise ValueError(f"no Pro_INS point step between {stage} and {nxt}")


def map_swc_rows(rows: Sequence[tuple], route: CoordinateRoute, *, source_frame: str,
                 target_frame: str, apply: Callable[[np.ndarray, Sequence[object]], np.ndarray]) -> list[tuple]:
    """Map in-memory (id,type,x,y,z,radius,parent) rows; preserve graph and radii.

    Radius remains in its original source unit because nonlinear deformation
    has no single scalar radius transform. Callers must label it accordingly.
    """
    if not rows:
        return []
    if any(len(row) != 7 for row in rows):
        raise ValueError("SWC rows require seven fields")
    xyz = np.asarray([row[2:5] for row in rows], dtype=float)
    source_unit = "um" if source_frame == "raw_swc_xyz" else (route.processed_unit if source_frame == route.processed_swc_frame else "voxel")
    mapped = route.convert(Points(xyz, source_frame, source_unit), target_frame, apply=apply)
    return [(row[0], row[1], *mapped.xyz[i], row[5], row[6]) for i, row in enumerate(rows)]
