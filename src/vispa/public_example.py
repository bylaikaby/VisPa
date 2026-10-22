"""Download and render one explicitly public SWC morphology example.

Version: 1.11.0.dev2 (local/unreleased)
Last updated: 2026-10-22
Change history: ../../CHANGELOG.md
Status: candidate (public source frame and units are unspecified)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import urllib.request

from ._version import __version__

SOURCE_URL = (
    "https://mouse.digital-brain.cn/projectome/2/srv/info/monkey/pfc/"
    "neuron_download/221747_1-qroot433.swc"
)
METADATA_URL = (
    "https://mouse.digital-brain.cn/projectome/2/srv/info/monkey/pfc/"
    "macaque.neuron.info.json"
)
RECORD_ID = "1"
RECORD_FILE = "221747_1-qroot433.swc"
EXPECTED_SHA256 = "c0e4c507368d69703900b0baae3abbc49fd3003ea02b23b6ca739976f24ca1d7"
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 20
DEFAULT_DPI = 160
MIN_DPI = 100
MAX_DPI = 240


def _user_data_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "VisPa"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "VisPa"


def _renderer_code_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def default_cache_dir() -> Path:
    return _user_data_root() / "cache" / "public-neuron-example"


def default_output_dir() -> Path:
    return _user_data_root() / "output" / "public-neuron-example"


def parse_swc(payload: bytes):
    """Validate a bounded seven-column rooted SWC tree and return rows."""
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError("public SWC is empty or exceeds the 8 MiB limit")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("public SWC is not UTF-8 text") from exc
    rows = []
    ids = set()
    parent_ids = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 7:
            raise ValueError(f"SWC line {line_no} does not have seven columns")
        try:
            node_id, kind = int(fields[0]), int(fields[1])
            xyzr = tuple(float(value) for value in fields[2:6])
            parent = int(fields[6])
        except ValueError as exc:
            raise ValueError(f"SWC line {line_no} contains an invalid number") from exc
        if node_id <= 0 or kind < 0 or node_id in ids:
            raise ValueError(f"SWC line {line_no} has an invalid or duplicate node ID/type")
        if not all(math.isfinite(value) for value in xyzr) or xyzr[3] < 0:
            raise ValueError(f"SWC line {line_no} has non-finite coordinates or negative radius")
        ids.add(node_id)
        rows.append((node_id, kind, *xyzr, parent))
        parent_ids.append(parent)
    roots = [row[0] for row in rows if row[6] == -1]
    if len(roots) != 1 or not rows:
        raise ValueError("SWC must contain exactly one root (parent ID -1)")
    missing = [parent for parent in parent_ids if parent != -1 and parent not in ids]
    if missing:
        raise ValueError("SWC contains a parent ID that is absent from the file")
    parents = {row[0]: row[6] for row in rows}
    root = roots[0]
    connected = {root}
    for node_id in ids:
        trail = []
        seen = set()
        current = node_id
        while current not in connected:
            if current in seen:
                raise ValueError("SWC parent links contain a cycle")
            seen.add(current)
            trail.append(current)
            current = parents[current]
            if current == -1:
                raise ValueError("SWC contains a disconnected tree")
        connected.update(trail)
    return rows


def _read_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": f"VisPa/{__version__}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            raise ValueError("public source returned HTML instead of SWC text")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_BYTES:
            raise ValueError("public source exceeds the 8 MiB download limit")
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("public source exceeds the 8 MiB download limit")
    return payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_source(cache_dir: Path):
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / RECORD_FILE
    fetched = not cached.exists()
    if cached.exists():
        if cached.stat().st_size > MAX_BYTES:
            raise ValueError("cached public SWC exceeds the 8 MiB limit")
        payload = cached.read_bytes()
    else:
        payload = _read_url(SOURCE_URL)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("public SWC content or cache does not match the verified source checksum")
    rows = parse_swc(payload)
    if not cached.exists():
        _atomic_write(cached, payload)
    elif hashlib.sha256(cached.read_bytes()).hexdigest() != digest:
        raise ValueError("cached public SWC changed while it was being read")
    return cached, rows, digest, fetched


def _matching_existing(png: Path, receipt_path: Path, source_sha: str, dpi: int) -> bool:
    if not png.is_file() or not receipt_path.is_file():
        return False
    try:
        if png.stat().st_size > 64 * 1024 * 1024 or receipt_path.stat().st_size > 1024 * 1024:
            return False
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        rendered = receipt["render"]
        if (receipt.get("schema") != "vispa.public-neuron-example.v1"
                or receipt.get("vispa_version") != __version__
                or receipt.get("source", {}).get("url") != SOURCE_URL
                or receipt.get("source", {}).get("sha256") != source_sha
                or receipt.get("source", {}).get("coordinate_frame") != "unknown"
                or receipt.get("source", {}).get("coordinate_units") != "unknown"
                or rendered.get("dpi") != dpi
                or rendered.get("renderer_code_sha256") != _renderer_code_sha256()
                or rendered.get("views") != ["XY", "XZ", "YZ", "3D"]
                or rendered.get("full_source_extent") is not True
                or rendered.get("output") != png.name):
            return False
        png_bytes = png.read_bytes()
        digest = hashlib.sha256(png_bytes).hexdigest()
        return (digest == rendered.get("output_sha256")
                and png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _output_paths(output_dir: Path, source_sha: str, dpi: int):
    base = output_dir / "public-macaque-neuron-morphology.png"
    base_receipt = base.with_suffix(".json")
    if _matching_existing(base, base_receipt, source_sha, dpi):
        return base, base_receipt, True
    if not base.exists() and not base_receipt.exists():
        return base, base_receipt, False

    qualified = output_dir / (
        f"public-macaque-neuron-morphology-v{__version__}-dpi{dpi}-"
        f"r{_renderer_code_sha256()[:12]}.png")
    qualified_receipt = qualified.with_suffix(".json")
    if _matching_existing(qualified, qualified_receipt, source_sha, dpi):
        return qualified, qualified_receipt, True
    if not qualified.exists() and not qualified_receipt.exists():
        return qualified, qualified_receipt, False
    raise FileExistsError(
        "the current version/settings output already exists but does not match its receipt; "
        f"preserving it at {qualified}")


def _render(rows, output_dir: Path, dpi: int, source_path: Path, source_sha: str,
            png: Path, receipt_path: Path):
    import matplotlib.figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import LineCollection
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    import numpy as np

    array = np.asarray(rows, dtype=float)
    xyz = array[:, 2:5]
    root_row = array[array[:, 6] == -1][0]
    by_id = {int(row[0]): row for row in array}
    children = {}
    for row in array:
        parent = int(row[6])
        if parent != -1:
            children.setdefault(parent, []).append(row)
    segments = []
    for parent_id, child_rows in children.items():
        parent_xyz = by_id[parent_id][2:5]
        for child in child_rows:
            segments.append((parent_xyz, child[2:5]))

    output_dir.mkdir(parents=True, exist_ok=True)
    if png.exists() or receipt_path.exists():
        raise FileExistsError(f"refusing to overwrite existing example output in {output_dir}")

    fig = matplotlib.figure.Figure(figsize=(12, 9), dpi=dpi, facecolor="white")
    FigureCanvasAgg(fig)
    fig.suptitle("Public macaque neuron · morphology only\n"
                 f"{RECORD_FILE} · record {RECORD_ID} · frame and units unspecified",
                 fontsize=14, fontweight="bold")
    views = ((0, 1, "XY", "Source X", "Source Y"),
             (0, 2, "XZ", "Source X", "Source Z"),
             (1, 2, "YZ", "Source Y", "Source Z"))
    colors = {"line": "#276fbf", "root": "#d1495b"}
    for index, (a, b, name, xlabel, ylabel) in enumerate(views, 1):
        ax = fig.add_subplot(2, 2, index)
        projected = [[(start[a], start[b]), (end[a], end[b])] for start, end in segments]
        ax.add_collection(LineCollection(projected, colors=colors["line"],
                                         linewidths=0.38, alpha=0.78,
                                         label="Public SWC"))
        ax.scatter(root_row[2 + a], root_row[2 + b], s=22, color=colors["root"],
                   edgecolors="white", linewidths=0.5, zorder=4, label="SWC root")
        ax.set_title(name)
        ax.set_xlabel(f"{xlabel} (units unspecified)")
        ax.set_ylabel(f"{ylabel} (units unspecified)")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(True, color="#dce3e9", linewidth=0.45)
        if index == 1:
            ax.legend(loc="best", fontsize=8, frameon=True)
    ax3 = fig.add_subplot(2, 2, 4, projection="3d")
    ax3.add_collection3d(Line3DCollection(segments, colors=colors["line"],
                                          linewidths=0.35, alpha=0.75,
                                          label="Public SWC"))
    ax3.scatter(*root_row[2:5], color=colors["root"], s=18, label="SWC root")
    ax3.set_title("3D source geometry")
    ax3.set_xlabel("Source X", labelpad=4)
    ax3.set_ylabel("Source Y", labelpad=4)
    ax3.set_zlabel("Source Z", labelpad=4)
    ax3.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax3.yaxis.set_major_locator(MaxNLocator(nbins=4))
    ax3.zaxis.set_major_locator(MaxNLocator(nbins=4))
    ax3.set_xlim(float(xyz[:, 0].min()), float(xyz[:, 0].max()))
    ax3.set_ylim(float(xyz[:, 1].min()), float(xyz[:, 1].max()))
    ax3.set_zlim(float(xyz[:, 2].min()), float(xyz[:, 2].max()))
    ax3.legend(loc="best", fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    fd, temporary = tempfile.mkstemp(prefix=f".{png.name}.", suffix=".part", dir=output_dir)
    os.close(fd)
    try:
        fig.savefig(temporary, format="png", dpi=dpi, facecolor="white")
        png_bytes = Path(temporary).read_bytes()
        os.replace(temporary, png)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
        fig.clear()
    digest = hashlib.sha256(png_bytes).hexdigest()
    receipt = {
        "schema": "vispa.public-neuron-example.v1",
        "vispa_version": __version__,
        "purpose": "public SWC morphology preview only",
        "source": {"url": SOURCE_URL, "metadata_url": METADATA_URL,
                   "record_id": RECORD_ID, "file": RECORD_FILE,
                   "source_date": None, "source_date_status": "unknown",
                   "sha256": source_sha, "cached_path": str(source_path),
                   "coordinate_frame": "unknown", "coordinate_units": "unknown"},
        "processing": {"transforms": [], "atlas": None, "image_context": None,
                       "anatomical_acceptance": False},
        "geometry": {"node_count": int(array.shape[0]), "root_node_id": int(root_row[0]),
                     "root_position": [float(v) for v in root_row[2:5]],
                     "source_xyz_bounds": [[float(v) for v in xyz.min(axis=0)],
                                            [float(v) for v in xyz.max(axis=0)]]},
        "render": {"dpi": dpi, "views": ["XY", "XZ", "YZ", "3D"],
                   "renderer_code_sha256": _renderer_code_sha256(),
                   "full_source_extent": True, "output": png.name,
                   "output_sha256": digest},
        "limitations": ["morphology only; no soma identity, atlas, image context, or registration",
                        "source coordinate frame and units were not declared"],
    }
    _atomic_write(receipt_path, json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return png, receipt_path, digest


def run(*, output_dir=None, cache_dir=None, dpi=DEFAULT_DPI, dry_run=False):
    if isinstance(dpi, bool) or not isinstance(dpi, int) or not MIN_DPI <= dpi <= MAX_DPI:
        raise ValueError(f"dpi must be an integer from {MIN_DPI} to {MAX_DPI}")
    output = Path(output_dir).expanduser() if output_dir else default_output_dir()
    cache = Path(cache_dir).expanduser() if cache_dir else default_cache_dir()
    plan = {"source_url": SOURCE_URL, "metadata_url": METADATA_URL,
            "record_id": RECORD_ID, "file": RECORD_FILE, "cache_path": str(cache / RECORD_FILE),
            "output_png": str(output / "public-macaque-neuron-morphology.png"),
            "output_receipt": str(output / "public-macaque-neuron-morphology.json"),
            "dpi": dpi, "dpi_range": [MIN_DPI, MAX_DPI], "dry_run": bool(dry_run),
            "network_access": not dry_run, "coordinate_frame": "unknown",
            "coordinate_units": "unknown", "mode": "morphology only"}
    if dry_run:
        return {"plan": plan, "written": False}
    source_path, rows, source_sha, fetched = _load_source(cache)
    plan["network_access"] = fetched
    png, receipt_path, reused = _output_paths(output, source_sha, dpi)
    plan["output_png"] = str(png)
    plan["output_receipt"] = str(receipt_path)
    if reused:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        return {"plan": plan, "written": False, "reused": True,
                "source_sha256": source_sha,
                "output_sha256": receipt["render"]["output_sha256"],
                "png": str(png), "receipt": str(receipt_path),
                "node_count": len(rows)}
    png, receipt_path, output_sha = _render(rows, output, dpi, source_path,
                                             source_sha, png, receipt_path)
    return {"plan": plan, "written": True, "source_sha256": source_sha,
            "output_sha256": output_sha, "png": str(png), "receipt": str(receipt_path),
            "node_count": len(rows), "reused": False}
