"""Explicit data-input adaptor for local SWCs and source-tree providers.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import tempfile
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

def load():
    """Load configuration lazily so source parsing remains usable on its own."""
    from .config import load as load_config
    return load_config()

_provider_factory: Callable | None = None


def set_iondata_provider_factory(factory: Callable | None) -> None:
    """Register a project-specific provider factory; pass None to restore local SWC."""
    global _provider_factory
    _provider_factory = factory


configure_iondata_provider = set_iondata_provider_factory


@dataclass
class SWCNode:
    id: int
    type: int
    x: float
    y: float
    z: float
    radius: float
    parent_id: int

    @property
    def xyz(self):
        return (self.x, self.y, self.z)


@dataclass
class SWCEdge:
    data: list[SWCNode]


@dataclass
class SWCTree:
    root: SWCNode
    edges: list[SWCEdge]
    points: list[SWCNode]


def list_neurons(sample_id: str, config: dict | None = None, *, source: str | None = None) -> dict:
    """Read one sample's catalog from configured CSV or the live IONData API.

    CSV remains the mode for older configurations. Live results are a bounded,
    timestamped in-memory snapshot; there is no implicit CSV fallback.
    """
    _validate_sample_id(sample_id)
    resolved = config if config is not None else load()
    catalog = (resolved.get("sources") or {}).get("neuron_catalog")
    if not isinstance(catalog, dict):
        raise ValueError("no sources.neuron_catalog.path or live-iondata source is configured")
    mode = source if source is not None else catalog.get("mode", "csv")
    if mode not in {"csv", "live-iondata"}:
        raise ValueError("source must be 'csv' or 'live-iondata'")
    if mode == "live-iondata":
        result = _list_live_neurons(sample_id, catalog)
    else:
        csv_catalog = dict(catalog)
        if catalog.get("mode") == "live-iondata":
            csv_catalog["path"] = catalog.get("snapshot_path")
        result = _list_csv_neurons(sample_id, csv_catalog)
    for row in result["rows"]:
        if result.get("snapshot_id"):
            row["snapshot_id"] = result["snapshot_id"]
    return result


def _validate_sample_id(sample_id: str) -> None:
    if not isinstance(sample_id, str):
        raise TypeError("sample_id must be an exact string identifier")
    if (not sample_id or sample_id != sample_id.strip()
            or any(ord(char) < 32 for char in sample_id)):
        raise ValueError("sample_id must be a nonempty exact identifier without control characters")


def _safe_neuron_id(neuron_id, context: str, sample_id: str) -> str:
    if (not isinstance(neuron_id, str) or not neuron_id or neuron_id != neuron_id.strip()
            or "/" in neuron_id or "\\" in neuron_id or ":" in neuron_id
            or ".." in neuron_id or any(ord(char) < 32 for char in neuron_id)):
        raise ValueError(
            f"{context}: neuron ID must be an exact safe basename without path separators, "
            f"colon, or '..' for sample {sample_id!r}")
    return neuron_id


def _list_live_neurons(sample_id: str, catalog: dict) -> dict:
    request_url = catalog_request_url(sample_id, catalog)
    timeout_value = catalog.get("timeout_seconds", 10)
    byte_value = catalog.get("max_response_bytes", 8 * 1024 * 1024)
    if (isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float))
            or not math.isfinite(timeout_value) or not 1 <= timeout_value <= 60):
        raise ValueError("sources.neuron_catalog.timeout_seconds must be between 1 and 60")
    if (isinstance(byte_value, bool) or not isinstance(byte_value, int)
            or not 1024 <= byte_value <= 32 * 1024 * 1024):
        raise ValueError("sources.neuron_catalog.max_response_bytes must be between 1024 and 33554432")
    timeout = float(timeout_value)
    max_bytes = byte_value
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.getcode()
        raw_bytes = response.read(max_bytes + 1)
    if status != 200:
        raise RuntimeError(f"IONData neuron catalog returned HTTP {status}: {request_url}")
    if len(raw_bytes) > max_bytes:
        raise ValueError(f"IONData neuron catalog exceeded the {max_bytes}-byte response limit")
    try:
        source_rows = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"IONData neuron catalog returned invalid UTF-8 JSON: {request_url}") from exc
    if not isinstance(source_rows, list):
        raise ValueError("IONData neuron catalog response must be a JSON array")

    rows = []
    seen = set()
    for index, source_row in enumerate(source_rows):
        if not isinstance(source_row, dict):
            raise ValueError(f"IONData catalog row {index + 1} must be an object")
        row_sample = source_row.get("sampleid")
        if not isinstance(row_sample, str) or row_sample != sample_id:
            raise ValueError(
                f"IONData catalog row {index + 1} has sampleid {row_sample!r}; "
                f"expected exact sample {sample_id!r}")
        neuron_id = _safe_neuron_id(source_row.get("name"), f"IONData row {index + 1}", sample_id)
        if neuron_id in seen:
            raise ValueError(f"IONData catalog has duplicate neuron ID {neuron_id!r} for sample {sample_id!r}")
        seen.add(neuron_id)
        rows.append({
            "sample_id": sample_id,
            "neuron_id": neuron_id,
            "portal_region": _string_or_empty(source_row.get("region"), f"row {index + 1} region"),
            "type": _string_or_empty(source_row.get("type"), f"row {index + 1} type"),
            "exclude": _string_or_empty(source_row.get("exclude"), f"row {index + 1} exclude"),
            "comment": _string_or_empty(source_row.get("comment"), f"row {index + 1} comment"),
        })
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    response_sha = hashlib.sha256(raw_bytes).hexdigest()
    return {"sample_id": sample_id, "monkey_id": "", "source_kind": "live-iondata",
            "source_path": request_url, "request_url": request_url, "source_date": "live",
            "fetched_at": fetched_at, "sha256": response_sha, "source_size": len(raw_bytes),
            "count": len(rows), "rows": rows,
            "snapshot_id": hashlib.sha256(
                f"{sample_id}\0{fetched_at}\0{response_sha}".encode("utf-8")).hexdigest()}


def catalog_request_url(sample_id: str, catalog: dict) -> str:
    """Resolve the observed IONData route without sending a request."""
    _validate_sample_id(sample_id)
    host = str(catalog.get("host") or "").rstrip("/")
    parsed_host = urllib.parse.urlsplit(host)
    if (parsed_host.scheme not in {"http", "https"} or not parsed_host.netloc
            or parsed_host.username or parsed_host.password
            or parsed_host.path or parsed_host.query or parsed_host.fragment):
        raise ValueError("sources.neuron_catalog.host must be an HTTP(S) origin without credentials or path")
    try:
        parsed_host.port
    except ValueError as exc:
        raise ValueError("sources.neuron_catalog.host has an invalid port") from exc
    encoded_id = urllib.parse.quote(sample_id, safe="")
    return f"{host}/neuronbrowser/api/user/selectNeurons?id={encoded_id}"


def _string_or_empty(value, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"IONData {label} must be a scalar string/number/boolean")
    return str(value)


def _list_csv_neurons(sample_id: str, catalog: dict) -> dict:
    if not catalog.get("path"):
        raise ValueError("no sources.neuron_catalog.path is configured for CSV mode")
    path = Path(catalog["path"]).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"configured neuron catalog does not exist: {path}")
    columns = catalog.get("columns") or {}
    sample_column = str(columns.get("sample", "sample"))
    neuron_column = str(columns.get("neuron_id", "neuron_id"))
    region_column = str(columns.get("portal_region", "portal_region"))
    monkey_column = columns.get("monkey")
    before = path.stat()
    raw_bytes = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"{path}: neuron catalog changed while it was being read; retry the list load")
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    required = {sample_column, neuron_column, region_column}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        missing = sorted(required - set(reader.fieldnames or ()))
        raise ValueError(f"{path}: neuron catalog is missing required column(s): {missing}")
    if monkey_column and monkey_column not in reader.fieldnames:
        raise ValueError(f"{path}: neuron catalog is missing monkey column {monkey_column!r}")

    rows = []
    seen = {}
    monkeys = set()
    for line_number, source_row in enumerate(reader, 2):
        exact_sample = source_row.get(sample_column, "")
        if exact_sample != sample_id:
            continue
        neuron_id = source_row.get(neuron_column, "")
        _safe_neuron_id(neuron_id, f"{path}:{line_number}", sample_id)
        if neuron_id in seen:
            raise ValueError(
                f"{path}:{line_number}: duplicate neuron ID {neuron_id!r} for sample {sample_id!r}; "
                f"first seen on line {seen[neuron_id]}"
            )
        seen[neuron_id] = line_number
        region = source_row.get(region_column, "")
        region = "" if region is None else region
        monkey = source_row.get(monkey_column, "") if monkey_column else ""
        monkey = "" if monkey is None else monkey
        if monkey:
            monkeys.add(monkey)
        rows.append({"sample_id": sample_id, "neuron_id": neuron_id,
                     "portal_region": region, "monkey_id": monkey})
    if len(monkeys) > 1:
        raise ValueError(f"{path}: sample {sample_id!r} maps to multiple monkey IDs: {sorted(monkeys)}")
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    return {"sample_id": sample_id, "monkey_id": next(iter(monkeys), ""),
            "source_kind": "csv", "source_path": str(path),
            "source_date": str(catalog.get("source_date") or "unknown"),
            "request_url": None, "fetched_at": None,
            "sha256": raw_sha, "source_size": after.st_size,
            "source_mtime_ns": after.st_mtime_ns, "count": len(rows), "rows": rows}


def catalog_snapshot_unchanged(snapshot: dict) -> bool:
    """Fast invalidation guard for a loaded list; the full SHA is captured at load."""
    if snapshot.get("source_kind") == "live-iondata":
        try:
            expected_id = hashlib.sha256(
                f"{snapshot['sample_id']}\0{snapshot['fetched_at']}\0{snapshot['sha256']}".encode("utf-8")
            ).hexdigest()
            return (isinstance(snapshot.get("sample_id"), str)
                    and isinstance(snapshot.get("snapshot_id"), str)
                    and snapshot["snapshot_id"] == expected_id
                    and len(snapshot.get("sha256", "")) == 64
                    and isinstance(snapshot.get("request_url"), str)
                    and snapshot.get("request_url", "").startswith(("http://", "https://"))
                    and all(row.get("snapshot_id") == expected_id for row in snapshot.get("rows", [])))
        except (KeyError, TypeError, AttributeError):
            return False
    try:
        stat = Path(snapshot["source_path"]).stat()
    except (KeyError, OSError, TypeError):
        return False
    return (stat.st_size == snapshot.get("source_size")
            and stat.st_mtime_ns == snapshot.get("source_mtime_ns"))


def catalog_matches_sample(requested_sample: str, current_sample: str) -> bool:
    """Guard asynchronous catalog results and row selection against sample edits."""
    return str(requested_sample) == str(current_sample).strip()


def catalog_selection_id(sample_id: str, current_sample: str, snapshot: dict,
                         row: dict) -> str | None:
    """Return the exact SWC ID only for a current row from an unchanged snapshot."""
    if not catalog_matches_sample(sample_id, current_sample):
        return None
    if (row.get("sample_id") != str(sample_id)
            or not catalog_snapshot_unchanged(snapshot)
            or (snapshot.get("source_kind") == "live-iondata"
                and (row.get("snapshot_id") != snapshot.get("snapshot_id")
                     or row not in snapshot.get("rows", [])))):
        return None
    neuron_id = row.get("neuron_id")
    return neuron_id if isinstance(neuron_id, str) and neuron_id else None


def read_swc(path: str | Path) -> SWCTree:
    """Read a checked SWC and expose the root/edge protocol used by renderers."""
    path = Path(path)
    nodes: dict[int, SWCNode] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 7:
            raise ValueError(f"{path}:{line_no}: SWC row must have 7 fields")
        try:
            node_id, kind = int(fields[0]), int(fields[1])
            xyzr = tuple(float(v) for v in fields[2:6])
            parent_id = int(fields[6])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_no}: invalid numeric SWC field") from exc
        import math
        if node_id in nodes or not all(math.isfinite(v) for v in xyzr) or xyzr[3] < 0:
            raise ValueError(f"{path}:{line_no}: duplicate id or invalid coordinate/radius")
        nodes[node_id] = SWCNode(node_id, kind, *xyzr, parent_id)
    if not nodes:
        raise ValueError(f"{path}: no SWC nodes")
    roots = [node for node in nodes.values() if node.parent_id == -1]
    if len(roots) != 1:
        raise ValueError(f"{path}: expected exactly one root, found {len(roots)}")
    children: dict[int, list[int]] = {node_id: [] for node_id in nodes}
    for node in nodes.values():
        if node.parent_id != -1:
            if node.parent_id not in nodes:
                raise ValueError(f"{path}: node {node.id} has missing parent {node.parent_id}")
            children[node.parent_id].append(node.id)
    reached = set()
    pending = [roots[0].id]
    while pending:
        node_id = pending.pop()
        if node_id in reached:
            raise ValueError(f"{path}: cycle or repeated parent path at node {node_id}")
        reached.add(node_id)
        pending.extend(children[node_id])
    if len(reached) != len(nodes):
        raise ValueError(f"{path}: {len(nodes) - len(reached)} node(s) are disconnected from the root")
    edges = [SWCEdge([node, nodes[child_id]]) for node in nodes.values()
             for child_id in children[node.id]]
    return SWCTree(roots[0], edges, list(nodes.values()))


class LocalSWCProvider:
    def __init__(self, config=None):
        self.config = config if config is not None else load()

    def getRawNeuronTreeByID(self, sample_id: str, neuron_id: str):
        sample_id = str(sample_id)
        if not sample_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in sample_id):
            raise ValueError("sample_id must be a simple identifier")
        sample = self.config.get("samples", {}).get(str(sample_id), {})
        name = str(neuron_id)
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("neuron_id must be a filename, not a path")
        if not name.lower().endswith(".swc"):
            name += ".swc"
        roots = []
        if sample.get("swc_cache") is not None:
            roots.append(Path(sample["swc_cache"]))
        legacy_root = self.config.get("sources", {}).get("legacy_raw_swc_root")
        if legacy_root:
            roots.append(Path(legacy_root) / sample_id)
        visited = set()
        for root in roots:
            root = root.resolve()
            if root in visited:
                continue
            visited.add(root)
            path = root / name
            if path.is_file():
                return read_swc(path)
        return None


class PortalSWCProvider:
    """Fetch a missing raw SWC from the configured portal and cache it locally.

    ``sources.http_host`` serves the sample metadata and
    ``sources.raw_swc_base`` serves ``<project>/<sample>/swc_raw/<neuron>``.
    A fetched file is written to ``sources.legacy_raw_swc_root/<sample>/`` so
    later loads reuse it without another request.
    """

    def __init__(self, config=None, timeout: float = 30.0):
        self.config = config if config is not None else load()
        sources = self.config.get("sources") or {}
        self.host = str(sources.get("http_host") or sources.get("http_base_url") or "").rstrip("/")
        self.raw_base = str(sources.get("raw_swc_base") or "").rstrip("/")
        root = sources.get("legacy_raw_swc_root")
        self.cache_root = Path(root) if root else None
        self.timeout = float(timeout)
        self._projects: dict[str, str] = {}

    def _read(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "VisualToolkit"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"HTTP {status} for {url}")
            return response.read(64 * 1024 * 1024)

    def getRawNeuronTreeByID(self, sample_id: str, neuron_id: str):
        if not self.host or not self.raw_base:
            return None
        sample = str(sample_id)
        if not sample or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                             for c in sample):
            raise ValueError("sample_id must be a simple identifier")
        name = str(neuron_id)
        if Path(name).name != name or name in {".", ".."}:
            raise ValueError("neuron_id must be a filename, not a path")
        if not name.lower().endswith(".swc"):
            name += ".swc"
        cache = (self.cache_root / sample / name) if self.cache_root else None
        if cache and cache.is_file():
            return read_swc(cache)
        project = self._projects.get(sample)
        if project is None:
            query = urllib.parse.urlencode({"project_id": "", "fMOST_id": sample})
            info_url = f"{self.host}/neuronbrowser/api/user/getSampleInfo?{query}"
            info = json.loads(self._read(info_url).decode("utf-8"))
            project = str((info or [{}])[0].get("project_id") or "")
            self._projects[sample] = project
        if not project:
            raise RuntimeError(
                f"Portal metadata for {sample} did not declare a project_id")
        raw_url = (f"{self.raw_base}/{urllib.parse.quote(project)}/{sample}/swc_raw/"
                   f"{urllib.parse.quote(name)}")
        text = self._read(raw_url).decode("utf-8", "replace")
        if not text.strip():
            raise RuntimeError(f"Portal returned an empty SWC for {sample}/{name}")
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_name(cache.name + ".part")
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, cache)
            return read_swc(cache)
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".swc", delete=False, encoding="utf-8")
        try:
            handle.write(text)
            handle.close()
            return read_swc(handle.name)
        finally:
            try:
                os.remove(handle.name)
            except OSError:
                pass


class IONData:
    """Compatibility-shaped provider; local SWC is default, adapters are explicit."""
    def __init__(self, *args, **kwargs):
        self._local = LocalSWCProvider()
        self._provider_args = args
        self._provider_kwargs = kwargs
        self._provider = None
        self._provider_checked = False
        self._portal = None

    def getRawNeuronTreeByID(self, sample_id: str, neuron_id: str):
        tree = self._local.getRawNeuronTreeByID(sample_id, neuron_id)
        if tree is not None:
            return tree
        if not self._provider_checked:
            self._provider = _provider_factory(*self._provider_args, **self._provider_kwargs) if _provider_factory else None
            self._provider_checked = True
        if self._provider is None:
            if self._portal is None:
                self._portal = PortalSWCProvider()
            return self._portal.getRawNeuronTreeByID(sample_id, neuron_id)
        return self._provider.getRawNeuronTreeByID(sample_id, neuron_id)


# Read-only workbook/resource planning. No ReMAP code is imported or executed.
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_WORKBOOK_NAME = re.compile(r"^(?P<sample>[A-Za-z0-9_-]+)_results(?:_[0-9]{8}_[0-9]{6})?\.xlsx$", re.I)


def _file_record(path: Path, *, inspect: bool = False, frame=None, units=None,
                 acquisition_date=None, processing_date=None, source_date=None) -> dict:
    record = {"path": str(path.resolve()), "exists": path.is_file(),
              "frame": frame or "unknown", "units": units or "unknown",
              "acquisition_date": acquisition_date or "unknown",
              "processing_date": processing_date or "unknown", "source_date": source_date or "unknown",
              "sha256": None, "size": None, "mtime_ns": None}
    if record["exists"]:
        before = path.stat()
        record.update(size=before.st_size, mtime_ns=before.st_mtime_ns)
        if inspect:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f"source changed during checksum: {path}")
            record["sha256"] = digest.hexdigest()
    return record


def locate_sample_table(sample_id: str, config: dict, *, selected: str | Path | None = None,
                        inspect: bool = False) -> dict:
    """Select exactly one declared workbook; multiple candidates require a choice."""
    _validate_sample_id(sample_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id):
        raise ValueError("sample_id must be a simple folder identifier")
    source = (config.get("sources") or {}).get("neuron_tables") or {}
    root_value = source.get("root")
    plan = {"sample_id": sample_id, "root": str(root_value) if root_value else None,
            "layout": source.get("layout", "per_sample"), "status": "not_configured",
            "candidates": [], "selected": None, "source": None}
    if not root_value:
        return plan
    if plan["layout"] != "per_sample":
        raise ValueError("only neuron_tables.layout='per_sample' is supported")
    folder = Path(root_value).expanduser().resolve() / sample_id
    if not folder.is_dir():
        plan["status"] = "missing"
        return plan
    candidates = sorted(p for p in folder.iterdir() if p.is_file() and
                        (match := _WORKBOOK_NAME.fullmatch(p.name)) and match.group("sample") == sample_id)
    plan["candidates"] = [str(p) for p in candidates]
    mapping = source.get("selected_workbooks") or {}
    declared = selected if selected is not None else mapping.get(sample_id)
    if declared is not None:
        choice = Path(declared)
        choice = choice if choice.is_absolute() else folder / choice
        if choice.resolve() not in {p.resolve() for p in candidates}:
            raise ValueError(f"selected workbook is not an exact candidate for {sample_id}: {declared}")
    elif len(candidates) == 1:
        choice = candidates[0]
    elif len(candidates) > 1:
        plan["status"] = "ambiguous"
        return plan
    else:
        plan["status"] = "missing"
        return plan
    plan.update(status="resolved", selected=str(choice.resolve()),
                source=_file_record(choice, inspect=inspect,
                                    frame=source.get("frame"), units=source.get("units")))
    return plan


def _workbook_rows(path: Path, sheet: str = "Summary") -> list[dict[str, str]]:
    """Read a bounded xlsx sheet as text, retaining stored string identifiers."""
    with zipfile.ZipFile(path) as book:
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        matches = [s for s in workbook.findall("m:sheets/m:sheet", _NS) if s.get("name") == sheet]
        if len(matches) != 1:
            raise ValueError(f"{path}: expected one {sheet} sheet")
        rel_id = matches[0].get("{" + _NS["r"] + "}id")
        rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next((r.get("Target") for r in rels if r.get("Id") == rel_id), None)
        if not target:
            raise ValueError(f"{path}: sheet relationship is missing")
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in Path(member).parts:
            raise ValueError("unsafe workbook member path")
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            strings = ET.fromstring(book.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter("{" + _NS["m"] + "}t")) for si in strings]
        xml = ET.fromstring(book.read(member))
        rows = []
        for row in xml.findall("m:sheetData/m:row", _NS):
            cells = {}
            for cell in row.findall("m:c", _NS):
                ref = cell.get("r", "")
                column = re.match(r"[A-Z]+", ref)
                if not column:
                    continue
                value = cell.find("m:v", _NS)
                if cell.get("t") == "inlineStr":
                    content = "".join(t.text or "" for t in cell.iter("{" + _NS["m"] + "}t"))
                elif value is None:
                    content = ""
                elif cell.get("t") == "s":
                    content = shared[int(value.text)]
                else:
                    content = value.text or ""
                cells[column.group()] = content
            rows.append(cells)
            if len(rows) > 100000:
                raise ValueError("Summary sheet exceeds 100000 rows")
    if not rows:
        raise ValueError("Summary sheet is empty")
    columns = rows[0]
    if len(set(columns.values())) != len(columns):
        raise ValueError("Summary sheet has duplicate headers")
    return [{name: row.get(letter, "") for letter, name in columns.items()} for row in rows[1:]]


def load_summary_neuron(sample_id: str, neuron_id: str, config: dict, *,
                        selected: str | Path | None = None, inspect: bool = False) -> dict:
    """Find one exact SampleID/NeuronID row without numeric ID coercion."""
    _validate_sample_id(sample_id)
    _safe_neuron_id(neuron_id, "Summary", sample_id)
    plan = locate_sample_table(sample_id, config, selected=selected, inspect=inspect)
    if plan["status"] != "resolved":
        raise ValueError(f"neuron table is {plan['status']}; select one workbook explicitly")
    rows = _workbook_rows(Path(plan["selected"]))
    if not rows or not {"SampleID", "NeuronID"}.issubset(rows[0]):
        raise ValueError("Summary requires SampleID and NeuronID columns")
    matching = []
    seen = set()
    for row in rows:
        identity = (row["SampleID"], row["NeuronID"])
        if identity in seen:
            raise ValueError(f"duplicate Summary identity {identity!r}")
        seen.add(identity)
        if row["SampleID"] == sample_id and row["NeuronID"] == neuron_id:
            matching.append(row)
        elif row["NeuronID"] == neuron_id and row["SampleID"] != sample_id:
            raise ValueError(f"Summary neuron {neuron_id!r} has mismatched SampleID")
    if len(matching) != 1:
        raise ValueError(f"no exact Summary row for {sample_id!r}/{neuron_id!r}")
    return {"sample_id": sample_id, "neuron_id": neuron_id, "row": matching[0], "workbook": plan}


def plan_neuron_resources(sample_id: str, neuron_id: str, config: dict, *,
                          selected_workbook: str | Path | None = None,
                          inspect: bool = False) -> dict:
    """Plan declared resources without loading volumes, fetching data, or transforming SWCs."""
    _validate_sample_id(sample_id)
    _safe_neuron_id(neuron_id, "resource plan", sample_id)
    sample = (config.get("samples") or {}).get(sample_id) or {}
    sources = config.get("sources") or {}
    name = neuron_id if neuron_id.lower().endswith(".swc") else neuron_id + ".swc"
    brain = sources.get("brain_view") or {}
    atlas = sources.get("atlas") or {}
    if isinstance(atlas, (str, Path)):
        atlas = {"path": atlas}
    raw_root = sources.get("legacy_raw_swc_root")
    brain_frame = brain.get("coordinate_frame")
    brain_units = brain.get("coordinate_units")
    plan = {"sample_id": sample_id, "neuron_id": neuron_id, "resources": {},
            "coordinate_relation": "unknown", "transform": None}
    for label, path, metadata in (
        ("raw_swc", Path(raw_root) / sample_id / name if raw_root else None,
         {"frame": sources.get("raw_swc_coordinate_frame"), "units": sources.get("raw_swc_coordinate_units"),
          "source_date": sources.get("raw_swc_source_date")}),
        ("processed_swc", Path(brain["processed_swc_root"]) / sample_id / name
         if brain.get("processed_swc_root") else None,
         {"frame": brain_frame, "units": brain_units, "processing_date": brain.get("processing_date"),
          "source_date": brain.get("source_date")}),
        ("mesh", brain.get("mesh_path"),
         {"frame": brain_frame, "units": brain_units, "processing_date": brain.get("processing_date"),
          "source_date": brain.get("source_date")}),
        ("ds00_processed", sample.get("ds00_processed"),
         {"frame": sample.get("ds00_coordinate_frame"), "units": sample.get("ds00_coordinate_units"),
          "acquisition_date": sample.get("ds00_acquisition_date"),
          "processing_date": sample.get("ds00_processing_date")}),
        ("resample_5um", sample.get("resample_5um"),
         {"frame": sample.get("resample_5um_coordinate_frame"), "units": sample.get("resample_5um_coordinate_units"),
          "acquisition_date": sample.get("resample_5um_acquisition_date"),
          "processing_date": sample.get("resample_5um_processing_date")}),
        ("atlas", atlas.get("path"),
         {"frame": atlas.get("coordinate_frame"), "units": atlas.get("coordinate_units"),
          "acquisition_date": atlas.get("acquisition_date"), "processing_date": atlas.get("processing_date")}),
    ):
        plan["resources"][label] = _file_record(Path(path), inspect=inspect, **metadata) if path else None
    plan["workbook"] = locate_sample_table(sample_id, config, selected=selected_workbook, inspect=inspect)
    return plan


def load_raw_neuron(config: dict, sample_id: str, neuron_id: str, *,
                    allow_download: bool = False) -> SWCTree:
    """Load a declared native raw SWC; portal retrieval requires explicit opt-in."""
    _validate_sample_id(sample_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id):
        raise ValueError("sample_id must be a simple folder identifier")
    _safe_neuron_id(neuron_id, "raw SWC", sample_id)
    name = neuron_id if neuron_id.lower().endswith(".swc") else neuron_id + ".swc"
    sources = config.get("sources") or {}
    raw_root = sources.get("legacy_raw_swc_root")
    path = None
    if raw_root:
        path = resolve_declared_raw_swc(raw_root, sample_id, name)
        if path.is_file():
            return read_swc(path)
    if not allow_download:
        raise FileNotFoundError(f"native raw SWC is not cached for {sample_id}/{name}")
    if not raw_root:
        raise ValueError("portal download requires sources.legacy_raw_swc_root")
    portal = PortalSWCProvider(config)
    tree = portal.getRawNeuronTreeByID(sample_id, name)
    if tree is None:
        raise FileNotFoundError(f"portal raw SWC source is not configured for {sample_id}/{name}")
    if path is None or not path.is_file():
        raise RuntimeError("portal did not cache native raw SWC at its declared path")
    return read_swc(path)


def resolve_declared_raw_swc(raw_root: str | Path, sample_id: str, name: str) -> Path:
    """Resolve one declared raw SWC, allowing a verified Windows MSIX root alias."""
    _validate_sample_id(sample_id)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sample_id):
        raise ValueError("sample_id must be a simple folder identifier")
    _safe_neuron_id(name, "raw SWC", sample_id)
    root = Path(raw_root).expanduser().resolve()
    path = (root / sample_id / name).resolve()
    if path.is_relative_to(root):
        return path
    # Windows MSIX may resolve a child through LocalCache although resolving
    # the root alone retains AppData. Only accept the alternate spelling when
    # its existing root is the very same filesystem directory.
    if path.name == name and path.parent.name == sample_id:
        try:
            if path.parent.parent.samefile(root):
                return path
        except OSError:
            pass
    raise ValueError("native raw SWC path escapes declared raw root")


def _manifest_selection(sample_id: str, manifest_path: str | Path,
                        ds00_root: str | Path, expected_path: str | Path | None):
    """Select one declared DS00 path using manifest bytes stable during the read."""
    _validate_sample_id(sample_id)
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest_before = manifest_file.stat()
    manifest_bytes = manifest_file.read_bytes()
    manifest_after = manifest_file.stat()
    if (manifest_before.st_size, manifest_before.st_mtime_ns) != (manifest_after.st_size, manifest_after.st_mtime_ns):
        raise RuntimeError("dataset manifest changed while being read")
    manifest = json.loads(manifest_bytes)
    rows = [r for r in manifest.get("selected_preprocessed_outputs", [])
            if isinstance(r, dict) and str(r.get("sample")) == sample_id]
    if len(rows) != 1:
        raise ValueError(f"Live dataset manifest does not uniquely select a processed DS00 for {sample_id}")
    row = rows[0]
    relative = row.get("relative_path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("manifest selected relative_path must remain inside ds00_root")
    relative = relative.replace("\\", "/")
    root = Path(ds00_root).expanduser().resolve()
    source_path = (root / relative).resolve()
    if not source_path.is_relative_to(root):
        raise ValueError("manifest selected source escapes ds00_root")
    if expected_path is not None:
        expected = Path(expected_path)
        expected = (root / expected) if not expected.is_absolute() else expected
        if expected.resolve() != source_path:
            raise ValueError("configured DS00 path differs from manifest selection")
    return manifest_file, manifest_bytes, manifest, row, relative, source_path


def plan_manifest_selected_ds00(sample_id: str, manifest_path: str | Path,
                                ds00_root: str | Path, *,
                                expected_path: str | Path | None = None,
                                inspect: bool = False) -> dict:
    """Read-only selection; default checks metadata, inspect verifies image checksum."""
    if inspect:
        return resolve_manifest_selected_ds00(sample_id, manifest_path, ds00_root,
                                              expected_path=expected_path)
    manifest_file, manifest_bytes, manifest, row, relative, source_path = _manifest_selection(
        sample_id, manifest_path, ds00_root, expected_path)
    record = _file_record(source_path, frame=row.get("space"), units=row.get("units"))
    if not record["exists"]:
        raise FileNotFoundError(f"Live manifest-selected preprocessed DS volume is unavailable: {source_path}")
    expected_hash = row.get("sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
        raise ValueError("manifest selected DS00 checksum declaration is missing or invalid")
    return {"sample_id": sample_id, "relative_path": relative, "source": record,
            "manifest_path": str(manifest_file),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "manifest_run_id": manifest.get("run_id"), "manifest_time": manifest.get("time"),
            "declared_sha256": expected_hash.lower(), "checksum_verified": False}


def resolve_manifest_selected_ds00(sample_id: str, manifest_path: str | Path,
                                   ds00_root: str | Path, *,
                                   expected_path: str | Path | None = None,
                                   expected_relative_path: str | None = None) -> dict:
    """Verify one manifest-selected processed DS00 source and its stable checksum."""
    if expected_relative_path is not None:
        if expected_path is not None:
            raise ValueError("provide one expected DS00 path")
        expected_path = expected_relative_path
    manifest_file, manifest_bytes, manifest, row, relative, source_path = _manifest_selection(
        sample_id, manifest_path, ds00_root, expected_path)
    record = _file_record(source_path, inspect=True, frame=row.get("space"), units=row.get("units"))
    if not record["exists"]:
        raise FileNotFoundError(source_path)
    expected_hash = row.get("sha256")
    if not isinstance(expected_hash, str) or record["sha256"] != expected_hash.lower():
        raise RuntimeError("Selected preprocessed DS SHA256 differs from the live manifest")
    return {"sample_id": sample_id, "relative_path": relative, "source": record,
            "manifest_path": str(manifest_file),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "manifest_run_id": manifest.get("run_id"), "manifest_time": manifest.get("time"),
            "repository_candidate_path": row.get("repository_candidate_path"),
            "processed_at": row.get("processed_at"),
            "source_historical_path": row.get("source_historical_path"),
            "source_sha256": row.get("source_sha256"),
            "processing_parameters": row.get("processing_parameters"),
            "software_versions": row.get("software_versions"),
            "declared_space": row.get("space"),
            "scientific_status": row.get("status"), "source_acquisition_date": "unknown"}


def processed_ds00_record(sample_id: str, manifest_path: str | Path,
                          ds00_root: str | Path,
                          expected_geometry: dict | None = None) -> dict:
    """Return the historical flat processed-DS00 receipt from one verified source."""
    selected = resolve_manifest_selected_ds00(sample_id, manifest_path, ds00_root)
    source = selected["source"]
    result = {
        "path": source["path"], "server_path": source["path"],
        "repository_candidate_path": selected["repository_candidate_path"],
        "relative_path": selected["relative_path"], "sha256": source["sha256"],
        "bytes": source["size"], "mtime_ns_before_after_equal": True,
        "server_file_present": True, "manifest_path": selected["manifest_path"],
        "manifest_sha256": selected["manifest_sha256"],
        "manifest_run_id": selected["manifest_run_id"], "manifest_time": selected["manifest_time"],
        "processed_at": selected["processed_at"],
        "source_historical_path": selected["source_historical_path"],
        "source_sha256": selected["source_sha256"],
        "processing_parameters": selected["processing_parameters"],
        "software_versions": selected["software_versions"],
        "declared_space": selected["declared_space"],
        "scientific_status": selected["scientific_status"],
        "source_acquisition_date": selected["source_acquisition_date"],
    }
    if expected_geometry is not None:
        result["expected_geometry"] = expected_geometry
    return result
