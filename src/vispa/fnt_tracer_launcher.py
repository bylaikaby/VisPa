"""Fetch one exact native FNT project into a reusable, verified local cache.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
Status: candidate
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _borrowed_route(config: dict, sample: str, neuron: str) -> dict:
    """Read-only route for the legacy raw-SWC -> fnt-from-swc workflow."""
    if not isinstance(sample, str) or not _SAMPLE.fullmatch(sample):
        raise ValueError("sample must be a simple SampleID")
    match = _NEURON.fullmatch(str(neuron))
    if not match:
        raise ValueError("neuron must be a three-digit raw SWC ID")
    settings = (config.get("visual_toolkit") or {}).get("fnt_tracer") or {}
    sources = config.get("sources") or {}
    executable = settings.get("executable")
    converter = settings.get("converter_executable") or (
        Path(executable).parent / "fnt-from-swc.exe" if executable else None)
    if not executable or not Path(executable).is_file():
        raise FileNotFoundError("configured FNT tracer executable is unavailable")
    if not converter or not Path(converter).is_file():
        raise FileNotFoundError("configured FNT converter is unavailable")
    host = str(sources.get("http_host") or sources.get("http_base_url") or "").rstrip("/")
    raw_base = str(sources.get("raw_swc_base") or "").rstrip("/")
    catalog_base = str(settings.get("catalog_base_url") or "").rstrip("/")
    for label, url in (("sources.http_host", host), ("sources.raw_swc_base", raw_base),
                       ("fnt_tracer.catalog_base_url", catalog_base)):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment:
            raise ValueError(f"{label} must be a plain HTTP(S) base URL")
    timeout = int(settings.get("timeout_seconds", 30))
    max_bytes = int(settings.get("max_response_bytes", 64 * 1024 * 1024))
    if timeout <= 0 or max_bytes <= 0:
        raise ValueError("FNT timeout and maximum bytes must be positive")
    raw_name = f"{match.group(1)}.swc"
    return {"sample": sample, "neuron": raw_name,
            "metadata_url": f"{host}/neuronbrowser/api/user/getSampleInfo?"
                            + urllib.parse.urlencode({"project_id": "", "fMOST_id": sample}),
            "raw_url_template": f"{raw_base}/{{project_id}}/{sample}/swc_raw/{raw_name}",
            "catalog_url": f"{catalog_base}/{sample}/catalog",
            "executable": str(Path(executable).resolve()),
            "converter": str(Path(converter).resolve()),
            "converter_sha256": _sha256(Path(converter)),
            "timeout_seconds": timeout, "max_response_bytes": max_bytes,
            "cache_root": str(_cache_root(config, settings))}


def swc2fnt(raw_path: str | Path, converter: str | Path, *,
            timeout_seconds: int = 30, max_bytes: int = 64 * 1024 * 1024) -> Path:
    """Port of legacy tools.py:swc2fnt; output is <raw>.fnt beside the raw copy."""
    raw = Path(raw_path)
    output = Path(str(raw) + ".fnt")
    if not raw.is_file() or output.exists():
        raise ValueError("raw SWC missing or FNT output already exists")
    if raw.stat().st_size <= 0 or raw.stat().st_size > max_bytes:
        raise ValueError("raw SWC exceeds bounded size")
    try:
        completed = subprocess.run([str(converter), str(raw), str(output)],
                                   capture_output=True, text=True, errors="replace",
                                   timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        output.unlink(missing_ok=True)
        raise TimeoutError("fnt-from-swc exceeded timeout") from exc
    if completed.returncode != 0:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"fnt-from-swc exited {completed.returncode}: {completed.stderr[-2000:]}")
    _inspect(output, max_bytes)
    return output


def swc_fnt_tracer(config: dict, sample: str, neuron: str, *, dry_run: bool = False) -> dict:
    """Port of legacy tools.py:swc_fnt_tracer with scoped fresh portal input.

    Fresh PortalSWCProvider fetch -> native converter -> replace FNT line 2 ->
    start tracer. No coordinate transform or image-load claim is made.
    """
    route = _borrowed_route(config, sample, neuron)
    if dry_run:
        return {**route, "status": "planned", "raw_path": None, "project_path": None,
                "receipt_path": None, "pid": None}
    from .data_input_adaptor import PortalSWCProvider
    cache_root = Path(route["cache_root"])
    cache_root.mkdir(parents=True, exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix="legacy-raw-fnt-", dir=cache_root))
    scoped = dict(config)
    scoped["sources"] = {**(config.get("sources") or {}),
                         "legacy_raw_swc_root": str(session / "raw")}
    raw = session / "raw" / sample / route["neuron"]
    project = Path(str(raw) + ".fnt")
    receipt_path = session / "receipt.json"
    log_path = session / "tracer.log"
    provider = PortalSWCProvider(scoped, timeout=route["timeout_seconds"])
    tree = provider.getRawNeuronTreeByID(sample, route["neuron"])
    if tree is None or not raw.is_file():
        raise RuntimeError("fresh portal raw SWC retrieval did not create the scoped input")
    project_id = provider._projects.get(sample)
    raw_url = (route["raw_url_template"].replace("{project_id}", urllib.parse.quote(project_id))
               if project_id else None)
    if raw.stat().st_size > route["max_response_bytes"]:
        raise ValueError("fresh portal raw SWC exceeds configured maximum")
    raw_sha = _sha256(raw)
    produced = swc2fnt(raw, route["converter"], timeout_seconds=route["timeout_seconds"],
                       max_bytes=route["max_response_bytes"])
    if produced != project or _sha256(raw) != raw_sha or _sha256(Path(route["converter"])) != route["converter_sha256"]:
        raise ValueError("raw SWC or converter changed during conversion")
    # Exact legacy operation: text readlines, replace catalog line 2, writelines.
    with project.open("r", encoding="utf-8", newline=None) as stream:
        lines = stream.readlines()
    if len(lines) < 2 or lines[0].rstrip("\r\n").encode() != _HEADER:
        raise ValueError("converter FNT lacks expected text header")
    original_lines = lines[2:]
    lines[1] = route["catalog_url"] + "\n"
    with project.open("w", encoding="utf-8", newline=None) as stream:
        stream.writelines(lines)
    info = _inspect(project, route["max_response_bytes"])
    with project.open("r", encoding="utf-8", newline=None) as stream:
        rebound_lines = stream.readlines()
    if info["catalog_url"] != route["catalog_url"] or rebound_lines[2:] != original_lines:
        raise ValueError("catalog rewrite changed FNT tracing text")
    command = [route["executable"], str(project)]
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=str(Path(route["executable"]).parent),
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   shell=False)
    code = process.poll()
    status = "process_started" if code is None else "exited_immediately"
    receipt = {"schema": "vispa.borrowed-fnt-tools.v1", "status": status,
               "sample": sample, "neuron": route["neuron"], "metadata_url": route["metadata_url"],
               "raw_url_template": route["raw_url_template"], "raw_url": raw_url,
               "raw_path": str(raw),
               "raw_sha256": raw_sha, "raw_tree_node_count": len(tree.points),
               "converter": route["converter"], "converter_sha256": route["converter_sha256"],
               "project_path": str(project), "project_sha256": info["sha256"],
               "tracing_header_count": info["tracing_data_field"],
               "tracing_header_count_semantics": "unknown; not total SWC node count",
               "catalog_url": route["catalog_url"], "log_path": str(log_path),
               "command": command, "pid": process.pid, "exit_code_at_start": code,
               "pixels_loaded": "unverified"}
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if code is not None:
        diagnostic = log_path.read_bytes()[-2000:].decode("utf-8", errors="replace")
        raise RuntimeError(f"FNT tracer exited immediately ({code}): {diagnostic}")
    return {**receipt, "receipt_path": str(receipt_path)}


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
    project_path = folder / "viewer" / filename
    return {"sample": sample, "neuron": f"{neuron_stem}.swc", "url": source_url,
            "catalog_url": catalog_url, "source_path": str(source_path),
            "bound_path": str(project_path), "receipt_path": str(folder / "viewer" / f"{filename}.json"),
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
    return {"size_bytes": size, "sha256": _sha256(path), "tracing_data_field": node_count,
            "node_count": node_count,  # Legacy receipt field; not a full SWC node count.
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
    destination.parent.mkdir(parents=True, exist_ok=True)
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
        with source.open("rb") as original, Path(temp_name).open("rb") as bound:
            original.readline(); original.readline()
            bound.readline(); bound.readline()
            while True:
                source_chunk = original.read(1024 * 1024)
                if source_chunk != bound.read(1024 * 1024):
                    raise ValueError("bound FNT tracing payload differs; source preserved")
                if not source_chunk:
                    break
        if destination.exists():
            raise FileExistsError("bound FNT cache appeared during binding; existing file preserved")
        os.replace(temp_name, destination)
        return info
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def resolve_native_fnt_plan(config: dict, sample: str, neuron: str,
                            raw_path: str | Path | None = None) -> dict:
    """Read-only plan for one raw-SWC-derived native session."""
    if not isinstance(sample, str) or not _SAMPLE.fullmatch(sample):
        raise ValueError("sample must be a simple SampleID")
    match = _NEURON.fullmatch(str(neuron))
    if match is None:
        raise ValueError("neuron must be a three-digit raw SWC ID")
    name = f"{match.group(1)}.swc"
    settings = (config.get("visual_toolkit") or {}).get("fnt_tracer") or {}
    catalog_base = str(settings.get("catalog_base_url") or "").rstrip("/")
    parsed = urllib.parse.urlsplit(catalog_base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("configure a plain HTTP(S) catalog_base_url")
    if raw_path is None:
        raw_root = (config.get("sources") or {}).get("legacy_raw_swc_root")
        if not raw_root:
            raise ValueError("configure sources.legacy_raw_swc_root or pass an explicit raw_path")
        from .data_input_adaptor import resolve_declared_raw_swc
        raw = resolve_declared_raw_swc(raw_root, sample, name)
        source_declaration = "sources.legacy_raw_swc_root"
    else:
        raw = Path(raw_path).expanduser()
        if raw.name.lower() != name.lower():
            raise ValueError("explicit raw SWC filename must match the requested neuron")
        source_declaration = "explicit raw_path"
    if not raw.is_file():
        raise FileNotFoundError(f"raw SWC does not exist: {raw}")
    executable = settings.get("executable")
    converter = settings.get("converter_executable") or (Path(executable).parent / "fnt-from-swc.exe" if executable else None)
    if converter is None or not Path(converter).is_file():
        raise FileNotFoundError("configure fnt_tracer.converter_executable or an executable with sibling fnt-from-swc.exe")
    raw, converter = raw.resolve(), Path(converter).resolve()
    from .data_input_adaptor import read_swc
    raw_tree_node_count = len(read_swc(raw).points)
    raw_sha, converter_sha = _sha256(raw), _sha256(converter)
    catalog_url = f"{catalog_base}/{sample}/catalog"
    identity = hashlib.sha256(f"{raw_sha}\0{converter_sha}\0{catalog_url}".encode()).hexdigest()
    folder = _cache_root(config, settings) / "native" / sample / match.group(1) / identity[:20]
    project = folder / f"{name}.fnt"
    return {"schema": "vispa.native-fnt-plan.v1", "sample": sample, "neuron": name,
            "raw_path": str(raw), "raw_sha256": raw_sha, "converter_path": str(converter),
            "converter_sha256": converter_sha, "catalog_url": catalog_url,
            "project_path": str(project), "receipt_path": str(project.with_suffix(".json")),
            "timeout_seconds": int(settings.get("timeout_seconds", 30)),
            "max_response_bytes": int(settings.get("max_response_bytes", 64 * 1024 * 1024)),
            "frame": "raw SWC coordinates; catalog correspondence unverified",
            "source_declaration": source_declaration,
            "raw_tree_node_count": raw_tree_node_count, "identity": identity}


def validate_native_fnt(plan: dict) -> dict:
    """Recheck source, converter, catalog, project and receipt at launch."""
    project, receipt_path = Path(plan["project_path"]), Path(plan["receipt_path"])
    if not receipt_path.is_file() or not project.is_file():
        raise FileNotFoundError("native FNT project or receipt is missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "vispa.native-fnt-cache.v1":
        raise ValueError("native FNT receipt schema differs")
    for key in ("sample", "neuron", "raw_path", "raw_sha256", "converter_path",
                "converter_sha256", "catalog_url", "project_path", "identity", "frame",
                "source_declaration", "raw_tree_node_count"):
        if receipt.get(key) != plan.get(key):
            raise ValueError(f"native FNT receipt {key} differs")
    if _sha256(Path(plan["raw_path"])) != plan["raw_sha256"]:
        raise ValueError("raw SWC SHA-256 changed")
    if _sha256(Path(plan["converter_path"])) != plan["converter_sha256"]:
        raise ValueError("FNT converter SHA-256 changed")
    info = _inspect(project, plan["max_response_bytes"])
    if info["sha256"] != receipt.get("project_sha256") or info["catalog_url"] != plan["catalog_url"]:
        raise ValueError("native FNT project hash or catalog differs")
    return receipt


def prepare_native_fnt(config: dict, sample: str, neuron: str,
                       raw_path: str | Path | None = None, dry_run: bool = False) -> dict:
    """Convert one bounded local raw SWC into a cached, catalog-bound FNT."""
    plan = resolve_native_fnt_plan(config, sample, neuron, raw_path)
    if dry_run:
        return {**plan, "status": "planned"}
    if plan["timeout_seconds"] <= 0 or plan["max_response_bytes"] <= 0:
        raise ValueError("native FNT timeout and maximum bytes must be positive")
    project, receipt_path = Path(plan["project_path"]), Path(plan["receipt_path"])
    if project.exists() or receipt_path.exists():
        validate_native_fnt(plan)
        return {**plan, "status": "cached"}
    project.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".raw-native-", suffix=".fnt", dir=project.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        try:
            completed = subprocess.run([plan["converter_path"], plan["raw_path"], str(temp)],
                                       capture_output=True, text=True, errors="replace",
                                       timeout=plan["timeout_seconds"], check=False)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("native FNT converter exceeded timeout") from exc
        if completed.returncode != 0:
            raise RuntimeError(f"native FNT converter exited {completed.returncode}: {completed.stderr[-2000:]}")
        if _sha256(Path(plan["raw_path"])) != plan["raw_sha256"] or _sha256(Path(plan["converter_path"])) != plan["converter_sha256"]:
            raise ValueError("raw SWC or converter changed during conversion")
        source_info = _inspect(temp, plan["max_response_bytes"])
        original_catalog = source_info["catalog_url"]
        parts = urllib.parse.urlsplit(original_catalog).path.strip("/").split("/")
        if len(parts) == 3 and parts[0] in {"monkeydata", "data"} and parts[2] == "catalog" and parts[1] != sample:
            raise ValueError("converter FNT catalog declares a different SampleID")
        # Rebind the generated temporary file itself; immutable raw SWC remains untouched.
        with temp.open("rb") as stream:
            first, second = stream.readline(), stream.readline()
            rest = stream.read()
        ending = b"\r\n" if second.endswith(b"\r\n") else b"\n"
        temp.write_bytes(first + plan["catalog_url"].encode() + ending + rest)
        info = _inspect(temp, plan["max_response_bytes"])
        if info["catalog_url"] != plan["catalog_url"]:
            raise ValueError("converted FNT catalog binding failed")
        receipt = {key: plan[key] for key in ("sample", "neuron", "raw_path", "raw_sha256",
                   "converter_path", "converter_sha256", "catalog_url", "project_path", "identity", "frame",
                   "source_declaration", "raw_tree_node_count")}
        receipt.update(schema="vispa.native-fnt-cache.v1", project_sha256=info["sha256"],
                       project_bytes=info["size_bytes"], original_converter_catalog=original_catalog,
                       tracing_header_count=info["tracing_data_field"],
                       tracing_header_count_semantics="unknown; not total SWC node count")
        if project.exists() or receipt_path.exists():
            raise FileExistsError("native FNT cache appeared during conversion; preserved")
        receipt_fd, receipt_temp_name = tempfile.mkstemp(prefix=f".{receipt_path.name}.", suffix=".part", dir=project.parent)
        try:
            with os.fdopen(receipt_fd, "w", encoding="utf-8") as output:
                json.dump(receipt, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            if project.exists() or receipt_path.exists():
                raise FileExistsError("native FNT cache appeared during receipt preparation; preserved")
            os.replace(temp, project)
            os.replace(receipt_temp_name, receipt_path)
        finally:
            Path(receipt_temp_name).unlink(missing_ok=True)
        validate_native_fnt(plan)
        return {**plan, "status": "converted"}
    finally:
        temp.unlink(missing_ok=True)


def launch_native_fnt(plan: dict, executable: str | Path) -> dict:
    """Start a validated session and report process state, not image readiness."""
    validate_native_fnt(plan)
    exe = Path(executable)
    if not exe.is_file():
        raise FileNotFoundError(f"FNT tracer executable unavailable: {exe}")
    command = [str(exe), plan["project_path"]]
    fd, stderr_name = tempfile.mkstemp(prefix=".fnt-launch-", suffix=".stderr.log",
                                        dir=Path(plan["project_path"]).parent)
    stderr_path = Path(stderr_name)
    with os.fdopen(fd, "wb") as stderr_stream:
        process = subprocess.Popen(command, cwd=str(exe.parent), stdout=subprocess.DEVNULL,
                                   stderr=stderr_stream)
    code = process.poll()
    if code is not None:
        stderr = stderr_path.read_bytes()[-2000:].decode("utf-8", errors="replace")
        raise RuntimeError(f"FNT tracer exited immediately ({code}): {stderr}")
    return {"status": "process_started", "pid": process.pid, "command": command,
            "project_path": plan["project_path"], "stderr_path": str(stderr_path),
            "pixels_loaded": "unverified"}


def prepare_manual_project(config: dict, plan: dict) -> dict:
    """At launch, bind an explicit project's catalog in a verified user-cache copy."""
    project = Path(plan["project"])
    root = (config.get("visual_toolkit") or {}).get("fnt_tracer", {}).get("project_root")
    if not root or project.parent != Path(root) or not plan["ready"]:
        return plan
    native = resolve_fnt_plan(config, plan["sample"], plan["neuron"])
    limit = native["max_response_bytes"]
    source_info = _inspect(project, limit)
    desired = native["catalog_url"]
    if source_info["catalog_url"] == desired:
        return plan
    parts = urllib.parse.urlsplit(source_info["catalog_url"]).path.strip("/").split("/")
    if (len(parts) == 3 and parts[0] in {"monkeydata", "data"}
            and parts[2] == "catalog" and parts[1] != plan["sample"]):
        raise ValueError("manual FNT catalog declares a different SampleID; source preserved")
    identity = hashlib.sha256((str(project.resolve()) + source_info["sha256"]).encode("utf-8")).hexdigest()[:16]
    bound = Path(native["bound_path"]).parent / "manual" / identity / project.name
    bound.parent.mkdir(parents=True, exist_ok=True)
    _bind_catalog(project, bound, desired, source_info, limit)
    if _sha256(project) != source_info["sha256"]:
        raise ValueError("manual FNT changed during preparation; source preserved")
    bound_info = _inspect(bound, limit)
    receipt = {"schema": "vispa.manual-fnt-binding.v1", "source_path": str(project),
               "source_sha256": source_info["sha256"], "bound_path": str(bound),
               "bound_sha256": bound_info["sha256"],
               "original_catalog": source_info["catalog_url"], "bound_catalog": desired,
               "tracing_payload_byte_identical": True}
    receipt_path = bound.with_suffix(".json")
    if receipt_path.exists():
        if json.loads(receipt_path.read_text(encoding="utf-8")) != receipt:
            raise ValueError("manual FNT binding receipt differs; files preserved for review")
    else:
        fd, temp_name = tempfile.mkstemp(prefix=f".{receipt_path.name}.", suffix=".part", dir=bound.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(receipt, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            if receipt_path.exists():
                raise FileExistsError("manual FNT binding receipt appeared; preserved for review")
            os.replace(temp_name, receipt_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    prepared = dict(plan)
    prepared["project"] = str(bound)
    prepared["command"] = [str(plan["executable"]), str(bound)]
    return prepared


def ensure_fnt(config: dict, sample: str, neuron: str, dry_run: bool = False) -> dict:
    """Explicit portal FNT fallback; never select this as a native raw-SWC session."""
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
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
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
