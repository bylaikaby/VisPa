"""Candidate axon-endpoint table from declared SWC frames.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../../CHANGELOG.md
Status: candidate

A row is one non-root SWC type-2 node with no children in the full graph.
These are reconstruction ends, not boutons or synapses. The table does not
inspect image support or assign scientific acceptance.

Two declared frames are kept apart. The raw SWC is assumed to use native
fMOST micrometres. ARM names use the processed SWC, assumed to use NMT
template micrometres, read at the same node id. Pairing does not validate
registration, orientation or anatomy.
Raw micrometres divided by 250 are not an NMT voxel.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import random
from pathlib import Path

from .sources import SWCTree, read_swc

SCHEMA = "vispa.terminal_qc.v2"
AXON_TYPE = 2
ATLAS_SCALE_UM = 250.0
REGION_LEVELS = (3, 6)


@dataclass(frozen=True)
class TerminalRow:
    node_id: int
    x: float
    y: float
    z: float
    radius: float
    parent_id: int
    node_type: int
    role: str

    def xyz(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def list_terminal_rows(tree: SWCTree) -> list[TerminalRow]:
    """Return the render table: non-root type-2 leaves, in node-id order."""
    children: dict[int, list[int]] = {node.id: [] for node in tree.points}
    by_id = {node.id: node for node in tree.points}
    for node in tree.points:
        if node.parent_id != -1:
            children[node.parent_id].append(node.id)
    rows = []
    for node_id in sorted(by_id):
        node = by_id[node_id]
        if children[node_id]:
            continue
        if node.parent_id == -1 or node.type != AXON_TYPE:
            continue
        rows.append(TerminalRow(
            node.id, node.x, node.y, node.z, node.radius, node.parent_id, node.type, "leaf"))
    return rows


def leaf_census(tree: SWCTree) -> dict:
    """Count every childless node and the type-2 subset used for rendering."""
    children: dict[int, int] = {node.id: 0 for node in tree.points}
    for node in tree.points:
        if node.parent_id != -1:
            children[node.parent_id] += 1
    leaves = [node for node in tree.points if children[node.id] == 0]
    type2 = [node for node in leaves if node.parent_id != -1 and node.type == AXON_TYPE]
    return {
        "nodes": len(tree.points),
        "all_leaves": len(leaves),
        "candidate_axon_endpoints": len(type2),
    }


def select_rows(rows: list[TerminalRow], node_ids: list[int] | None = None,
                *, n: int | None = None, seed: int | None = None) -> list[TerminalRow]:
    """Choose table rows by id, or a seeded random subset. Order follows the table."""
    by_id = {row.node_id: row for row in rows}
    if node_ids is not None:
        missing = [node_id for node_id in node_ids if node_id not in by_id]
        if missing:
            raise ValueError(f"node id is not a type-2 terminal row: {missing[0]}")
        chosen = set(node_ids)
        return [row for row in rows if row.node_id in chosen]
    if n is None:
        raise ValueError("select rows by node id or by random n")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("random n must be a positive integer")
    if seed is None:
        raise ValueError("random n requires an explicit seed")
    if n > len(rows):
        raise ValueError(f"random n {n} exceeds {len(rows)} terminal rows")
    picked = set(random.Random(seed).sample([row.node_id for row in rows], n))
    return [row for row in rows if row.node_id in picked]


@dataclass(frozen=True)
class TerminalBranch:
    """The unbranched run from one leaf back to its branch point (raw frame)."""
    leaf_id: int
    branch_start_id: int
    axon_stop_id: int
    node_ids: tuple[int, ...]
    length_um: float
    chord_um: float
    tortuosity: float | None
    terminal_edge_um: float
    path_to_soma_um: float
    branch_order: int
    compartment_transitions: int
    zero_length_edges: int
    coincident_leaf_count: int
    z_span_um: float
    sections_crossed: int


class SwcGraph:
    """Child lists and parent links for one SWC, built once per tree."""

    def __init__(self, tree: SWCTree):
        self.tree = tree
        self.nodes = {node.id: node for node in tree.points}
        self.children: dict[int, list[int]] = {node_id: [] for node_id in self.nodes}
        for node in tree.points:
            if node.parent_id != -1:
                self.children[node.parent_id].append(node.id)
        self.root_id = tree.root.id
        self._order: dict[int, int] = {}
        self._path: dict[int, float] = {}
        leaves = [node_id for node_id, kids in self.children.items() if not kids]
        self.leaf_positions = {}
        for node_id in leaves:
            key = tuple(round(value, 6) for value in self.nodes[node_id].xyz)
            self.leaf_positions[key] = self.leaf_positions.get(key, 0) + 1

    def edge_um(self, node_id: int) -> float:
        node = self.nodes[node_id]
        if node.parent_id == -1:
            return 0.0
        return math.dist(node.xyz, self.nodes[node.parent_id].xyz)

    def path_to_root_um(self, node_id: int) -> float:
        if node_id in self._path:
            return self._path[node_id]
        chain = []
        current = node_id
        while current not in self._path and self.nodes[current].parent_id != -1:
            chain.append(current)
            current = self.nodes[current].parent_id
        base = self._path.get(current, 0.0)
        for item in reversed(chain):
            base += self.edge_um(item)
            self._path[item] = base
        self._path.setdefault(node_id, base)
        return self._path[node_id]

    def branch_order(self, node_id: int) -> int:
        """Full-graph branch points on the path to root; not NeuroM axon order."""
        order = 0
        current = self.nodes[node_id].parent_id
        while current != -1:
            if len(self.children[current]) > 1:
                order += 1
            current = self.nodes[current].parent_id
        return order


def terminal_branch(graph: SwcGraph, leaf_id: int, section_um: float = 3.0) -> TerminalBranch:
    """Walk upstream from a leaf while each node has exactly one child.

    The walk stops at the first node whose child count is not one, or at the
    root, and includes that node, as Projectome ``terminal_site_summary`` does.
    ``axon_stop_id`` is where a non-axon parent ends the same walk earlier.
    """
    if not math.isfinite(section_um) or section_um <= 0:
        raise ValueError("section_um must be positive and finite")
    nodes, children = graph.nodes, graph.children
    if children[leaf_id]:
        raise ValueError(f"node {leaf_id} has children; it is not a leaf")
    ids = [leaf_id]
    length = 0.0
    transitions = zero_edges = 0
    axon_stop = None
    current = leaf_id
    while nodes[current].parent_id != -1:
        parent = nodes[current].parent_id
        edge = graph.edge_um(current)
        length += edge
        zero_edges += int(edge == 0.0)
        if nodes[parent].type != nodes[current].type:
            transitions += 1
            if axon_stop is None and nodes[current].type == AXON_TYPE:
                axon_stop = parent
        ids.append(parent)
        current = parent
        if current == graph.root_id or len(children[current]) != 1:
            break
    start = ids[-1]
    leaf_xyz = nodes[leaf_id].xyz
    chord = math.dist(leaf_xyz, nodes[start].xyz)
    zs = [nodes[node_id].z for node_id in ids]
    z_span = max(zs) - min(zs)
    key = tuple(round(value, 6) for value in leaf_xyz)
    return TerminalBranch(
        leaf_id=leaf_id,
        branch_start_id=start,
        axon_stop_id=start if axon_stop is None else axon_stop,
        node_ids=tuple(ids),
        length_um=round(length, 3),
        chord_um=round(chord, 3),
        tortuosity=None if chord == 0.0 else round(length / chord, 4),
        terminal_edge_um=round(graph.edge_um(leaf_id), 3),
        path_to_soma_um=round(graph.path_to_root_um(leaf_id), 3),
        branch_order=graph.branch_order(leaf_id),
        compartment_transitions=transitions,
        zero_length_edges=zero_edges,
        coincident_leaf_count=graph.leaf_positions.get(key, 1),
        z_span_um=round(z_span, 3),
        sections_crossed=int(math.floor(max(zs) / section_um) - math.floor(min(zs) / section_um)),
    )


def all_leaf_ids(tree: SWCTree) -> list[int]:
    """Every childless node of any type, root excluded. Step1 uses this set."""
    graph = SwcGraph(tree)
    return [node_id for node_id, kids in graph.children.items()
            if not kids and node_id != graph.root_id]


def pair_processed(raw: SWCTree, processed: SWCTree) -> dict[int, tuple[float, float, float]]:
    """Map each raw node id to its processed-frame XYZ.

    The two files must describe the same graph: equal node ids, types and
    parents. Coordinates may differ between declared frames. Node ID bridges
    structurally matching graphs; this does not validate registration or anatomy.
    """
    raw_nodes = {node.id: node for node in raw.points}
    processed_nodes = {node.id: node for node in processed.points}
    if raw_nodes.keys() != processed_nodes.keys():
        missing = sorted(raw_nodes.keys() ^ processed_nodes.keys())[:5]
        raise ValueError(f"raw and processed SWC node ids differ, e.g. {missing}")
    for node_id, node in raw_nodes.items():
        other = processed_nodes[node_id]
        if node.type != other.type or node.parent_id != other.parent_id:
            raise ValueError(
                f"raw and processed SWC differ at node {node_id}: "
                f"type {node.type}/{other.type}, parent {node.parent_id}/{other.parent_id}")
    return {node_id: node.xyz for node_id, node in processed_nodes.items()}


@dataclass
class HierarchyAtlas:
    """One 5-D NMT hierarchy volume (x, y, z, 1, level) and its key."""
    image: object
    table: dict
    path: str
    key_path: str
    provenance: dict | None = None

    def plane(self, level: int):
        image = self.image
        if image.ndim == 5 and image.shape[3] == 1 and 1 <= level <= image.shape[4]:
            return image[:, :, :, 0, level - 1]
        if image.ndim == 4 and 1 <= level <= image.shape[-1]:
            return image[..., level - 1]
        if image.ndim == 3 and level == 6:
            return image
        return None


def load_atlas(atlas_path, key_path) -> HierarchyAtlas:
    """Read the hierarchy volume and its ``Index Abbreviation Full_Name`` key."""
    import numpy as np
    path = str(atlas_path)
    if path.endswith(".npy"):
        image = np.load(path)
    else:
        import nibabel as nib
        image = np.asanyarray(nib.load(path).dataobj)
    table = {}
    for line in Path(key_path).read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        table[int(parts[0])] = {"abbreviation": parts[1], "full_name": parts[2]}
    return HierarchyAtlas(image, table, path, str(key_path), {
        "atlas": _input_record(path), "atlas_key": _input_record(key_path)})


def atlas_names(xyz, atlas: HierarchyAtlas, levels=REGION_LEVELS,
                scale_um: float = ATLAS_SCALE_UM) -> dict:
    """Region names at one processed-frame point.

    The voxel is ``np.round(xyz / scale_um)``, the half-to-even rounding that
    region analysis uses before it indexes the atlas. A point outside the
    grid is ``Out_of_Bounds``; label 0 is ``background``.
    """
    import numpy as np
    if not math.isfinite(scale_um) or scale_um <= 0:
        raise ValueError("scale_um must be positive and finite")
    if len(xyz) != 3 or not all(math.isfinite(float(value)) for value in xyz):
        raise ValueError("xyz must contain three finite coordinates")
    voxel = np.round(np.asarray(list(xyz), dtype=float) / float(scale_um)).astype(int)
    names = {}
    for level in levels:
        entry = {"id": None, "abbreviation": "Out_of_Bounds", "full_name": "Out_of_Bounds"}
        plane = atlas.plane(int(level))
        if plane is None:
            entry.update(abbreviation="unresolved", full_name="unresolved")
        elif all(0 <= int(voxel[axis]) < plane.shape[axis] for axis in range(3)):
            code = int(plane[tuple(int(value) for value in voxel)])
            entry["id"] = code
            if code == 0:
                entry.update(abbreviation="background", full_name="background")
            else:
                entry.update(atlas.table.get(
                    code, {"abbreviation": f"Unknown_{code}", "full_name": f"Unknown_{code}"}))
        names[int(level)] = entry
    return {
        "voxel": [int(value) for value in voxel],
        "names": names,
        "scale_um": float(scale_um),
        "atlas": atlas.path,
    }


def charm_names(xyz, atlas_path, key_path, levels=REGION_LEVELS,
                scale_um: float = ATLAS_SCALE_UM) -> dict:
    """Load one atlas and name one processed-frame point. Prefer ``atlas_names``."""
    return atlas_names(xyz, load_atlas(atlas_path, key_path), levels, scale_um)


def region_line(lookup: dict) -> str:
    """One title fragment: ``L3 name | L6 name``."""
    parts = []
    for level in sorted(lookup.get("names") or {}):
        item = lookup["names"][level]
        parts.append(f"L{level} {item.get('abbreviation') or 'unresolved'}")
    return " | ".join(parts)


def _tree(value) -> SWCTree:
    return value if isinstance(value, SWCTree) else read_swc(value)


def _input_record(value) -> dict | None:
    if value is None:
        return None
    if isinstance(value, SWCTree):
        return {"kind": "in_memory_tree", "source_sha256": None,
                "provenance_status": "source_identity_unknown"}
    path = Path(value)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"input changed while hashing: {path}")
    return {"kind": "file", "path": str(path), "sha256": digest.hexdigest(),
            "size_bytes": after.st_size, "mtime_ns": after.st_mtime_ns,
            "provenance_status": "source_hash_recorded"}


def terminal_table(raw_path, processed_path=None, atlas: HierarchyAtlas | None = None,
                   levels=REGION_LEVELS) -> dict:
    """Rows with raw image coordinates and, when given, processed-frame ARM names.

    ``raw_path`` and ``processed_path`` accept a file path or an ``SWCTree``,
    such as the one ``IONData().getRawNeuronTreeByID`` returns.
    """
    raw = _tree(raw_path)
    rows = list_terminal_rows(raw)
    processed_xyz = None
    if processed_path is not None:
        processed_xyz = pair_processed(raw, _tree(processed_path))
    soma = raw.root.xyz
    graph = SwcGraph(raw)
    records = []
    for row in rows:
        branch = terminal_branch(graph, row.node_id)
        record = {
            **asdict(row),
            "raw_xyz_um": list(row.xyz()),
            "soma_distance_um": round(math.dist(row.xyz(), soma), 3),
            "branch": {**asdict(branch), "node_ids": list(branch.node_ids)},
        }
        if processed_xyz is not None:
            record["processed_xyz_um"] = list(processed_xyz[row.node_id])
            if atlas is not None:
                record["region"] = atlas_names(processed_xyz[row.node_id], atlas, levels)
        records.append(record)
    soma_region = None
    if processed_xyz is not None and atlas is not None:
        soma_region = atlas_names(processed_xyz[raw.root.id], atlas, levels)
    return {
        "schema": SCHEMA,
        "swc": "SWCTree" if isinstance(raw_path, SWCTree) else str(raw_path),
        "processed_swc": (None if processed_path is None else
                          "SWCTree" if isinstance(processed_path, SWCTree) else str(processed_path)),
        "atlas": None if atlas is None else {"path": atlas.path, "key": atlas.key_path},
        "input_provenance": {
            "raw_swc": _input_record(raw_path),
            "processed_swc": _input_record(processed_path),
            "atlas": None if atlas is None else (atlas.provenance or {}).get("atlas", {
                "kind": "in_memory_atlas", "source_sha256": None,
                "provenance_status": "source_identity_unknown"}),
            "atlas_key": None if atlas is None else (atlas.provenance or {}).get("atlas_key", {
                "kind": "in_memory_atlas_key", "source_sha256": None,
                "provenance_status": "source_identity_unknown"}),
        },
        "branch_section_um": 3.0,
        "branch_section_status": "candidate raw-sampling interval; physical section assignment unvalidated",
        "frames": {
            "image": "declared raw SWC micrometres (native fMOST assumed; not validated here)",
            "region": "declared processed SWC micrometres, node id matched; voxel = round(xyz/250); registration not validated here",
        },
        "soma_raw_xyz_um": list(soma),
        "soma_region": soma_region,
        **leaf_census(raw),
        "rows": records,
    }


def table_from_swc(path) -> dict:
    """Read one raw SWC and return the candidate axon-endpoint table."""
    return terminal_table(path)
