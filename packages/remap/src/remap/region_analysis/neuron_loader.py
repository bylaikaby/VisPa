"""Load one neuron SWC from the configured cache or from IONData.

A file already in the cache is used as it is. A missing file is fetched from
the configured host into that same cache. This module does not parse the
graph or change the /250 atlas step.

Version: 0.1.0.dev34 (local/unreleased)
Last updated: 2026-11-10
Change history:
- 2026-11-09: Cache hit stays as stored. Missing SWC, or refresh, fetches from IONData.
- 2026-11-10: Moved from the package root into region_analysis/.
Status: candidate
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request

from .._version import __version__


_ORIGIN = re.compile(r"https?://[^/?#]+")
_MAX_BYTES = 64 * 1024 * 1024


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError(f"IONData redirect refused ({code})")


def _origin(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _default_opener():
    return urllib.request.build_opener(_RefuseRedirect)


def ensure_cached_swc(sample_id: str, neuron_id: str, cache_root, iondata_host=None, *,
                      allow_download: bool = False, refresh: bool = False, opener=None,
                      timeout_seconds: float = 30, max_response_bytes: int = _MAX_BYTES) -> Path:
    """Return one cached SWC, fetching from IONData when it is missing or refresh is set."""
    if Path(neuron_id).name != neuron_id or not str(neuron_id).endswith(".swc"):
        raise ValueError("neuron_id must be an exact SWC basename")
    if not isinstance(refresh, bool):
        raise ValueError("refresh must be a boolean")
    root = Path(cache_root).resolve()
    flat = (root / neuron_id).resolve()
    nested = (root / str(sample_id) / neuron_id).resolve()
    if flat.parent != root or nested.parent.parent != root:
        raise ValueError("SWC path must stay inside the configured cache")
    existing = flat if flat.is_file() else nested if nested.is_file() else None
    if existing is not None and not refresh:
        return existing
    destination = existing or (flat if root.name == str(sample_id) else nested)
    if not allow_download and not refresh:
        raise FileNotFoundError(f"SWC is not in the cache: {sample_id}/{neuron_id}")
    host = str(iondata_host or "").rstrip("/")
    if not _ORIGIN.fullmatch(host):
        raise ValueError("iondata_host must be an HTTP(S) origin to fetch a missing SWC")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds)) or not 1 <= float(timeout_seconds) <= 60
            or isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int)
            or not 1024 <= max_response_bytes <= _MAX_BYTES):
        raise ValueError("SWC fetch timeout or byte limit is invalid")
    query = urllib.parse.urlencode({"sampleid": sample_id, "neuronid": neuron_id})
    url = f"{host}/neuronbrowser/api/user/getSWC?{query}"
    payload = _read_bounded(url, float(timeout_seconds), max_response_bytes, opener or _default_opener())
    text = payload.decode("utf-8-sig")
    from .neuron_table import parse_swc
    parse_swc(text, source=url)
    digest = hashlib.sha256(payload).hexdigest()
    if destination.is_file():
        cached = destination.read_bytes()
        if hashlib.sha256(cached).hexdigest() == digest:
            return destination
        if not refresh:
            raise FileExistsError(f"cached SWC differs from the IONData response: {destination}")
        _replace_bytes(destination, payload)
        stored = destination.read_bytes()
        if hashlib.sha256(stored).hexdigest() != digest:
            raise RuntimeError(f"cached SWC hash changed while publishing: {destination}")
        _write_receipt(destination, sample_id, neuron_id, url, digest, exclusive=False)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(destination, flags)
    try:
        view = payload
        while view:
            written = os.write(fd, view)
            view = view[written:]
    finally:
        os.close(fd)
    _write_receipt(destination, sample_id, neuron_id, url, digest, exclusive=True)
    stored = destination.read_bytes()
    if hashlib.sha256(stored).hexdigest() != digest:
        raise RuntimeError(f"cached SWC hash changed while publishing: {destination}")
    return destination


def _replace_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _write_receipt(destination: Path, sample_id, neuron_id, url, digest, *, exclusive: bool) -> None:
    receipt = {"role": "processed", "loader": "remap.region_analysis.neuron_loader",
               "version": __version__, "sample_id": str(sample_id),
               "neuron_id": neuron_id, "origin_url": url,
               "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
               "sha256": digest, "active_path": str(destination)}
    receipt_path = destination.with_name(destination.name + ".source.json")
    if exclusive:
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
        return
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")


def _read_bounded(url: str, timeout: float, limit: int, opener) -> bytes:
    expected = _origin(url)
    request = urllib.request.Request(url, headers={"User-Agent": f"ReMAP/{__version__}"})
    with opener.open(request, timeout=timeout) as response:
        if _origin(response.geturl()) != expected:
            raise RuntimeError("IONData response origin differs from iondata_host")
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"HTTP {response.status} for SWC")
        payload = response.read(limit + 1)
    if not payload or len(payload) > limit:
        raise ValueError("IONData SWC response is empty or exceeds the byte limit")
    return payload
