"""Fetch one exact native FNT project into a reusable, verified local cache.

Version: 1.11.0.dev8 (local/unreleased)
Last updated: 2026-10-23
Change history: ../../CHANGELOG.md
Status: candidate
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


_SAMPLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_NEURON = re.compile(r"([0-9]{3})(?:\.swc)?\Z", re.IGNORECASE)
_HEADER = b"Fast Neurite Tracer Session File 1.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_root(config: dict, settings: dict) -> Path:
    configured = settings.get("cache_root")
    if configured:
        return Path(configured).expanduser()
    shared_cache = (config.get("defaults") or {}).get("cache_root")
    if shared_cache:
        return Path(shared_cache).expanduser() / "fnt"
    user_data = os.environ.get("LOCALAPPDATA")
    return (Path(user_data) if user_data else Path.home() / ".cache") / "VisPa" / "cache" / "fnt"


def resolve_fnt_plan(config: dict, sample: str, neuron: str) -> dict:
    """Resolve one native route and cache layout without I/O or side effects."""
    if not isinstance(sample, str) or not _SAMPLE.fullmatch(sample):
        raise ValueError("sample must be a simple SampleID")
    match = _NEURON.fullmatch(str(neuron))
    if match is None:
        raise ValueError("native FNT route supports only a three-digit neuron ID, with optional .swc")
    settings = (config.get("visual_toolkit") or {}).get("fnt_tracer") or {}
    if not settings.get("server_base_url") or not settings.get("catalog_base_url"):
        raise ValueError("configure visual_toolkit.fnt_tracer.server_base_url and catalog_base_url")
    source_base = str(settings["server_base_url"]).rstrip("/")
    catalog_base = str(settings["catalog_base_url"]).rstrip("/")
    for name, value in (("server_base_url", source_base), ("catalog_base_url", catalog_base)):
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError(f"{name} must be a plain HTTP(S) base URL")
    neuron_stem = match.group(1)
    filename = f"{sample}-{neuron_stem}-merge.fnt"
    source_url = f"{source_base}/{sample}/{sample}/merge/{filename}"
    catalog_url = f"{catalog_base}/{sample}/catalog"
    host = urllib.parse.urlsplit(source_base).netloc.replace(":", "_")
    # The base path is part of cache identity so distinct configured routes cannot collide.
    source_namespace = hashlib.sha256(source_base.encode("utf-8")).hexdigest()[:12]
    folder = _cache_root(config, settings) / host / source_namespace / sample
    source_path = folder / filename
    project_path = folder / f"{sample}-{neuron_stem}-merge.catalog-bound.fnt"
    return {"sample": sample, "neuron": f"{neuron_stem}.swc", "url": source_url,
            "catalog_url": catalog_url, "source_path": str(source_path),
            "bound_path": str(project_path), "receipt_path": str(folder / f"{filename}.json"),
            "timeout_seconds": int(settings.get("timeout_seconds", 30)),
            "max_response_bytes": int(settings.get("max_response_bytes", 64 * 1024 * 1024)),
            "auto_download": settings.get("auto_download", True)}


def _inspect(path: Path, max_bytes: int) -> dict:
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ValueError("FNT size is empty or exceeds configured maximum")
    with path.open("rb") as stream:
        first = stream.readline(65537)
        second = stream.readline(65537)
        if len(first) > 65536 or len(second) > 65536 or first.rstrip(b"\r\n") != _HEADER:
            raise ValueError("FNT header is invalid")
        before_marker = len(first) + len(second)
        found = False
        for _ in range(4096):
            line = stream.readline(65537)
            before_marker += len(line)
            if len(line) > 65536 or before_marker > 1024 * 1024:
                raise ValueError("FNT header exceeds safe scan limit")
            if not line:
                break
            if line.rstrip(b"\r\n") == b"BEGIN_TRACING_DATA":
                found = True
                break
        count_line = stream.readline(65537) if found else b""
        first_payload_line = stream.readline(65537) if count_line else b""
    if not found or len(count_line) > 65536 or not count_line.rstrip(b"\r\n").isdigit():
        raise ValueError("FNT tracing-data marker or node count is invalid")
    node_count = int(count_line.rstrip(b"\r\n"))
    if node_count <= 0:
        raise ValueError("FNT declares no tracing nodes")
    if not first_payload_line or len(first_payload_line) > 65536:
        raise ValueError("FNT tracing payload is empty or malformed")
    try:
        catalog = second.rstrip(b"\r\n").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("FNT catalog line is not UTF-8") from exc
    return {"size_bytes": size, "sha256": _sha256(path), "node_count": node_count,
            "catalog_url": catalog, "first_line": first, "second_line": second}


def _download(url: str, destination: Path, timeout: int, max_bytes: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            request = urllib.request.Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "VisPa"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise ValueError(f"FNT response returned HTTP {status}; expected 200")
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > max_bytes:
                    raise ValueError("FNT response exceeds configured maximum")
                total = 0
                while True:
                    chunk = response.read(min(1024 * 1024, max_bytes - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("FNT response exceeds configured maximum")
                    output.write(chunk)
                if declared and total != int(declared):
                    raise ValueError("FNT response ended before declared Content-Length")
            output.flush()
            os.fsync(output.fileno())
        _inspect(Path(temp_name), max_bytes)
        if destination.exists():
            raise FileExistsError("FNT cache appeared during download; existing file preserved")
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _bind_catalog(source: Path, destination: Path, desired: str, source_info: dict, max_bytes: int) -> dict:
    if destination.exists():
        info = _inspect(destination, max_bytes)
        if info["catalog_url"] != desired or info["node_count"] != source_info["node_count"]:
            raise ValueError("existing bound FNT cache differs; preserved for review")
        with source.open("rb") as original, destination.open("rb") as bound:
            original.readline(); original.readline()
            bound.readline(); bound.readline()
            while True:
                source_chunk = original.read(1024 * 1024)
                if source_chunk != bound.read(1024 * 1024):
                    raise ValueError("existing bound FNT tracing payload differs; preserved for review")
                if not source_chunk:
                    break
        return info
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as original:
            output.write(original.readline())
            old_second = original.readline()
            ending = b"\r\n" if old_second.endswith(b"\r\n") else b"\n"
            output.write(desired.encode("utf-8") + ending)
            shutil.copyfileobj(original, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        info = _inspect(Path(temp_name), max_bytes)
        if info["catalog_url"] != desired or info["node_count"] != source_info["node_count"]:
            raise ValueError("bound FNT validation failed")
        if destination.exists():
            raise FileExistsError("bound FNT cache appeared during binding; existing file preserved")
        os.replace(temp_name, destination)
        return info
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def ensure_fnt(config: dict, sample: str, neuron: str, dry_run: bool = False) -> dict:
    """Fetch and validate one exact FNT; return a nonfatal status for GUI Render."""
    try:
        plan = resolve_fnt_plan(config, sample, neuron)
    except (TypeError, ValueError) as exc:
        return {"status": "unsupported", "sample": sample, "neuron": neuron, "errors": [str(exc)]}
    result = {"status": "planned" if dry_run else "pending", "sample": plan["sample"],
              "neuron": plan["neuron"], "url": plan["url"], "source_path": plan["source_path"],
              "project_path": None, "sha256": None, "node_count": None, "errors": [],
              "dry_run": bool(dry_run), "catalog_url": plan["catalog_url"]}
    if dry_run:
        result["project_path"] = plan["bound_path"]
        return result
    if not plan["auto_download"] and not Path(plan["source_path"]).exists():
        result.update(status="disabled", errors=["FNT auto-download is disabled"])
        return result
    source = Path(plan["source_path"])
    bound = Path(plan["bound_path"])
    receipt_path = Path(plan["receipt_path"])
    try:
        if plan["timeout_seconds"] <= 0 or plan["max_response_bytes"] <= 0:
            raise ValueError("FNT timeout and maximum bytes must be positive")
        existing = None
        if receipt_path.exists():
            try:
                existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError("existing FNT cache receipt is unreadable; preserved for review") from exc
            if (not isinstance(existing, dict) or existing.get("schema") != "vispa.fnt-cache.v1"
                    or existing.get("sample") != plan["sample"]
                    or existing.get("neuron") != plan["neuron"]
                    or existing.get("url") != plan["url"]
                    or existing.get("source_path") != str(source)
                    or existing.get("source_sha256") is None):
                raise ValueError("existing FNT cache receipt identity differs; preserved for review")
        downloaded = not source.exists()
        if existing and downloaded:
            raise ValueError("FNT source recorded by cache receipt is absent; receipt preserved for review")
        if downloaded:
            _download(plan["url"], source, plan["timeout_seconds"], plan["max_response_bytes"])
        source_info = _inspect(source, plan["max_response_bytes"])
        if existing and source_info["sha256"] != existing["source_sha256"]:
            raise ValueError("FNT source SHA-256 differs from cache receipt; files preserved for review")
        if existing and existing.get("source_bytes") != source_info["size_bytes"]:
            raise ValueError("FNT source size differs from cache receipt; files preserved for review")
        catalog_parts = urllib.parse.urlsplit(source_info["catalog_url"]).path.strip("/").split("/")
        if (len(catalog_parts) == 3 and catalog_parts[0] in {"monkeydata", "data"}
                and catalog_parts[2] == "catalog" and catalog_parts[1] != plan["sample"]):
            raise ValueError("FNT source catalog declares a different SampleID; files preserved for review")
        if existing and bound.exists() and existing.get("project_path") == str(bound):
            if _sha256(bound) != existing.get("project_sha256"):
                raise ValueError("bound FNT SHA-256 differs from cache receipt; files preserved for review")
        if source_info["catalog_url"] == plan["catalog_url"]:
            project, project_info = source, source_info
        else:
            project = bound
            project_info = _bind_catalog(source, bound, plan["catalog_url"], source_info,
                                         plan["max_response_bytes"])
        if existing and (existing.get("project_path") != str(project)
                         or existing.get("project_sha256") != project_info["sha256"]):
            raise ValueError("FNT project differs from cache receipt; files preserved for review")
        receipt = {"schema": "vispa.fnt-cache.v1", "sample": plan["sample"],
                   "neuron": plan["neuron"], "url": plan["url"],
                   "source_path": str(source), "source_sha256": source_info["sha256"],
                   "source_bytes": source_info["size_bytes"], "source_catalog_url": source_info["catalog_url"],
                   "project_path": str(project), "project_sha256": project_info["sha256"],
                   "project_catalog_url": project_info["catalog_url"],
                   "node_count": source_info["node_count"], "source_date": None,
                   "fetched_at": datetime.now(timezone.utc).isoformat() if downloaded else None}
        if not downloaded and existing and existing.get("source_sha256") == source_info["sha256"]:
            receipt["fetched_at"] = existing.get("fetched_at")
        if receipt != existing:
            fd, temp_name = tempfile.mkstemp(prefix=f".{receipt_path.name}.", suffix=".tmp", dir=receipt_path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(receipt, stream, indent=2)
                    stream.write("\n")
                    stream.flush(); os.fsync(stream.fileno())
                os.replace(temp_name, receipt_path)
            finally:
                if os.path.exists(temp_name): os.unlink(temp_name)
        result.update(status="downloaded" if downloaded else "cached", project_path=str(project),
                      sha256=project_info["sha256"], node_count=source_info["node_count"],
                      source_sha256=source_info["sha256"], source_bytes=source_info["size_bytes"],
                      receipt_path=str(receipt_path), fetched_at=receipt["fetched_at"])
    except (OSError, ValueError, OverflowError) as exc:
        result.update(status="failed", errors=[str(exc)])
    return result
