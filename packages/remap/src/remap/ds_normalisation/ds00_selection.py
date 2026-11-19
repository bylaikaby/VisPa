"""Read the shared DS00 selection without changing ReMAP analysis inputs.

Version: 0.2.0 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-03: Read-only DS00 selection registry. region_ready stays false.
- 2026-11-10: Moved into ds_normalisation/.
Status: candidate
"""
import json
import hashlib
from pathlib import Path


SCHEMA = "vispa.ds00.selection.v1"


def resolve_selection(registry_path: Path, sample_id: str, *, swc_frame: str | None = None) -> dict:
    """Resolve one sample and reject an unproven processed-SWC frame binding."""
    path = Path(registry_path).resolve(strict=True)
    raw = path.read_bytes()
    registry = json.loads(raw)
    if registry.get("schema") != SCHEMA:
        raise ValueError(f"Unsupported DS00 registry schema: {registry.get('schema')}")
    sample = registry.get("samples", {}).get(str(sample_id))
    if not isinstance(sample, dict):
        raise ValueError(f"Sample {sample_id} absent from DS00 registry")
    active = sample.get("active", {})
    variants = sample.get("variants", {})
    selected = {}
    for role in ("native_ds00", "normalization"):
        key = active.get(role)
        if key is None:
            if role == "native_ds00":
                raise ValueError("Native DS00 selection is unset")
            selected[role] = None
            continue
        variant = variants.get(key)
        if not isinstance(variant, dict) or variant.get("role") != role:
            raise ValueError(f"Invalid {role} selection: {key}")
        if role == "normalization" and not variant.get("bundle_path"):
            raise ValueError("Selected normalization lacks a saved bundle")
        if role == "normalization":
            bundle = Path(variant["bundle_path"])
            if not bundle.is_file() or hashlib.sha256(bundle.read_bytes()).hexdigest() != variant.get("bundle_sha256"):
                raise ValueError("Selected normalization bundle absent or hash mismatch")
        selected[role] = {"id": key, **variant}
    native_frame = sample.get("expected_native_frame")
    if not native_frame or selected["native_ds00"].get("frame") != native_frame:
        raise ValueError("Native DS00 frame disagrees with sample expectation")
    if swc_frame is not None:
        raise ValueError("Processed SWC to DS00 frame binding is unverified; no ReMAP region run is authorized by this registry alone")
    return {"schema": "remap.ds00_selection.v1", "registry": str(path),
            "registry_sha256": hashlib.sha256(raw).hexdigest(),
            "registry_revision": registry.get("revision"), "sample_id": str(sample_id),
            "animal": sample.get("animal"), "selected": selected,
            "region_ready": False,
            "step1_binding": "unverified processed-SWC to sharedPitch10 frame; existing atlas/SWC inputs unchanged"}
