"""Shared DS00 selection boundary checks.

Version: 0.1.0.dev10 (local/unreleased)
Last updated: 2026-11-03
Change history: ../CHANGELOG.md
Status: candidate
"""
import hashlib
import json
from pathlib import Path

import pytest

from remap.ds_normalisation.ds00_selection import resolve_selection


def test_read_only_selection_and_fail_closed(tmp_path):
    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}", encoding="utf-8")
    native = {"role": "native_ds00", "frame": "native", "path": "source.nii"}
    norm = {"role": "normalization", "frame": "prepared", "bundle_path": str(bundle),
            "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest()}
    digest = norm["bundle_sha256"]
    data = {"schema": "vispa.ds00.selection.v1", "revision": 2,
            "samples": {"123": {"expected_native_frame": "native", "active": {
                "native_ds00": "raw", "normalization": "fit"},
                "variants": {"raw": native, "fit": norm}}}}
    registry = tmp_path / "registry.json"

    def write():
        registry.write_text(json.dumps(data), encoding="utf-8")

    write()
    result = resolve_selection(registry, "123")
    assert result["region_ready"] is False
    assert result["selected"]["normalization"]["id"] == "fit"
    assert result["registry_sha256"] == hashlib.sha256(registry.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="binding is unverified"):
        resolve_selection(registry, "123", swc_frame="native")
    with pytest.raises(ValueError, match="absent"):
        resolve_selection(registry, "999")
    data["samples"]["123"]["variants"]["fit"]["bundle_sha256"] = "bad"
    write()
    with pytest.raises(ValueError, match="hash mismatch"):
        resolve_selection(registry, "123")
    data["samples"]["123"]["variants"]["fit"]["bundle_sha256"] = digest
    data["samples"]["123"]["variants"]["fit"]["role"] = "prepared"
    write()
    with pytest.raises(ValueError, match="Invalid normalization"):
        resolve_selection(registry, "123")
    data["samples"]["123"]["variants"]["fit"]["role"] = "normalization"
    data["samples"]["123"]["expected_native_frame"] = "other"
    write()
    with pytest.raises(ValueError, match="frame disagrees"):
        resolve_selection(registry, "123")
