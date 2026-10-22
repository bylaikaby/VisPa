"""Local SWC source and explicit adapter seam for source-tree providers.

Version: 1.11.0.dev1 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../CHANGELOG.md
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .dataset_config import load

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


def list_neurons(sample_id: str, config: dict | None = None) -> dict:
    """Read exact-sample neuron IDs and portal regions from an explicit CSV.

    The configured catalog describes a dated snapshot, not a live portal query.
    It is intentionally independent of selected-cohort workbooks and does not
    infer sample membership from SWC files present on disk.
    """
    if not isinstance(sample_id, str):
        raise TypeError("sample_id must be an exact string identifier")
    if not sample_id or sample_id != sample_id.strip():
        raise ValueError("sample_id must be a nonempty exact identifier")
    resolved = config if config is not None else load()
    catalog = (resolved.get("sources") or {}).get("neuron_catalog")
    if not isinstance(catalog, dict) or not catalog.get("path"):
        raise ValueError("no sources.neuron_catalog.path is configured")
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
        if (not isinstance(neuron_id, str) or not neuron_id or neuron_id != neuron_id.strip()
                or "/" in neuron_id or "\\" in neuron_id or ":" in neuron_id
                or ".." in neuron_id):
            raise ValueError(
                f"{path}:{line_number}: neuron ID must be an exact safe basename "
                f"without path separators, colon, or '..' for sample {sample_id!r}")
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
    return {"sample_id": sample_id, "monkey_id": next(iter(monkeys), ""),
            "source_path": str(path), "source_date": str(catalog.get("source_date") or "unknown"),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(), "source_size": after.st_size,
            "source_mtime_ns": after.st_mtime_ns, "count": len(rows), "rows": rows}


def catalog_snapshot_unchanged(snapshot: dict) -> bool:
    """Fast invalidation guard for a loaded list; the full SHA is captured at load."""
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
    if row.get("sample_id") != str(sample_id) or not catalog_snapshot_unchanged(snapshot):
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
