"""
vispa_gui.py - GUI for NeuroVis Visual Toolkit

Version: 1.21.1 (local/unreleased)
Last updated: 2026-11-08
Change history: ../../CHANGELOG.md
Status: candidate (GUI layout reviewed; scientific review pending)
2026-10-30: Record effective fixed crosshair and smaller legacy square separately from legacy
profile settings in figure fingerprints and cache receipts.
2026-11-02: Pass a validated current-sample portal region to brain-view after manual identity entry.
2026-11-02: Separate neuron and purple region status, move the workflow guide to a top-bar window, and stack full-width plotting cards in their original left-panel section with source hints visible and aligned typography.
2026-11-02: Read exact-neuron FULL workbook laterality off the UI thread, guard stale identity results, and fit the preview above the full bottom action bar.
2026-11-02: Show the user-supplied VisPa artwork in the GUI title bar and taskbar from packaged image assets.
2026-11-04: Add VisPa-derived catalog laterality, autoloaded side refresh, current-monkey CSV records, shaded button borders, and split physical/NMT coordinates.
2026-11-04: Add Go to search plus an exact region selector, dark structural borders, reliable left-panel scrolling, compact plot cards, and distinct application/config version blocks.
2026-11-04: Make the complete resource-check list respond to wheel scrolling, enlarge both version blocks, show the config update date explicitly, and label the compact neuron identity as a subtitle.
2026-11-04: Make the packaged ded_vispa_config 1.0.6 profile the default while selected profiles remain writable.

DESCRIPTION:
    Tkinter review interface for standalone VisPa panels. It uses the
    configured source/provider boundary for local data, exposes a dated neuron
    catalog browser, and can launch the optional local legacy OpenGL viewer in
    its isolated worker. The GUI itself does not query the portal or import the
    legacy OpenGL stack.

KEY FEATURES:
    - Two-column layout: settings on the left, a live figure preview on the right
    - Render (F5) produces the complete panel set (Soma, Context, Sagittal and
      TrioPlot); there is no per-panel selection to tick
    - Preview: one panel at a time in the right pane
    - Saving: choose the output folder; the ticked panels and Soma NIfTI are
      written automatically, and "Browse…" / "Open output folder" sit in one block
    - Auto-Load on Startup: Uses optional configured identity and auto-load defaults
    - Auto-Fill Soma: Read soma coordinates from the configured SWC source
    - Neuron list: Browse the configured live or dated source and select an exact SWC ID
    - fnt-tracer: Open the current neuron's FNT project beside SWC Brain View interactive
    - Threaded Processing: Non-blocking panel requests with progress indicators

USAGE NOTES:
    1. Launch the GUI (package-relative imports):
        cd main_scripts
        python -m vispa.reviewer

    2. Auto-Load Feature:
        - The GUI loads a configured default neuron on startup only when enabled
        - Soma coordinates are auto-filled after ~0.5 seconds
        - Status bar shows loading progress
        - No popup on successful auto-load (silent operation)

    3. Basic Workflow:
        - Sample ID (e.g., '251637') and Neuron ID (e.g., '003.swc') are pre-filled
        - If auto-load succeeded, coordinates are already populated
    - Enter a valid Sample ID and Neuron ID to trigger soma lookup automatically
        - Adjust the Soma Plot / Context Plot settings if needed
        - Tick the panels in the Plot lane and press 'Render' (F5); tick the
          review-figure option only when you want the combined trio as well
        - The rendered figure appears in the right-hand preview pane

    4. Output Directory:
        - Default: configured VisPa GUI output folder/<sample_id>_<YYYYMMDD>
        - Use 'Browse' to select custom directory
        - Note: Changing Sample ID auto-updates path unless manually set

    5. Processing:
        - Soma: downloads the soma-centred high-resolution window and renders the MIP
        - Context: downloads the 5 µm sections and renders the MIP with SWC overlay
        - Each ticked panel renders independently: a missing source is reported for
          that panel and the others still render and preview

CONFIGURATION:
    - Window size: 1280x980 pixels, resizable; the minimum is the built layout size
    - Default identity and auto-load behaviour come from the selected config;
      without them the identity is blank and auto-load is off. The FOV boxes
      take their initial values from REVIEW_SETTINGS['context'] (8000x8000x30 µm)
      and the Soma window from REVIEW_SETTINGS['soma_window']
    - Progress bar shows during active processing
    - Status bar provides step-by-step feedback

UPDATE NOTES (v1.5.0):
    - Added auto-load feature: default neuron loads automatically on startup
    - Added auto_load_default_neuron() method for startup initialization
    - Modified load_and_autofill() with silent_success parameter for auto-load
    - Auto-load runs after 500ms delay to ensure GUI is fully rendered

UNRELEASED LOCAL CHANGE (2026-10-16):
    - Capture immutable processing requests on the UI thread and use per-job toolkit/client instances.
    - Clear auto-filled coordinates after sample/neuron edits; discard late fills for a different identity.
    - Preserve fractional raw soma coordinates and marshal worker UI updates through Tk's event queue.
    - Prevent overlapping operations and clarify grid-radius-to-cube-count behavior.

UNRELEASED LOCAL CHANGE (2026-10-17):
    - Soma actions now request a soma-centred one-cube native window
      (``get_high_res_soma_window``) so the marker sits at the panel centre; a
      missing neighbour cube falls back to the soma's own cube and is recorded.
    - New "Sagittal Context Plot" action (registered processed-DS panel) and
      "All Plots + Trio" action (Soma + Context + Sagittal plus the one-figure
      tri-plot). Labels follow the plot titles: Soma Plot / Context Plot.
    - Soma actions use the larger soma-centred window from
      ``REVIEW_SETTINGS['soma_window']`` (1.5 cubes by default), so the marker sits
      at the panel centre with context around it.
    - Context/widefield defaults are read from ``REVIEW_SETTINGS['context']``
      instead of repeating the numbers here.
    - Layout check against the legacy v1.5.0 window found the status bar clipped by
      the fixed 700x700 frame once the two review actions were added. The status
      frame is now packed first, the default window is 760x840, resizing is allowed
      and the minimum size is derived from the built layout.
    - v1.7.0 redesign after a side-by-side check with the legacy GUI: Binavi-style
      cards on a pale page with a navy header, a real "Plot" lane (Soma / Context /
      Sagittal ticks) and a "Save" lane (per-artifact PNG ticks, Soma NIfTI, output
      folder), one "Render" action and a right-hand
      figure preview that shows the newest panel or review figure.
    - GUI renders use the configured GUI output folder or the per-user
      VisPa output default; backend cache/output roots remain independent.
    - Panel failures are isolated: the Sagittal panel's missing raw-SWC source is
      reported in the status bar (and pre-warned in the Plot lane) while Soma and
      Context still render and preview. A modal appears only when nothing rendered.
    - ``plot_soma_block``/``plot_widefield_context`` now return ``output_png`` so the
      preview pane can resolve every panel type; F5 runs the selected panels.
    - The preview defaults to a single panel (Soma / Context / Sagittal tabs); the
      combined trio is an opt-in tick under the Plot lane.

UPDATE NOTES (v1.4.0):
    - Synchronized output directory logic with vispa.py
    - Added default path generation matching core toolkit behavior
    - Added 'Browse' button for custom output directory selection
    - Manual path changes persist across Sample ID updates
    - Improved import error handling with warning instead of exit
    - Thread-safe status updates and progress bar management

DEPENDENCIES:
    - vispa module (sibling import)
    - Local sources/provider interface; projectome data access is injected by the compatibility facade
    - tkinter, threading, standard library

See CHANGELOG.md for detailed version history.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import argparse
import threading
import sys
import os
import math
import re
import tempfile
import time
import hashlib
import json
import queue
import contextlib
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from importlib import resources
from ._version import __version__
from .config import _stamp

SWC_BRAIN_VIEW_LABEL = "SWC Brain View"
CATALOG_ALL_REGIONS = "All regions"
FIXED_CROSSHAIR_NOTICE = (
    "Crosshair arm length follows marker.crosshair_px in the review settings; "
    "the box follows marker.box_mode.")
SWC_BRAIN_VIEW_INTERACTIVE_LABEL = "SWC Brain View interactive"

EMPTY_PREVIEW_TEXT = ""

try:  # preview pane only; the rest of the GUI works without Pillow
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - environment without Pillow
    Image = ImageTk = None


def _apply_window_icon(root):
    """Use the packaged user artwork for Tk and the Windows title bar."""
    assets = resources.files('vispa').joinpath('assets')
    try:
        with resources.as_file(assets.joinpath('vispa.png')) as png:
            root._vispa_icon_photo = tk.PhotoImage(file=str(png))
            root.iconphoto(True, root._vispa_icon_photo)
    except (OSError, tk.TclError):
        pass  # A missing icon must not prevent review work.
    if sys.platform == 'win32':
        try:
            with resources.as_file(assets.joinpath('vispa.ico')) as ico:
                root.iconbitmap(default=str(ico))
        except (OSError, tk.TclError):
            pass


class _LogStream:
    """Redirect the toolkit's prints into the GUI process log."""

    def __init__(self, sink):
        self._sink = sink

    def write(self, text):
        for line in str(text).splitlines():
            line = line.strip()
            if line:
                self._sink.put(line)

    def flush(self):
        pass


@dataclass(frozen=True)
class ProcessingRequest:
    """Values captured on the UI thread for one immutable processing run."""
    sample_id: str
    neuron_id: str
    soma_xyz: tuple[float, float, float]
    grid_radius: int
    width_um: int
    height_um: int
    depth_um: int
    output_dir: str
    save_outputs: bool = True
    save_soma_nifti: bool = True
    soma_cubes: float = 1.5
    plot_soma: bool = True
    plot_context: bool = True
    plot_sagittal: bool = True
    save_soma_png: bool = True
    save_context_png: bool = True
    save_sagittal_png: bool = True
    save_trio_png: bool = True
    make_review_figure: bool = False
    review_session_path: str | None = None
    review_session_source: tuple[str, str, str] | None = None
    review_session_event_id: str | None = None


def make_processing_request(sample_id, neuron_id, xyz, grid_radius,
                            width_um, height_um, depth_um, output_dir,
                            save_outputs=True, save_soma_nifti=True, soma_cubes=None,
                            plot_soma=True, plot_context=True, plot_sagittal=True,
                            save_soma_png=True, save_context_png=True,
                            save_sagittal_png=True, save_trio_png=True,
                            make_review_figure=False, review_session_path=None,
                            review_session_source=None, review_session_event_id=None):
    """Parse UI values once so worker threads never follow changing widgets."""
    sample_id, neuron_id = str(sample_id).strip(), str(neuron_id).strip()
    if not sample_id or not neuron_id:
        raise ValueError("sample and neuron identity are required")
    coords = tuple(float(value) for value in xyz)
    if len(coords) != 3:
        raise ValueError("soma coordinates must contain exactly three values")
    if not all(math.isfinite(value) for value in coords):
        raise ValueError("soma coordinates must be finite")
    radius, width, height, depth = int(grid_radius), int(width_um), int(height_um), int(depth_um)
    if radius < 1 or min(width, height, depth) <= 0:
        raise ValueError("grid radius and field dimensions must be positive")
    cubes = float(REVIEW_SETTINGS['soma_window']['cubes_xy'] if soma_cubes is None else soma_cubes)
    if not math.isfinite(cubes) or cubes <= 0:
        raise ValueError("soma window size must be a positive number of cubes")
    return ProcessingRequest(
        sample_id, neuron_id, coords, radius, width, height, depth,
        str(output_dir).strip(), bool(save_outputs), bool(save_soma_nifti), cubes,
        bool(plot_soma), bool(plot_context), bool(plot_sagittal),
        bool(save_soma_png), bool(save_context_png), bool(save_sagittal_png),
        bool(save_trio_png), bool(make_review_figure),
        os.path.abspath(review_session_path) if review_session_path else None,
        tuple(review_session_source) if review_session_source else None,
        review_session_event_id,
    )


def identity_matches(request_identity, current_sample, current_neuron):
    return tuple(request_identity) == (str(current_sample).strip(), str(current_neuron).strip())


@dataclass(frozen=True)
class ReviewSessionEvent:
    path: str
    sample_id: str
    neuron_id: str
    event_id: str | None
    digest: str
    source: tuple[str, str, str]

    @property
    def identity(self):
        return self.sample_id, self.neuron_id

    @property
    def key(self):
        return self.event_id, self.digest


def normalize_review_identity(sample_id, neuron_id):
    """Validate exact reviewer IDs and normalize only the SWC extension."""
    if not isinstance(sample_id, str) or not isinstance(neuron_id, str):
        raise ValueError("sample_id and neuron_id must be strings")
    sample = sample_id
    neuron = neuron_id
    if (not sample or sample != sample.strip()
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", sample)):
        raise ValueError("sample ID must be a nonempty path-safe identifier")
    if (not neuron or neuron != neuron.strip()
            or "/" in neuron or "\\" in neuron
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", neuron)):
        raise ValueError("neuron ID must be a basename without path separators")
    if neuron.lower().endswith(".swc"):
        neuron = neuron[:-4] + ".swc"
    elif "." in neuron:
        raise ValueError("neuron ID may use only the .swc extension")
    else:
        neuron += ".swc"
    if ".." in neuron:
        raise ValueError("neuron ID cannot contain traversal components")
    return sample, neuron


def resolve_gui_launch_defaults(config=None, sample_id=None, neuron_id=None, auto_load=None):
    """Resolve explicit identity over configured defaults without importing data providers."""
    if config is None:
        from .config import load
        config = load()
    if not isinstance(config, dict):
        raise ValueError("VisPa config must be a mapping")
    if (sample_id is None) != (neuron_id is None):
        raise ValueError("sample_id and neuron_id must be provided together")
    ui = config.get("visual_toolkit", {})
    if ui is None:
        ui = {}
    if not isinstance(ui, dict):
        raise ValueError("visual_toolkit must be a mapping")
    default_sample = ui.get("default_sample", "")
    default_neuron = ui.get("default_neuron", "")
    if not isinstance(default_sample, str) or not isinstance(default_neuron, str):
        raise ValueError("configured default_sample and default_neuron must be strings")
    if bool(default_sample) != bool(default_neuron):
        raise ValueError("configured default_sample and default_neuron must both be set")
    if sample_id is not None:
        identity = normalize_review_identity(sample_id, neuron_id)
        identity_source = "explicit"
    elif default_sample and default_neuron:
        identity = normalize_review_identity(default_sample, default_neuron)
        identity_source = "configured_default"
    else:
        identity = ("", "")
        identity_source = "none"
    configured_auto_load = ui.get("auto_load", False)
    if not isinstance(configured_auto_load, bool):
        raise ValueError("configured visual_toolkit.auto_load must be a boolean")
    if auto_load is not None and not isinstance(auto_load, bool):
        raise ValueError("auto_load must be a boolean or None")
    effective_auto_load = configured_auto_load if auto_load is None else auto_load
    if not all(identity):
        effective_auto_load = False
    return identity, identity_source, effective_auto_load


def read_review_session(path):
    """Read a local identity event as data; never interpret producer fields."""
    session_path = os.path.abspath(os.fspath(path))
    with open(session_path, "rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("review session exceeds the 64 KiB size limit")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"review session is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("review session must contain a JSON object")
    if payload.get("schema") != "projectome.neuron-review.v1":
        raise ValueError("review session schema must be projectome.neuron-review.v1")
    if "sample_id" not in payload or "neuron_id" not in payload:
        raise ValueError("review session requires sample_id and neuron_id")
    sample, neuron = normalize_review_identity(payload["sample_id"], payload["neuron_id"])
    event_id = payload.get("event_id")
    if event_id is not None and (not isinstance(event_id, str) or not event_id.strip()):
        raise ValueError("review session event_id must be a nonempty string when provided")
    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("review session requires a source object")
    source_values = tuple(source.get(key) for key in ("kind", "path", "sha256"))
    if any(not isinstance(value, str) or not value.strip() for value in source_values):
        raise ValueError("review session source requires nonempty kind, path, and sha256 strings")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", source_values[2]):
        raise ValueError("review session source.sha256 must contain 64 hexadecimal characters")
    return ReviewSessionEvent(session_path, sample, neuron, event_id, digest,
                              (source_values[0], source_values[1], source_values[2].lower())), payload


def _bootstrap_config_override(argv=None):
    """Honor ``--config`` before importing toolkit modules that cache settings."""
    args = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(args):
        if value == "--config" and index + 1 < len(args):
            os.environ["VISPA_CONFIG"] = args[index + 1]
            return
        if value.startswith("--config="):
            os.environ["VISPA_CONFIG"] = value.partition("=")[2]
            return


_bootstrap_config_override()


def _resolve_output_root(config_path=None):
    try:
        from .config import default_output_root, load
        config = load(config_path)
        configured = (config.get("visual_toolkit") or {}).get("output_root")
        if configured:
            return str(configured), "dataset configuration"
        return str(default_output_root(config)), "per-user toolkit default"
    except Exception:
        local_data = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache"))
        return str(local_data / "VisPa" / "output"), "per-user VisPa fallback"


def _resolve_figure_output_root(config_path=None):
    try:
        from .config import load
        configured = (load(config_path).get("visual_toolkit") or {}).get("figure_output_root")
        if configured:
            return str(configured), "dataset configuration"
    except Exception:
        pass
    return _resolve_output_root(config_path)


def _figure_folder(root, sample_id, neuron_id):
    sample = re.sub(r'[^A-Za-z0-9_.-]', '_', str(sample_id).strip()).strip('.') or 'sample'
    neuron = re.sub(r'[^A-Za-z0-9_.-]', '_', str(neuron_id).strip().removesuffix('.swc')).strip('.') or 'neuron'
    return os.path.join(root, sample, 'neurons', neuron)

# Import the core toolkit
try:
    from .renderers.microscopy_panels import VisPa
    from .renderers.microscopy_panels import REVIEW_SETTINGS
    from .renderers.microscopy_panels import BLOCK_SIZE_PIXELS
    from .renderers.microscopy_panels import TARGET_BOX_SIDE_SCALE
    from .renderers.microscopy_panels import configure_data_sources
    from . import sources as IT
except ImportError as e:
    print(f"WARNING: Could not import required modules: {e}")

class NeuroVisGUI:
    """Complete GUI for NeuroVis Visual Toolkit."""

    # Graphite surfaces follow the reviewed classic preview. Plot action colours
    # remain semantic and are kept at their call sites below.
    COLORS = {
        'page': '#303637', 'card': '#414a4c', 'border': '#697575',
        'header': '#171d1e', 'header_text': '#c5ddca', 'header_muted': '#b7c9ba',
        'text': '#e4e4dc', 'muted': '#c5cecb', 'accent': '#168a91',
        'accent_dark': '#126b78', 'accent_soft': '#263031', 'strip': '#465052',
        'preview_bg': '#0c1213', 'field': '#202728', 'disabled': '#aab5b2',
        'border_dark': '#899e91', 'field_border': '#738183',
        'button_border': '#879092',
    }

    def __init__(self, root, sample_id=None, neuron_id=None,
                 auto_load=None, review_session=None, watch_session=False,
                 config_path=None, auto_fill_on_identity=True, test_mode=False):
        """Initialize GUI window and widgets."""
        from .config import config_version_report, load
        configuration = load(config_path)
        self.version_report = config_version_report(configuration)
        (sample_id, neuron_id), identity_source, auto_load = resolve_gui_launch_defaults(
            configuration, sample_id, neuron_id, auto_load)
        self.identity_source = identity_source
        self.root = root
        self.test_mode = bool(test_mode)
        mode_label = " · TEST OUTPUT" if self.test_mode else ""
        self.root.title(
            f"VisPa {__version__} · "
            f"{self.version_report['config_name']} {self.version_report['config_version']}"
            f"{mode_label} · local review")
        _apply_window_icon(self.root)
        # Design sizes below are quoted in 96-dpi pixels. Tk fonts follow the
        # display DPI, so the container geometry must follow the same factor or
        # a 200 % display renders text 1.75x larger than the fixed column.
        self.scale = max(1.0, float(self.root.winfo_fpixels('1i')) / 96.0)
        self.root.geometry(self._window_geometry())
        self.root.configure(bg=self.COLORS['page'])
        self._configure_graphite_ttk()
        # Resizable, with the minimum taken from the built layout below, so a future
        # extra control cannot trap the status bar outside a fixed window.
        self.root.resizable(True, True)

        # === 1. Processing Variables ===
        self.sample_id = tk.StringVar(value=sample_id)
        self.neuron_id = tk.StringVar(value=neuron_id)
        self.x_coord = tk.StringVar(value="")
        self.y_coord = tk.StringVar(value="")
        self.z_coord = tk.StringVar(value="")
        self.nmt_x = tk.StringVar(value="—")
        self.nmt_y = tk.StringVar(value="—")
        self.nmt_z = tk.StringVar(value="—")
        self.grid_radius = tk.IntVar(value=1)
        # Context/widefield defaults come from the shared review settings so the GUI
        # and the bulk runners cannot disagree.
        context = REVIEW_SETTINGS['context']
        self.width_um = tk.StringVar(value=str(context['width_um']))
        self.height_um = tk.StringVar(value=str(context['height_um']))
        self.depth_um = tk.StringVar(value=str(context['depth_um']))
        # Soma panel window in cubes; the toolkit takes the largest covered centred step.
        self.soma_cubes = tk.StringVar(
            value=f"{REVIEW_SETTINGS['soma_window']['cubes_xy']:g}")
        self.soma_source = tk.StringVar(value="")
        self.context_source = tk.StringVar(value="")
        # Plot lane: which panels to render.
        self.plot_soma = tk.BooleanVar(value=True)
        self.plot_context = tk.BooleanVar(value=True)
        self.plot_sagittal = tk.BooleanVar(value=True)
        self.force_rerender = tk.BooleanVar(value=False)
        # Save lane: which rendered artifacts are written to the output folder.
        self.save_soma_png = tk.BooleanVar(value=True)
        self.save_context_png = tk.BooleanVar(value=True)
        self.save_sagittal_png = tk.BooleanVar(value=True)
        self.save_trio_png = tk.BooleanVar(value=True)
        self.save_soma_nifti = tk.BooleanVar(value=True)
        # No per-panel selection: every run produces the full review set.
        self.make_review_figure = tk.BooleanVar(value=True)
        # Master switch kept for API compatibility; the GUI decides per artifact.
        self.save_outputs = tk.BooleanVar(value=True)
        self.status_text = tk.StringVar(value="Ready")

        # Preview pane state (populated by _register_outputs after each run).
        self.preview_files = {}
        self.preview_buttons = {}
        self.current_preview = None
        self._preview_photo = None
        self._preview_after = None
        self._ephemeral_images = {}
        self._log_queue = queue.Queue()
        self._log_stream = _LogStream(self._log_queue)
        self._startup_mode = configuration.get("visual_toolkit", {}).get(
            "startup_mode", "configured")

        # === 2. Default Output Directory Logic ===
        self.config_path = str(configuration.get("path") or config_path) if (configuration.get("path") or config_path) else None
        self.output_root = self._configured_output_root()
        self.figure_output_root = self._configured_figure_output_root()
        default_path = self._generate_default_path(self.sample_id.get())
        self.output_dir = tk.StringVar(value=default_path)

        # Flag to track if user manually changed the path
        self.manual_path_set = False

        # Add listener: Update output path when Sample ID changes (if not manually set)
        self.sample_id.trace_add("write", self._on_sample_id_change)
        self.sample_id.trace_add("write", self._on_identity_change)
        self.neuron_id.trace_add("write", self._on_identity_change)
        self.neuron_id.trace_add("write", self._on_sample_id_change)
        self.sample_id.trace_add("write", self._on_catalog_sample_change)
        self._selected_identity = (self.sample_id.get(), self.neuron_id.get())

        # Toolkit instances
        self.toolkit = None
        self.ion = None
        self._operation_running = False
        self._autofill_identity = None
        self._neuron_lookup_state = "idle"
        self._cache_status = "not checked"
        self._neuron_lookup_error = None
        self._auto_fill_on_identity = bool(auto_fill_on_identity)
        self._soma_autofill_after = None
        self.review_session_path = review_session.path if review_session else None
        self.watch_review_session = bool(watch_session)
        self._review_event_key = review_session.key if review_session else None
        self._current_review_event = review_session
        self._pending_review_event = None
        self._review_session_error = None
        self.last_data_check = None
        self._catalog_request_id = 0
        self._catalog_observed_sample_id = self.sample_id.get().strip()
        self._catalog_sample_id = None
        self._catalog_snapshot = None
        self._catalog_source = None
        self._catalog_source_var = None
        self._catalog_source_choices = {}
        self._catalog_rows_by_iid = {}
        self._catalog_side_request_id = 0
        self._catalog_side_snapshot_id = None
        self._catalog_side_result = None
        self._catalog_side_state = "idle"
        self._catalog_reload_after = None
        self._catalog_filter_after = None
        self._catalog_filter_var = tk.StringVar(value="")
        self._catalog_region_filter_var = tk.StringVar(
            value=CATALOG_ALL_REGIONS)
        self._catalog_region_selector = None
        self._catalog_sort_column = None
        self._catalog_sort_reverse = False
        self._catalog_view_side_result = None
        self._catalog_view_side_state = "idle"
        self.neuron_catalog_visible_count = tk.StringVar(value="")
        self._portal_region_cache = {}
        self._portal_region_snapshots = {}
        self._side_config = configuration
        self._neuron_side_cache = {}
        self._neuron_side_pending = set()
        self._neuron_catalog_window = None
        self.neuron_catalog_table = None
        self.neuron_catalog_load_button = None
        self.neuron_catalog_export_button = None
        self.neuron_catalog_title = tk.StringVar(value="Neuron catalog")
        self.neuron_catalog_side_summary = tk.StringVar(value="")
        self.neuron_catalog_info = tk.StringVar(value="Portal inventory has not been loaded.")

        self.build_full_gui()
        self._catalog_filter_var.trace_add(
            'write', self._schedule_neuron_catalog_filter)
        self._catalog_region_filter_var.trace_add(
            'write', self._schedule_neuron_catalog_filter)
        self.sample_id.trace_add('write', lambda *_: self._refresh_portal_region())
        self.neuron_id.trace_add('write', lambda *_: self._refresh_portal_region())
        self.sample_id.trace_add('write', lambda *_: self._refresh_neuron_side())
        self.neuron_id.trace_add('write', lambda *_: self._refresh_neuron_side())
        self._refresh_portal_region()
        self._refresh_neuron_side()

        # Start the identity lookup before the later resource-check callback so
        # the sample-section status and coordinates populate without waiting
        # for the data-check prompt to close.
        if self._auto_fill_on_identity and sample_id and neuron_id:
            self.root.after(500, self._auto_fill_current_identity)
        if self.watch_review_session:
            self.root.after(500, self._poll_review_session)

    def _configure_graphite_ttk(self):
        """Keep native ttk controls legible beside the Graphite Tk surfaces."""
        C = self.COLORS
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=C['page'], foreground=C['text'],
                        fieldbackground=C['field'], font=('Segoe UI', 9))
        style.configure('TFrame', background=C['page'])
        style.configure('TLabel', background=C['page'], foreground=C['text'])
        style.configure('TButton', background=C['card'], foreground=C['text'],
                        bordercolor=C['button_border'], padding=5)
        style.map('TButton', background=[('active', C['strip'])])
        style.configure('TEntry', fieldbackground=C['field'], foreground=C['text'],
                        bordercolor=C['field_border'])
        style.configure('TCombobox', fieldbackground=C['field'], foreground=C['text'],
                        background=C['card'])
        style.map('TCombobox', fieldbackground=[('readonly', C['field'])],
                  foreground=[('readonly', C['text'])])
        style.configure('TCheckbutton', background=C['page'], foreground=C['text'])
        style.configure('TRadiobutton', background=C['page'], foreground=C['text'])

    def _generate_default_path(self, sample_id, neuron_id=None):
        """Per-neuron figure folder under the configured GUI figure root."""
        neuron = neuron_id if neuron_id is not None else self.neuron_id.get()
        return _figure_folder(self.figure_output_root, sample_id, neuron)

    def _configured_output_root(self):
        """Output/reload root from the active VisPa config or per-user default."""
        return _resolve_output_root(self.config_path)[0]

    def _configured_figure_output_root(self):
        return _resolve_figure_output_root(self.config_path)[0]

    def _on_sample_id_change(self, *args):
        """Updates output directory automatically when Sample ID changes."""
        if not self.manual_path_set:
            new_path = self._generate_default_path(self.sample_id.get())
            self.output_dir.set(new_path)

    def _on_identity_change(self, *args):
        """Clear coordinates when identity changes, preventing silent stale reuse."""
        after_id = getattr(self, '_soma_autofill_after', None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._soma_autofill_after = None
        identity = (self.sample_id.get().strip(), self.neuron_id.get().strip())
        if identity != self._selected_identity:
            self._selected_identity = identity
            self._autofill_identity = None
            self._neuron_lookup_state = "waiting" if all(identity) else "idle"
            self._cache_status = "checking" if all(identity) else "not checked"
            self._neuron_lookup_error = None
            self.x_coord.set("")
            self.y_coord.set("")
            self.z_coord.set("")
            self._update_nmt_coordinate_display()
            self._clear_identity_preview()
            self._update_neuron_status()
            try:
                normalize_review_identity(*identity)
            except ValueError:
                return
            if getattr(self, '_auto_fill_on_identity', True):
                self._soma_autofill_after = self.root.after(
                    650, self._auto_fill_current_identity)
            else:
                self.root.after(650, self._check_identity_cache)

    def _auto_fill_current_identity(self):
        """Fetch soma coordinates after a valid identity stops changing."""
        self._soma_autofill_after = None
        identity = (self.sample_id.get().strip(), self.neuron_id.get().strip())
        try:
            normalize_review_identity(*identity)
        except ValueError:
            return
        if self._operation_running:
            self._soma_autofill_after = self.root.after(
                350, self._auto_fill_current_identity)
            return
        if self._autofill_identity == identity:
            return
        self.load_and_autofill(silent_success=True, silent_failure=True)

    def _check_identity_cache(self):
        """Report/load cached rendering data after an identity change."""
        sample = self.sample_id.get().strip()
        neuron = self.neuron_id.get().strip()
        if sample and neuron:
            self._activate_cached_figures(
                sample, neuron.removesuffix(".swc"),
                quiet=False, start_fnt=False)

    def _clear_identity_preview(self):
        """Drop any prior identity's displayed and cached panel references."""
        self.preview_files = {}
        self._ephemeral_images = {}
        self.current_preview = None
        self.current_role = None
        self._preview_photo = None
        after_id = getattr(self, "_preview_after", None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._preview_after = None
        label = getattr(self, "preview_label", None)
        if label is not None:
            label.configure(image="", text=EMPTY_PREVIEW_TEXT)
        caption = getattr(self, "preview_caption", None)
        if caption is not None:
            caption.set("")
        if hasattr(self, "_refresh_preview_tabs"):
            self._refresh_preview_tabs()
        if (hasattr(self, "_refresh_dataset_sources")
                and hasattr(self, "soma_source") and hasattr(self, "context_source")):
            self._refresh_dataset_sources()
        if hasattr(self, "_refresh_sagittal_hint"):
            self._refresh_sagittal_hint()

    def _px(self, value):
        """Convert a mockup pixel size to the current display's Tk pixels."""
        return int(round(float(value) * self.scale))

    def _window_geometry(self):
        """Design-sized window, clamped to the visible screen on high-DPI use."""
        width = min(self._px(1298), self.root.winfo_screenwidth() - self._px(24))
        height = min(self._px(1212), self.root.winfo_screenheight() - self._px(96))
        return f"{max(self._px(980), width)}x{max(self._px(760), height)}"

    def _catalog_geometry(self, requested_width, requested_height):
        """Fit the neuron browser near its parent within the visible desktop."""
        left = self.root.winfo_vrootx()
        top = self.root.winfo_vrooty()
        screen_width = self.root.winfo_vrootwidth()
        screen_height = self.root.winfo_vrootheight()
        margin = self._px(24)
        width = min(max(self._px(560), requested_width), max(1, screen_width - 2 * margin))
        height = min(max(self._px(600), requested_height), max(1, screen_height - 2 * margin))
        parent_x = self.root.winfo_rootx()
        parent_y = self.root.winfo_rooty()
        x = parent_x + (self.root.winfo_width() - width) // 2
        y = parent_y + (self.root.winfo_height() - height) // 2
        x = max(left + margin, min(x, left + screen_width - margin - width))
        y = max(top + margin, min(y, top + screen_height - margin - height))
        return width, height, x, y

    @staticmethod
    def _settings_wheel_handler(canvas):
        """Scroll the main settings canvas from any child widget under the cursor."""
        def on_wheel(event):
            try:
                if not canvas.winfo_exists():
                    return "break"
                delta = int(getattr(event, "delta", 0) or 0)
                if delta:
                    canvas.yview_scroll(-1 if delta > 0 else 1, "units")
            except tk.TclError:
                pass
            return "break"
        return on_wheel

    def _bind_settings_wheel(self, widget, handler):
        """Apply one settings-wheel handler to the complete card subtree."""
        widget.bind('<MouseWheel>', handler)
        for child in widget.winfo_children():
            self._bind_settings_wheel(child, handler)

    def build_full_gui(self):
        """Construct the Binavi-style layout: settings left, figure preview right."""
        C = self.COLORS
        P = self._px
        self.root.configure(bg=C['page'])
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.sample_id.trace_add('write', lambda *_: self._refresh_dataset_sources())
        self._refresh_dataset_sources()

        # Header strip
        header = tk.Frame(self.root, bg=C['header'], height=P(54))
        header.grid(row=0, column=0, columnspan=2, sticky='ew')
        header.grid_propagate(False)
        tk.Label(header, text=f"VisPa {__version__}", bg=C['header'],
                 fg=C['header_text'], font=('Segoe UI', 14, 'bold')).pack(
                     side='left', padx=(P(18), P(8)))
        tk.Label(
            header,
            text=(f"{self.version_report['config_name']} "
                  f"{self.version_report['config_version']}"
                  f"{' TEST OUTPUT' if self.test_mode else ''} · "
                  "DEB lab · fMOST neuron reviewer"),
            bg=C['header'],
                 fg=C['header_muted'], font=('Segoe UI', 9)).pack(side='left')
        self._flat_button(header, "Version", self._show_runtime_version,
                          small=True).pack(side='right', padx=(0, P(4)))
        self._flat_button(header, "Settings", self._open_config_yaml,
                          small=True).pack(side='right', padx=P(16))
        self._flat_button(header, "Guide", self._open_guide,
                          small=True).pack(side='right', padx=(0, P(4)))

        # Left column: scrollable setting cards, fixed to the mockup's 392 px.
        left = tk.Frame(
            self.root, bg=C['page'], highlightthickness=1,
            highlightbackground=C['border_dark'])
        left.grid(row=1, column=0, sticky='nsew', padx=(P(14), P(8)), pady=P(12))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(
            left, bg=C['page'], highlightthickness=0, width=P(392),
            yscrollincrement=P(16))
        scrollbar = ttk.Scrollbar(left, orient='vertical', command=canvas.yview)
        inner = tk.Frame(canvas, bg=C['page'])
        self._settings_inner = inner
        self._settings_canvas = canvas
        window_id = canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        def sync_scroll_region(_event=None):
            if not inner.winfo_exists() or not canvas.winfo_exists():
                return
            canvas.configure(scrollregion=canvas.bbox('all'))
            if inner.winfo_reqheight() <= canvas.winfo_height():
                scrollbar.grid_remove()
            else:
                scrollbar.grid()

        inner.bind('<Configure>', sync_scroll_region)
        canvas.bind(
            '<Configure>',
            lambda event: (canvas.itemconfigure(window_id, width=event.width),
                           sync_scroll_region()))
        settings_wheel = self._settings_wheel_handler(canvas)
        for widget in (canvas, inner):
            widget.bind('<MouseWheel>', settings_wheel)

        body = self._card(inner, "Neuron input")
        self._field(body, "Sample ID", self.sample_id, 0, width=16)
        self._field(body, "Neuron ID", self.neuron_id, 1, width=16)
        self.neuron_status_var = tk.StringVar(value="Neuron status: not loaded")
        self.region_status_var = tk.StringVar(value="Region: unavailable")
        status_row = tk.Frame(body, bg=C['card'])
        status_row.grid(row=2, column=0, columnspan=3, sticky='ew',
                        pady=(P(4), P(2)))
        for column in range(2):
            status_row.grid_columnconfigure(column, weight=1)
        status_boxes = (
            (self.neuron_status_var, C['accent_soft'], 0, 0, 2),
            (self.region_status_var, C['strip'], 1, 0, 2),
        )
        for variable, fill, row, column, columnspan in status_boxes:
            box = tk.Frame(status_row, bg=fill, highlightthickness=1,
                           highlightbackground=C['border'])
            box.grid(row=row, column=column, columnspan=columnspan, sticky='nsew',
                     padx=(0 if column == 0 else P(3), 0),
                     pady=(0, P(3)) if row == 0 else (P(3), 0))
            tk.Label(box, textvariable=variable, bg=fill, fg=C['text'],
                     anchor='w', font=('Segoe UI', 9, 'bold'), justify='left',
                     wraplength=P(155)).pack(fill='x', padx=P(7), pady=P(5))
        self.neuron_catalog_open_button = self._flat_button(
            body, "Neuron list", self._open_neuron_catalog, primary=True)
        self.neuron_catalog_open_button.grid(
            row=3, column=0, columnspan=3, sticky='ew', pady=(P(4), P(2)))
        neuron_actions = tk.Frame(body, bg=C['card'])
        neuron_actions.grid(row=4, column=0, columnspan=3, sticky='ew',
                            pady=(P(4), P(2)))
        neuron_actions.grid_columnconfigure(0, weight=1)
        neuron_actions.grid_columnconfigure(1, weight=1)
        self._flat_button(
            neuron_actions, "Update figures", self._update_current_identity,
            small=True, outlined=True).grid(
                row=0, column=0, sticky='ew', padx=(0, P(3)))
        self._flat_button(
            neuron_actions, "Re-process", self._reprocess_current_identity,
            primary=True, small=True, color='#9a5a24',
            active='#7d4318', outlined=True).grid(
                row=0, column=1, sticky='ew', padx=(P(3), 0))
        body = self._card(inner, "Target soma coordinates")
        physical = tk.Frame(
            body, bg=C['accent_soft'], highlightthickness=1,
            highlightbackground=C['border'])
        physical.grid(row=0, column=0, sticky='ew', pady=(P(2), P(5)))
        tk.Label(
            physical, text='Physical coordinate (µm)', bg=C['accent_soft'],
            fg=C['header_text'], font=('Segoe UI', 9, 'bold')).grid(
                row=0, column=0, columnspan=6, sticky='w',
                padx=P(7), pady=(P(5), P(2)))
        for column, (label, variable) in enumerate((
                ("X", self.x_coord), ("Y", self.y_coord), ("Z", self.z_coord))):
            tk.Label(physical, text=label, bg=C['accent_soft'], fg=C['muted'],
                     font=('Segoe UI', 9)).grid(
                         row=1, column=column * 2, sticky='w',
                         padx=(P(7) if column == 0 else P(6), 0),
                         pady=(0, P(5)))
            entry = tk.Entry(
                physical, textvariable=variable, width=7, relief='flat',
                bg=C['field'], fg=C['text'], highlightthickness=1,
                highlightbackground=C['field_border'],
                highlightcolor=C['accent'],
                font=('Segoe UI', 9), insertbackground=C['text'])
            entry.grid(row=1, column=column * 2 + 1, sticky='ew',
                       padx=(P(6), P(8) if column < 2 else P(7)),
                       pady=(0, P(5)), ipady=P(3))
            physical.grid_columnconfigure(column * 2 + 1, weight=1)

        template = tk.Frame(
            body, bg=C['strip'], highlightthickness=1,
            highlightbackground=C['border'])
        template.grid(row=1, column=0, sticky='ew', pady=(0, P(3)))
        tk.Label(
            template, text='NMT template coordinate (voxel)', bg=C['strip'],
            fg=C['header_text'], font=('Segoe UI', 9, 'bold')).grid(
                row=0, column=0, columnspan=6, sticky='w',
                padx=P(7), pady=(P(5), P(2)))
        for column, (label, variable) in enumerate((
                ("X", self.nmt_x), ("Y", self.nmt_y), ("Z", self.nmt_z))):
            tk.Label(template, text=label, bg=C['strip'], fg=C['muted'],
                     font=('Segoe UI', 9)).grid(
                         row=1, column=column * 2, sticky='w',
                         padx=(P(7) if column == 0 else P(6), 0),
                         pady=(0, P(5)))
            entry = tk.Entry(
                template, textvariable=variable, width=7, relief='flat',
                bg=C['field'], fg=C['text'], readonlybackground=C['field'],
                highlightthickness=1, highlightbackground=C['field_border'],
                font=('Segoe UI', 9, 'bold'), state='readonly')
            entry.grid(row=1, column=column * 2 + 1, sticky='ew',
                       padx=(P(6), P(8) if column < 2 else P(7)),
                       pady=(0, P(5)), ipady=P(3))
            template.grid_columnconfigure(column * 2 + 1, weight=1)
        tk.Label(
            body, text=('Derived by VisPa from IONData soma + configured NMT '
                        'atlas; not inferred from edited physical X/Y/Z.'),
            bg=C['card'], fg=C['muted'], font=('Segoe UI', 8),
            justify='left', anchor='w', wraplength=P(340)).grid(
                row=2, column=0, sticky='ew', pady=(0, P(3)))

        # Put Soma and Context in the compact top row, with Sagittal spanning
        # both columns underneath. Source text remains visible through wrapping.
        body = self._card(inner, 'Plotting settings')
        for column in range(2):
            body.grid_columnconfigure(column, weight=1, uniform='plots')
        body.grid_rowconfigure(0, weight=1)

        def plot_box(row, column, title, *, columnspan=1):
            box = tk.Frame(body, bg=C['card'], highlightthickness=1,
                           highlightbackground=C['border'])
            box.grid(
                row=row, column=column, columnspan=columnspan, sticky='nsew',
                padx=(0 if column == 0 else P(3),
                      0 if column + columnspan >= 2 else P(3)),
                pady=(0, P(4)) if row else (0, P(6)))
            tk.Label(box, text=title, bg=C['card'], fg=C['header_text'],
                     font=('Segoe UI', 9, 'bold'), justify='left').pack(
                         anchor='w', padx=P(6), pady=(P(5), P(3)))
            return box

        def plot_source(box, text=None, variable=None, *, wrap_width=156):
            tk.Label(box, text=text, textvariable=variable, bg=C['card'],
                     fg=C['muted'], font=('Segoe UI', 9), justify='left',
                     anchor='w', wraplength=P(wrap_width)).pack(fill='x', padx=P(6),
                                                       pady=(0, P(3)))

        soma_box = plot_box(0, 0, 'Soma plot')
        plot_source(soma_box, text='Window (blocks)')
        tk.Entry(soma_box, textvariable=self.soma_cubes, width=5, relief='flat',
                 bg=C['field'], fg=C['text'], highlightthickness=1,
                 highlightbackground=C['field_border'],
                 highlightcolor=C['accent'],
                 font=('Segoe UI', 9), insertbackground=C['text']).pack(
                     anchor='w', padx=P(6), pady=(0, P(4)), ipady=P(1))
        plot_source(soma_box, text=(
            f"Block 234×234×270 µm · XY: 1 block = 234 µm · "
            f"default {REVIEW_SETTINGS['soma_window']['cubes_xy']:g}"))
        plot_source(soma_box, variable=self.soma_source)

        ctx_box = plot_box(0, 1, 'Context plot')
        ctx_fields = tk.Frame(ctx_box, bg=C['card'])
        ctx_fields.pack(fill='x', padx=P(6), pady=(0, P(4)))
        for column, (label, variable) in enumerate((
                ('W', self.width_um), ('H', self.height_um),
                ('D', self.depth_um))):
            field = tk.Frame(ctx_fields, bg=C['card'])
            field.grid(row=0, column=column, sticky='ew', padx=P(1))
            ctx_fields.grid_columnconfigure(column, weight=1, uniform='context')
            tk.Label(field, text=label, bg=C['card'], fg=C['muted'],
                     font=('Segoe UI', 9)).pack(anchor='w')
            tk.Entry(field, textvariable=variable, width=4, relief='flat',
                     bg=C['field'], fg=C['text'], highlightthickness=1,
                     highlightbackground=C['field_border'],
                     highlightcolor=C['accent'],
                     font=('Segoe UI', 9), insertbackground=C['text']).pack(
                         fill='x', ipady=P(1))
        plot_source(ctx_box, text='Dimensions in µm · 3 µm per section')
        plot_source(ctx_box, variable=self.context_source)

        sagittal_box = plot_box(
            1, 0, 'Sagittal plot', columnspan=2)
        self.sagittal_hint = tk.Label(sagittal_box, text='', bg=C['card'],
                                      fg=C['muted'], font=('Segoe UI', 9),
                                      anchor='w', wraplength=P(340), justify='left')
        self.sagittal_hint.pack(fill='x', padx=P(6), pady=(0, P(4)))
        for variable in (self.sample_id, self.neuron_id, self.plot_sagittal):
            variable.trace_add('write', lambda *_: self._refresh_sagittal_hint())
        self._refresh_sagittal_hint()

        # Saving: output folder only; the selected panels are always written.
        body = self._card(inner, "Saving")
        tk.Label(body, text="Output folder", bg=C['card'], fg=C['muted'],
                 font=('Segoe UI', 9)).grid(
                     row=0, column=0, columnspan=3, sticky='w', pady=(P(2), P(3)))
        out_entry = tk.Entry(body, textvariable=self.output_dir, relief='flat',
                             bg=C['field'], fg=C['text'], highlightthickness=1,
                             highlightbackground=C['field_border'],
                             highlightcolor=C['accent'],
                             font=('Segoe UI', 9), insertbackground=C['text'])
        out_entry.grid(row=1, column=0, columnspan=3, sticky='ew',
                       pady=(0, P(6)), ipady=P(3))
        out_entry.bind("<Key>", lambda event: setattr(self, 'manual_path_set', True))
        body.grid_columnconfigure(0, weight=1)
        folder_buttons = tk.Frame(body, bg=C['card'])
        folder_buttons.grid(row=2, column=0, columnspan=3, sticky='ew')
        self._flat_button(folder_buttons, "Browse…", self.browse_folder, small=True,
                          color='#eef3f6', active='#dde8ee').pack(
                              side='left', fill='x', expand=True, padx=(0, P(4)))
        self._flat_button(folder_buttons, "Open output folder", self._open_output_folder,
                          small=True, color='#eef3f6', active='#dde8ee').pack(
                              side='left', fill='x', expand=True, padx=(P(4), 0))
        self.soma_nifti_check = tk.Checkbutton(
            body, text="Save Soma NIfTI (.nii.gz)", variable=self.save_soma_nifti,
            bg=C['card'], fg=C['text'], activebackground=C['card'],
            selectcolor=C['field'], font=('Segoe UI', 9), cursor='hand2')
        self.soma_nifti_check.grid(row=3, column=0, columnspan=3, sticky='w',
                                   pady=(P(8), P(2)))

        # Right column: figure preview
        right = tk.Frame(self.root, bg=C['page'])
        right.grid(row=1, column=1, sticky='nsew', padx=(P(8), P(14)), pady=P(12))
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        preview_card = tk.Frame(right, bg=C['card'], highlightbackground=C['border'],
                                highlightthickness=1)
        preview_card.grid(row=0, column=0, sticky='nsew')
        preview_card.grid_propagate(False)
        head = tk.Frame(preview_card, bg=C['header'])
        head.pack(fill='x', pady=(0, P(6)))
        tk.Label(head, text="Figure preview", bg=C['header'], fg=C['header_text'],
                 font=('Segoe UI', 11, 'bold')).pack(
                     side='left', padx=P(14), pady=P(6))
        self.preview_caption = tk.StringVar(value="")
        tk.Label(head, textvariable=self.preview_caption, bg=C['header'], fg=C['header_muted'],
                 font=('Segoe UI', 9)).pack(side='right', padx=P(14), pady=(P(10), P(2)))
        self.preview_identity = tk.StringVar(value="")
        tk.Label(head, textvariable=self.preview_identity, bg=C['header'],
                 fg=C['header_text'], font=('Segoe UI', 9, 'bold')).pack(
                     side='right', padx=(0, P(10)), pady=(P(10), P(2)))
        for variable in (self.sample_id, self.neuron_id):
            variable.trace_add('write', lambda *_: self._refresh_preview_identity())
        self._refresh_preview_identity()
        self.preview_holder = tk.Frame(preview_card, bg=C['preview_bg'],
                                       height=P(520),
                                       highlightbackground='#0b141c', highlightthickness=1)
        self.preview_holder.pack(fill='both', expand=True, padx=P(14), pady=(0, P(8)))
        self.preview_holder.pack_propagate(False)
        self.preview_label = tk.Label(
            self.preview_holder, bg=C['preview_bg'], fg='#c9d6de', justify='center',
            font=('Segoe UI', 11), text=EMPTY_PREVIEW_TEXT)
        self.preview_label.pack(fill='both', expand=True)
        self.preview_holder.bind('<Configure>', self._on_preview_resize)
        tabs = tk.Frame(preview_card, bg=C['card'])
        tabs.pack(fill='x', padx=P(14), pady=(0, P(12)))
        # Segmented grid: equal cells separated by 1-px border lines.
        tab_grid = tk.Frame(tabs, bg=C['border'], highlightthickness=1,
                            highlightbackground=C['border'])
        tab_grid.pack(side='left')
        for index, (role, label) in enumerate((('Soma', 'Soma'), ('Context', 'Context'),
                                               ('Sagittal', 'Sagittal'),
                                               ('TrioPlot', 'TrioPlot'),
                                               ('SWC3D', SWC_BRAIN_VIEW_LABEL))):
            button = tk.Button(tab_grid, text=label,
                               command=lambda r=role: self._show_role(r),
                               relief='raised', bd=1, bg=C['card'], fg=C['text'],
                               activebackground=C['strip'], activeforeground=C['text'],
                               disabledforeground=C['disabled'],
                               font=('Segoe UI', 9, 'bold'), padx=P(16), pady=P(4),
                               cursor='hand2', highlightthickness=1,
                               highlightbackground=C['button_border'],
                               highlightcolor=C['accent'])
            button.grid(row=0, column=index, sticky='nsew',
                        padx=(0 if index == 0 else 1, 0))
            tab_grid.grid_columnconfigure(index, weight=1, uniform='tabs')
            self.preview_buttons[role] = button
        # Process log (the toolkit's fetch/download/render lines, like the legacy status)
        log_frame = tk.Frame(preview_card, bg=C['card'])
        log_frame.pack(fill='x', padx=P(14), pady=(0, P(10)))
        tk.Label(log_frame, text="Process log", bg=C['card'], fg=C['muted'],
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w')
        self.log_widget = tk.Text(log_frame, height=5, bg=C['field'], fg=C['text'],
                                  relief='flat', highlightthickness=1,
                                  highlightbackground=C['border'],
                                  font=('Consolas', 8), wrap='none', state='disabled')
        self.log_widget.pack(fill='x', pady=(P(2), 0))
        self._append_log("Ready.")

        # Bottom action bar
        actions = tk.Frame(self.root, bg=C['card'], highlightbackground=C['border'],
                           highlightthickness=1)
        actions.grid(row=3, column=0, columnspan=2, sticky='ew')
        action_row = tk.Frame(actions, bg=C['card'])
        action_row.pack(fill='x', padx=P(14), pady=P(10))
        render_button = self._flat_button(
            action_row, "Render", self.run_selected, primary=True,
            color='#6b4fa0', active='#563d85')
        render_button.configure(font=('Segoe UI', 12, 'bold'),
                                padx=P(34), pady=P(12))
        render_button.pack(side='left', padx=(0, P(10)))
        tk.Checkbutton(action_row, text="Save outputs", variable=self.save_outputs,
                       bg=C['card'], fg=C['text'], activebackground=C['card'],
                       selectcolor=C['field'], font=('Segoe UI', 10),
                       cursor='hand2').pack(side='left', padx=(0, P(12)))
        brain_button = self._flat_button(
            action_row, SWC_BRAIN_VIEW_INTERACTIVE_LABEL,
            self._on_template_brain_view, primary=True,
            color='#e07a1f', active='#b95f10', outlined=True)
        brain_button.configure(font=('Segoe UI', 12, 'bold'),
                               padx=P(38), pady=P(12))
        brain_button.pack(side='left')
        fnt_button = self._flat_button(
            action_row, "fnt-tracer", self._on_fnt_tracer,
            color='#fff3e8', active='#ffe3c9')
        fnt_button.configure(font=('Segoe UI', 11, 'bold'), fg='#b95f10',
                             activeforeground='#8a4308', padx=P(22), pady=P(12))
        fnt_button.pack(side='left', padx=(P(10), 0))
        self._flat_button(action_row, "FNT setup…", self._on_fnt_setup).pack(
            side='left', padx=(P(6), 0))
        self._flat_button(action_row, "Check data", self._start_resource_check).pack(
            side='left', padx=(P(6), 0))
        self._flat_button(action_row, "Bulk review…", self._on_bulk_review).pack(
            side='left', padx=(P(6), 0))
        # Status strip
        strip = tk.Frame(self.root, bg=C['strip'], highlightbackground=C['border'],
                         highlightthickness=1)
        strip.grid(row=2, column=0, columnspan=2, sticky='ew')
        tk.Label(strip, textvariable=self.status_text, bg=C['strip'], fg=C['text'],
                 font=('Segoe UI', 9), anchor='w').pack(
                     side='left', padx=P(14), pady=P(5))
        self.progress = ttk.Progressbar(strip, mode='indeterminate', length=P(240))

        self._refresh_preview_tabs()
        self._refresh_plot_state()
        self._bind_settings_wheel(
            inner, self._settings_wheel_handler(canvas))
        self.root.after_idle(sync_scroll_region)
        # Keyboard access to the selected-panel action (also handy for scripted checks).
        self.root.bind('<F5>', lambda event: self.run_selected())
        self.root.update_idletasks()
        self.root.minsize(self._px(980), self._px(760))
        # Quick reload of already-rendered figures (also available as a button).
        self.root.after(
            1500,
            lambda: self._reload_existing(
                quiet=True, rerender_if_stale=False))
        self.root.after(700, self._start_resource_check)

    def _review_step(self, parent, row, number, name, headline, detail,
                     highlight=False):
        """One review-stage row: numbered badge, bold stage, muted detail."""
        C = self.COLORS
        P = self._px
        bg = '#f08a24' if highlight else (C['strip'] if row % 2 else C['card'])
        fg = '#ffffff' if highlight else C['text']
        frame = tk.Frame(parent, bg=bg)
        frame.grid(row=row, column=0, sticky='ew', pady=(0, P(2)))
        frame.grid_columnconfigure(1, weight=1)
        tk.Label(frame, text=str(number), width=2,
                 bg='#ffffff' if highlight else C['field'],
                 fg='#e07a1f' if highlight else C['text'],
                 font=('Segoe UI', 8, 'bold')).grid(
                     row=0, column=0, rowspan=2, sticky='nw',
                     padx=(P(8), P(8)), pady=(P(5), P(2)))
        line = tk.Frame(frame, bg=bg)
        line.grid(row=0, column=1, sticky='w', padx=(0, P(6)), pady=(P(4), 0))
        tk.Label(line, text=name, bg=bg, fg=fg,
                 font=('Segoe UI', 9, 'bold')).pack(side='left')
        tk.Label(line, text=headline, bg=bg, fg=fg,
                 font=('Segoe UI', 9)).pack(side='left', padx=(P(10), 0))
        if detail:
            tk.Label(frame, text=detail, bg=bg,
                     fg='#fff2e2' if highlight else C['muted'],
                     font=('Segoe UI', 8), anchor='w', justify='left',
                     wraplength=P(295)).grid(
                         row=1, column=1, sticky='w', padx=(0, P(6)),
                         pady=(0, P(4)))
        self.root.after(150, self._drain_log)

    # ---------- styling and preview helpers ----------
    def _open_guide(self):
        """Show the scrollable workflow reference on demand."""
        window = getattr(self, '_guide_window', None)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            return
        C = self.COLORS
        P = self._px
        window = tk.Toplevel(self.root)
        self._guide_window = window
        window.title('VisPa · Guide')
        window.configure(bg=C['page'])
        width, height, x, y = self._catalog_geometry(P(690), P(700))
        window.geometry(f'{width}x{height}+{x}+{y}')
        window.minsize(P(480), P(400))
        window.protocol('WM_DELETE_WINDOW', window.destroy)
        tk.Label(window, text='Review workflow', bg=C['page'], fg=C['header_text'],
                 font=('Segoe UI', 14, 'bold')).pack(anchor='w', padx=P(16), pady=(P(14), P(5)))
        outer = tk.Frame(window, bg=C['page'])
        outer.pack(fill='both', expand=True, padx=P(12), pady=(0, P(12)))
        canvas = tk.Canvas(outer, bg=C['page'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        inner = tk.Frame(canvas, bg=C['page'])
        window_id = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window_id, width=event.width))
        for section, details in self._guide_sections():
            card = self._card(inner, section)
            for detail in details:
                tk.Label(card, text='• ' + detail, bg=C['card'], fg=C['text'],
                         anchor='w', justify='left', wraplength=P(610),
                         font=('Segoe UI', 9)).pack(fill='x', pady=(0, P(5)))
        def on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), 'units')
        def bind_wheel(widget):
            widget.bind('<MouseWheel>', on_wheel)
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(inner)

    def _runtime_version_message(self):
        report = self.version_report
        detail = (
            f"VisPa: {report['vispa_version']}\n"
            f"Config: {report['config_name']} {report['config_version']}\n"
            f"Config updated: {report['config_updated_at']}\n"
            f"Packaged config: {report.get('packaged_config_name')} "
            f"{report.get('packaged_config_version')}\n"
            f"Precedence: {report.get('config_precedence')}\n"
            f"Selected config present: {report.get('selected_config_present')}\n"
            f"Mode: {'test output' if self.test_mode else 'configured output'}\n"
            f"Path: {report['config_path']}\n"
            f"Origin: {report['config_origin']}\n"
            f"Output: {report['resolved_output_root']}\n"
            f"Cache: {report['resolved_cache_root']}\n"
            f"SHA-256: {report['config_sha256']}")
        return detail

    @staticmethod
    def _version_display_rows(report):
        """Return distinct application and configuration version values."""
        app_version = report.get("vispa_version") or "unknown"
        config_name = report.get("config_name") or "unknown"
        config_version = report.get("config_version") or "unversioned"
        updated = report.get("config_updated_at") or "unknown"
        packaged_name = report.get("packaged_config_name") or "unknown"
        packaged_version = report.get("packaged_config_version") or "unknown"
        return (
            ("APP VERSION", f"VisPa {app_version}"),
            ("CONFIG VERSION",
             f"{config_name} · {config_version}\n"
             f"base {packaged_name} {packaged_version}\n"
             f"Updated: {updated}"),
        )

    def _show_runtime_version(self):
        messagebox.showinfo("VisPa runtime version", self._runtime_version_message())

    @staticmethod
    def _guide_sections():
        """Keep workflow guidance available without occupying the review pane."""
        return (
            ('1 · Select a neuron', (
                'Enter Sample ID and Neuron ID, or choose an exact SWC ID from Neuron list. The status areas report neuron/cache, atlas-derived side, and portal region separately.',
                'Changing identity clears the previous coordinates and previews. After the SWC loads, VisPa updates the Neuron status with the cached rendering state.')),
            ('2 · Check sources and target', (
                'A valid identity loads the raw SWC root into X/Y/Z in µm. Edit the coordinates when the marker needs correction; use the displayed source hints to inspect the configured context.',
                'Update figures refreshes IONData and rerenders from cached acquisitions. Re-process refreshes the SWC and reacquires source cubes and slices.')),
            ('3 · Render and inspect', (
                'Render (F5) builds Soma, Context, Sagittal and TrioPlot. Switch tabs to inspect each completed figure, marker position and axes.',
                'Soma uses cached 0.65 µm CH1 cubes when available; missing cubes may be fetched. A failed input or panel is reported in the status/log.')),
            ('4 · Save and provenance', (
                'Save outputs writes figures and Soma NIfTI to the Saving folder; with Save outputs off, figures are temporary previews.',
                'Open output folder opens the Saving folder. Check the run receipt for identity, sources, parameters and paths; cached inputs may be reused.')),
            ('5 · Brain view and FNT', (
                'The 3D SWC tab renders the configured processed trace and brain mesh. Region overlay requires configured region assets and a resolved region; inspect its status and log when unavailable.',
                'Open interactive 3D view launches the optional local viewer. Open fnt-tracer launches the matching local FNT project when the program and project are available.')),
            ('6 · Settings and recovery', (
                'Settings edits the current profile. Save and reload it before relying on changed paths, output options or mesh settings; inspect the settings validation message.',
                'For missing sources, failed downloads or rendering errors, read the status/log, correct the identity or configuration, then retry. Do not interpret a missing figure as an anatomical result.')),
        )

    def _card(self, parent, title, subtitle=None):
        C = self.COLORS
        P = self._px
        card = tk.Frame(parent, bg=C['card'], highlightbackground=C['border'],
                        highlightthickness=1)
        card.pack(fill='x', padx=P(2), pady=(0, P(1)))
        head = tk.Frame(card, bg=C['card'])
        head.pack(fill='x', anchor='w', padx=P(12), pady=(P(4), P(2)))
        tk.Label(head, text=title, bg=C['card'], fg=C['header_text'],
                 font=('Segoe UI', 11, 'bold')).pack(side='left')
        if subtitle:
            tk.Label(head, text=subtitle, bg=C['card'], fg=C['muted'],
                     font=('Segoe UI', 8)).pack(side='left', padx=(P(8), 0))
        body = tk.Frame(card, bg=C['card'])
        body.pack(fill='x', padx=P(12), pady=(P(4), P(5)))
        return body

    def _field(self, parent, label, variable, row, column=0, width=12, hint=None):
        C = self.COLORS
        P = self._px
        tk.Label(parent, text=label, bg=C['card'], fg=C['muted'],
                 font=('Segoe UI', 10)).grid(row=row, column=column, sticky='w',
                                            pady=P(1))
        entry = tk.Entry(parent, textvariable=variable, width=width, relief='flat',
                         bg=C['field'], fg=C['text'], highlightthickness=1,
                         highlightbackground=C['field_border'],
                         highlightcolor=C['accent'],
                         font=('Segoe UI', 10), insertbackground=C['text'])
        entry.grid(row=row, column=column + 1, sticky='ew',
                   padx=(P(8), P(6)), pady=P(1), ipady=P(2))
        parent.grid_columnconfigure(column + 1, weight=1)
        if hint:
            tk.Label(parent, text=hint, bg=C['card'], fg=C['muted'],
                     font=('Segoe UI', 9)).grid(row=row, column=column + 2,
                                                sticky='w', padx=(0, P(4)),
                                                pady=P(1))
        return entry

    def _flat_button(self, parent, text, command, primary=False, small=False,
                     color=None, active=None, outlined=True):
        C = self.COLORS
        fill = color or (C['accent'] if primary else C['card'])
        hover = active or (C['accent_dark'] if primary else C['strip'])
        button_text = ('#173747' if color in {'#eef3f6', '#eef6f6', '#fff3e8'}
                       else '#ffffff' if primary else C['text'])
        return tk.Button(
            parent, text=text, command=command,
            relief='raised' if outlined else 'flat', bd=1 if outlined else 0,
            bg=fill,
            fg=button_text,
            activebackground=hover,
            activeforeground=button_text,
            highlightthickness=1,
            highlightbackground=C['button_border'],
            highlightcolor=C['accent'],
            font=('Segoe UI', 10 if small else 11, 'bold'),
            padx=10 if small else 24, pady=3 if small else 9, cursor='hand2')

    def _refresh_preview_identity(self):
        if getattr(self, 'preview_identity', None) is not None:
            sample = self.sample_id.get().strip() or '—'
            neuron = self.neuron_id.get().strip() or '—'
            self.preview_identity.set(f"{sample} · {neuron}")

    def _on_catalog_sample_change(self, *args):
        current = self.sample_id.get().strip()
        if current == self._catalog_observed_sample_id:
            return
        self._catalog_observed_sample_id = current
        self._catalog_request_id += 1
        self._catalog_side_request_id = getattr(
            self, "_catalog_side_request_id", 0) + 1
        self._catalog_sample_id = None
        self._catalog_snapshot = None
        self._catalog_side_snapshot_id = None
        self._catalog_side_result = None
        self._catalog_side_state = "idle"
        self._catalog_rows_by_iid.clear()
        if getattr(self, "_catalog_reload_after", None) is not None:
            try:
                self.root.after_cancel(self._catalog_reload_after)
            except Exception:
                pass
            self._catalog_reload_after = None
        if getattr(self, "_catalog_filter_after", None) is not None:
            try:
                self.root.after_cancel(self._catalog_filter_after)
            except Exception:
                pass
            self._catalog_filter_after = None
        if self.neuron_catalog_table is not None:
            for item in self.neuron_catalog_table.get_children():
                self.neuron_catalog_table.delete(item)
        if self._neuron_catalog_window is not None:
            if self.neuron_catalog_load_button is not None:
                self.neuron_catalog_load_button.configure(state='normal')
            if self.neuron_catalog_export_button is not None:
                self.neuron_catalog_export_button.configure(state='disabled')
            self.neuron_catalog_title.set(f"Refreshing sample {current or '—'}")
            self.neuron_catalog_side_summary.set("")
            self.neuron_catalog_info.set("Sample changed. Refreshing the neuron list…")
            filter_variable = getattr(self, "_catalog_filter_var", None)
            if filter_variable is not None:
                filter_variable.set("")
            region_variable = getattr(
                self, "_catalog_region_filter_var", None)
            if region_variable is not None:
                region_variable.set(CATALOG_ALL_REGIONS)
            if current:
                def reload_current_sample():
                    self._catalog_reload_after = None
                    if (self._neuron_catalog_window is not None
                            and self.sample_id.get().strip() == current):
                        self.load_neuron_catalog()

                self._catalog_reload_after = self.root.after(
                    700, reload_current_sample)

    def _open_neuron_catalog(self):
        """Open the compact live-or-snapshot browser; keep the Sample card uncluttered."""
        C = self.COLORS
        window = self._neuron_catalog_window
        if window is not None and window.winfo_exists():
            if self.neuron_catalog_table is None:
                self._close_neuron_catalog()
                window = None
            else:
                window.lift()
                if (self._catalog_sample_id == self.sample_id.get().strip()
                        and self._catalog_snapshot is not None
                        and IT.catalog_snapshot_unchanged(self._catalog_snapshot)):
                    return
                self.load_neuron_catalog()
                return

        window = tk.Toplevel(self.root)
        window.withdraw()
        window.configure(bg=C['page'])
        window.title("Neuron list")
        window.transient(self.root)
        window.grid_rowconfigure(3, weight=1)
        window.grid_columnconfigure(0, weight=1)
        self._neuron_catalog_window = window
        summary = tk.Frame(
            window, bg=C['accent_soft'], highlightthickness=2,
            highlightbackground=C['border_dark'])
        summary.grid(row=0, column=0, columnspan=2, sticky='ew',
                     padx=12, pady=(10, 4))
        summary.grid_columnconfigure(0, weight=1)
        tk.Label(
            summary, textvariable=self.neuron_catalog_title,
            bg=C['accent_soft'], fg=C['header_text'],
            font=('Segoe UI', 10, 'bold'), anchor='w').grid(
                row=0, column=0, sticky='ew', padx=(9, 6), pady=(8, 2))
        tk.Label(
            summary, textvariable=self.neuron_catalog_side_summary,
            bg=C['accent_soft'], fg=C['header_text'],
            font=('Segoe UI', 9, 'bold'), anchor='e').grid(
                row=0, column=1, sticky='e', padx=(6, 9), pady=(8, 2))
        tk.Label(
            summary, textvariable=self.neuron_catalog_info,
            bg=C['accent_soft'], fg=C['muted'],
            font=('Segoe UI', 8), justify='left', anchor='w',
            wraplength=510).grid(
                row=1, column=0, columnspan=2, sticky='ew',
                padx=9, pady=(0, 8))
        tk.Label(
            window,
            text=("INS cohort AnimalIDs (megatable): 331, 605, 631, 797, 900, 936, 945, 948\n"
                  "Separate sample: 747 (SampleID 250432)"),
            justify='left', anchor='w', wraplength=520, padx=12, pady=0,
            bg=C['page'], foreground=C['muted']).grid(
                row=1, column=0, columnspan=2, sticky='ew')
        filter_row = tk.Frame(
            window, bg=C['page'], highlightthickness=1,
            highlightbackground=C['border_dark'])
        filter_row.grid(row=2, column=0, columnspan=2, sticky='ew',
                        padx=12, pady=(2, 6))
        filter_row.grid_columnconfigure(1, weight=1)
        tk.Label(
            filter_row, text="Go to", font=('Segoe UI', 9, 'bold'),
            bg=C['page'], foreground=C['muted']).grid(
                row=0, column=0, sticky='w', padx=(8, 6), pady=6)
        filter_entry = tk.Entry(
            filter_row, textvariable=self._catalog_filter_var, relief='flat',
            bg=C['field'], fg=C['text'], highlightthickness=1,
            highlightbackground=C['field_border'],
            highlightcolor=C['border_dark'],
            font=('Segoe UI', 9), insertbackground=C['text'])
        filter_entry.grid(row=0, column=1, sticky='ew', pady=6, ipady=3)

        def clear_catalog_filters(_event=None):
            self._catalog_filter_var.set("")
            self._catalog_region_filter_var.set(CATALOG_ALL_REGIONS)

        filter_entry.bind('<Escape>', clear_catalog_filters)
        tk.Label(
            filter_row, text="Region", font=('Segoe UI', 9, 'bold'),
            bg=C['page'], foreground=C['muted']).grid(
                row=0, column=2, sticky='w', padx=(10, 6), pady=6)
        region_values = self._catalog_region_values(
            (self._catalog_snapshot or {}).get("rows") or ())
        self._catalog_region_selector = ttk.Combobox(
            filter_row, textvariable=self._catalog_region_filter_var,
            values=region_values, state='readonly', width=20,
            style='VisPa.Neuron.TCombobox')
        self._catalog_region_selector.grid(
            row=0, column=3, sticky='ew', pady=6)
        self._catalog_region_selector.bind(
            '<<ComboboxSelected>>', self._schedule_neuron_catalog_filter)
        tk.Label(
            filter_row, textvariable=self.neuron_catalog_visible_count,
            font=('Segoe UI', 8), bg=C['page'],
            foreground=C['muted']).grid(
                row=0, column=4, sticky='e', padx=(9, 8), pady=6)
        table_frame = tk.Frame(window, bg=C['page'])
        table_frame.grid(row=3, column=0, columnspan=2, sticky='nsew', padx=12)
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        catalog_style = ttk.Style(window)
        catalog_style.configure(
            "VisPa.Neuron.TCombobox",
            fieldbackground=C['field'], foreground=C['text'],
            arrowcolor=C['border_dark'],
            bordercolor=C['border_dark'], lightcolor=C['border_dark'],
            darkcolor=C['border_dark'], padding=3)
        catalog_style.configure(
            "VisPa.Neuron.Treeview",
            background=C['field'], fieldbackground=C['field'],
            foreground=self.COLORS['text'], rowheight=self._px(26),
            borderwidth=1, relief="solid", bordercolor=C['border_dark'],
            lightcolor=C['border_dark'], darkcolor=C['border_dark'])
        catalog_style.map(
            "VisPa.Neuron.Treeview",
            background=[("selected", C['accent'])],
            foreground=[("selected", C['header'])])
        self.neuron_catalog_table = ttk.Treeview(
            table_frame, columns=('side', 'neuron_id', 'portal_region'),
            show='headings', height=18, selectmode='browse',
            style="VisPa.Neuron.Treeview")
        self.neuron_catalog_table.heading(
            'side', text='Side', command=lambda: self._sort_neuron_catalog('side'))
        self.neuron_catalog_table.heading(
            'neuron_id', text='SWC ID',
            command=lambda: self._sort_neuron_catalog('neuron_id'))
        self.neuron_catalog_table.heading(
            'portal_region', text='Ion_NMT_region',
            command=lambda: self._sort_neuron_catalog('portal_region'))
        self.neuron_catalog_table.column('side', width=92, stretch=False, anchor='center')
        self.neuron_catalog_table.column('neuron_id', width=108, stretch=False)
        self.neuron_catalog_table.column('portal_region', width=282, stretch=True)
        self.neuron_catalog_table.tag_configure(
            'side-left', background='#263c48', foreground='#c5e1f2')
        self.neuron_catalog_table.tag_configure(
            'side-right', background='#483629', foreground='#f2ceb2')
        self.neuron_catalog_table.tag_configure(
            'side-checking', background='#46412c', foreground='#f0e5b5')
        self.neuron_catalog_table.tag_configure(
            'side-unknown', background=C['card'], foreground=C['muted'])
        catalog_scroll = ttk.Scrollbar(
            table_frame, orient='vertical', command=self.neuron_catalog_table.yview)
        self.neuron_catalog_table.configure(yscrollcommand=catalog_scroll.set)
        self.neuron_catalog_table.grid(row=0, column=0, sticky='nsew')
        catalog_scroll.grid(row=0, column=1, sticky='ns')
        self.neuron_catalog_table.bind('<<TreeviewSelect>>',
                                       self._on_neuron_catalog_selected)
        self.neuron_catalog_table.bind('<Double-1>', self._load_catalog_row_event)
        actions = tk.Frame(window, bg=C['page'])
        actions.grid(row=4, column=0, columnspan=2, sticky='ew', padx=12, pady=8)
        source_row = tk.Frame(actions, bg=C['page'])
        source_row.pack(fill='x')
        button_row = tk.Frame(actions, bg=C['page'])
        button_row.pack(fill='x', pady=(6, 0))
        self.neuron_catalog_load_button = self._flat_button(
            source_row, "Refresh list", self.load_neuron_catalog, small=True)
        self.neuron_catalog_load_button.pack(side='left')
        self._configure_catalog_source_control(source_row)
        self._flat_button(
            button_row, "Load selected", self.load_selected_catalog_row,
            small=True).pack(side='left')
        self.neuron_catalog_export_button = self._flat_button(
            button_row, "Save CSV table", self.save_neuron_catalog_table,
            small=True, color='#eef6f6', active='#dcecee')
        self.neuron_catalog_export_button.configure(state='disabled')
        self.neuron_catalog_export_button.pack(side='left', padx=(8, 0))
        self._flat_button(
            button_row, "Close", self._close_neuron_catalog,
            small=True).pack(side='right')
        window.protocol("WM_DELETE_WINDOW", self._close_neuron_catalog)
        window.update_idletasks()
        width, height, x, y = self._catalog_geometry(
            window.winfo_reqwidth(), window.winfo_reqheight())
        window.minsize(min(self._px(460), width), min(self._px(420), height))
        window.geometry(f"{width}x{height}{x:+d}{y:+d}")
        window.deiconify()

        if (self._catalog_sample_id == self.sample_id.get().strip()
                and self._catalog_snapshot is not None
                and IT.catalog_snapshot_unchanged(self._catalog_snapshot)):
            side_result = (
                self._catalog_side_result
                if self._catalog_side_snapshot_id == self._catalog_snapshot.get("snapshot_id")
                else None)
            self._populate_neuron_catalog(
                self._catalog_snapshot, side_result=side_result,
                side_state="complete" if side_result is not None else "checking")
            if side_result is not None:
                self._catalog_side_result = side_result
                self._catalog_side_state = "complete"
                if self.neuron_catalog_export_button is not None:
                    self.neuron_catalog_export_button.configure(state='normal')
            else:
                self._start_catalog_side_load(self._catalog_snapshot)
        else:
            self.load_neuron_catalog()

    def _configure_catalog_source_control(self, parent):
        """Offer a source selector only when both live and dated sources exist."""
        try:
            from .config import load as load_config
            config = load_config(self.config_path)
            catalog = (config.get("sources") or {}).get("neuron_catalog") or {}
        except Exception:
            catalog = {}
        mode = str(catalog.get("mode") or "").strip().lower()
        has_snapshot = bool(catalog.get("snapshot_path")) if mode == "live-iondata" else bool(catalog.get("path"))
        # A configured CSV catalog remains the default, but the operator may
        # explicitly request the intranet API. This is never an automatic fallback.
        has_live = mode == "live-iondata" or bool(catalog)
        choices = {}
        if has_live:
            choices["Live IONData"] = "live-iondata"
        if has_snapshot:
            choices["Dated CSV snapshot"] = "csv"
        if not choices:
            choices["Configured source"] = None
        self._catalog_source_choices = choices
        configured = mode if mode in {"live-iondata", "csv"} else next(iter(choices.values()))
        if configured not in choices.values():
            configured = next(iter(choices.values()))
        self._catalog_source = configured
        if len(choices) > 1:
            self._catalog_source_var = tk.StringVar(
                parent, value=next(label for label, source in choices.items()
                                   if source == configured))
            ttk.Label(parent, text="Source:").pack(side="left", padx=(14, 4))
            selector = ttk.Combobox(
                parent, textvariable=self._catalog_source_var,
                values=tuple(choices), state="readonly", width=20)
            selector.pack(side="left", padx=(0, 8))
            selector.bind("<<ComboboxSelected>>", self._on_catalog_source_changed)
        else:
            label = next(iter(choices))
            ttk.Label(parent, text=f"Source: {label}").pack(side="left", padx=(14, 8))

    def _on_catalog_source_changed(self, _event=None):
        label = self._catalog_source_var.get() if self._catalog_source_var is not None else ""
        self._catalog_source = self._catalog_source_choices.get(label)
        self.load_neuron_catalog()

    def _close_neuron_catalog(self):
        window = self._neuron_catalog_window
        if window is None:
            return
        if getattr(self, "_catalog_reload_after", None) is not None:
            try:
                self.root.after_cancel(self._catalog_reload_after)
            except Exception:
                pass
            self._catalog_reload_after = None
        if getattr(self, "_catalog_filter_after", None) is not None:
            try:
                self.root.after_cancel(self._catalog_filter_after)
            except Exception:
                pass
            self._catalog_filter_after = None
        self._catalog_request_id += 1
        self._catalog_side_request_id = getattr(
            self, "_catalog_side_request_id", 0) + 1
        self._neuron_catalog_window = None
        self.neuron_catalog_table = None
        self.neuron_catalog_load_button = None
        self.neuron_catalog_export_button = None
        try:
            window.destroy()
        except tk.TclError:
            pass

    def load_neuron_catalog(self):
        """Load the selected live or dated neuron list in a worker thread."""
        sample_id = self.sample_id.get().strip()
        if not sample_id:
            self.neuron_catalog_info.set("Enter a sample ID before loading its neuron list.")
            return
        if self._neuron_catalog_window is None or not self._neuron_catalog_window.winfo_exists():
            return
        if self.neuron_catalog_table is None:
            return
        self._catalog_request_id += 1
        self._catalog_side_request_id += 1
        request_id = self._catalog_request_id
        requested_source = self._catalog_source
        self._log_operation(
            "Neuron catalog load", "start", sample=sample_id,
            source=requested_source, config=self.config_path)
        self._catalog_sample_id = None
        self._catalog_snapshot = None
        self._catalog_side_snapshot_id = None
        self._catalog_side_result = None
        self._catalog_side_state = "loading_catalog"
        self._catalog_rows_by_iid.clear()
        for item in self.neuron_catalog_table.get_children():
            self.neuron_catalog_table.delete(item)
        self.neuron_catalog_title.set(f"Loading neuron catalog · sample {sample_id}")
        self.neuron_catalog_side_summary.set("Side: waiting for catalog")
        self.neuron_catalog_info.set("Reading the selected neuron source…")
        self.neuron_catalog_load_button.configure(state='disabled')
        if self.neuron_catalog_export_button is not None:
            self.neuron_catalog_export_button.configure(state='disabled')

        def worker():
            try:
                from .config import load as load_config
                result = IT.list_neurons(
                    sample_id, config=load_config(self.config_path),
                    source=requested_source)
                error = None
            except Exception as exc:
                result, error = None, str(exc)
            self.root.after(0, lambda: self._apply_neuron_catalog(
                request_id, sample_id, result, error))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_neuron_catalog(self, request_id, sample_id, result, error):
        window = self._neuron_catalog_window
        if request_id != self._catalog_request_id:
            return
        if (window is None or not window.winfo_exists()
                or not IT.catalog_matches_sample(sample_id, self.sample_id.get())):
            self.update_status(f"Discarded stale neuron list for sample {sample_id}")
            return
        self.neuron_catalog_load_button.configure(state='normal')
        if error:
            self._log_operation(
                "Neuron catalog load", "failed", sample=sample_id,
                source=self._catalog_source, error=error)
            self._catalog_sample_id = None
            self._catalog_snapshot = None
            self._catalog_side_snapshot_id = None
            self._catalog_side_result = None
            self._catalog_side_state = "idle"
            self._catalog_rows_by_iid.clear()
            if self.neuron_catalog_export_button is not None:
                self.neuron_catalog_export_button.configure(state='disabled')
            for item in self.neuron_catalog_table.get_children():
                self.neuron_catalog_table.delete(item)
            self.neuron_catalog_title.set("Neuron catalog unavailable")
            self.neuron_catalog_side_summary.set("")
            self.neuron_catalog_info.set(f"Could not load neuron list: {error}")
            self._update_neuron_catalog_region_values(())
            self.update_status("Neuron list unavailable; check the selected source and network")
            return
        self._catalog_sample_id = sample_id
        self._catalog_snapshot = result
        self._log_operation(
            "Neuron catalog load", "finished", sample=sample_id,
            source=self._catalog_source, rows=result.get("count"),
            sha256=result.get("sha256"))
        self._populate_neuron_catalog(result, side_state="checking")
        self._start_catalog_side_load(result)
        source_label = "live IONData" if result.get('source_kind') == 'live-iondata' else "dated snapshot"
        self.update_status(f"Loaded {result['count']} neuron IDs from {source_label} for {sample_id}")

    def _populate_neuron_catalog(self, result, *, side_result=None,
                                 side_state="checking"):
        self._catalog_view_side_result = side_result
        self._catalog_view_side_state = side_state
        self._update_neuron_catalog_region_values(result.get("rows") or ())
        self._catalog_rows_by_iid.clear()
        for item in self.neuron_catalog_table.get_children():
            self.neuron_catalog_table.delete(item)
        self._render_neuron_catalog_rows(result)
        monkey = result.get("monkey_id")
        if not monkey:
            try:
                from .config import load as load_config
                monkey = (load_config(self.config_path).get("samples", {})
                          .get(str(result["sample_id"]), {}).get("monkey"))
            except Exception:
                monkey = None
        monkey = monkey or "unmapped"
        if side_result is not None:
            counts = side_result.get("counts") or {}
            side_summary = (
                f"Side: Left {counts.get('Left', 0)} · "
                f"Right {counts.get('Right', 0)} · "
                f"Unknown {counts.get('Unknown', 0)}")
            side_method = (side_result.get("source") or {}).get("method") or "unavailable"
            side_line = side_method
        elif side_state in {"checking", "loading"}:
            side_summary = "Side: checking…"
            side_line = "Loading sides via IONData soma + NMT atlas"
        else:
            side_summary = "Side: not loaded"
            side_line = "No side result"
        self.neuron_catalog_side_summary.set(side_summary)
        if result.get('source_kind') == 'live-iondata':
            self.neuron_catalog_title.set(
                f"Live IONData · sample {result['sample_id']} · monkey {monkey} · "
                f"{result['count']} neurons")
            self.neuron_catalog_info.set(
                f"{side_line} · fetched {result.get('fetched_at', 'time unknown')}\n"
                f"SHA-256 {result['sha256']}")
        else:
            self.neuron_catalog_title.set(
                f"Dated snapshot {result.get('source_date') or 'unknown'} · "
                f"sample {result['sample_id']} · monkey {monkey} · {result['count']} neurons")
            self.neuron_catalog_info.set(
                f"{side_line} · SHA-256 {result['sha256']}")

    @staticmethod
    def _catalog_side_value(row, side_result, side_state):
        side_results = (side_result or {}).get("results") or {}
        side_record = side_results.get(row["neuron_id"]) or {}
        if side_record.get("status") == "verified":
            side = side_record.get("side") or "Unknown"
            return side, f"side-{side.lower()}"
        if side_state in {"checking", "loading"}:
            return "Checking", "side-checking"
        return "Unknown", "side-unknown"

    @staticmethod
    def _catalog_neuron_sort_key(neuron_id):
        return tuple(
            int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", str(neuron_id)))

    @staticmethod
    def _catalog_region_values(rows):
        regions = {
            str(row.get("portal_region") or "Unassigned")
            for row in rows
        }
        return (
            CATALOG_ALL_REGIONS,
            *sorted(regions, key=str.casefold),
        )

    def _update_neuron_catalog_region_values(self, rows):
        selector = getattr(self, "_catalog_region_selector", None)
        values = self._catalog_region_values(rows)
        if selector is not None:
            selector.configure(values=values)
        variable = getattr(self, "_catalog_region_filter_var", None)
        if variable is not None and variable.get() not in values:
            variable.set(CATALOG_ALL_REGIONS)

    def _catalog_filtered_rows(self, rows):
        filter_variable = getattr(self, "_catalog_filter_var", None)
        filter_text = filter_variable.get() if filter_variable is not None else ""
        region_variable = getattr(self, "_catalog_region_filter_var", None)
        region_filter = (
            region_variable.get().strip()
            if region_variable is not None else CATALOG_ALL_REGIONS)
        terms = [term for term in filter_text.lower().split()
                 if term]
        visible = []
        for index, row in enumerate(rows):
            side, _tag = self._catalog_side_value(
                row, self._catalog_view_side_result,
                self._catalog_view_side_state)
            region = row.get("portal_region") or "Unassigned"
            if (region_filter
                    and region_filter != CATALOG_ALL_REGIONS
                    and region != region_filter):
                continue
            searchable = " ".join((
                side, row.get("neuron_id", ""), region)).lower()
            if all(term in searchable for term in terms):
                visible.append((index, row, side, region))
        column = getattr(self, "_catalog_sort_column", None)
        if column is not None:
            positions = {'side': 2, 'neuron_id': 1, 'portal_region': 3}
            position = positions[column]
            if column == 'neuron_id':
                key = lambda entry: (
                    self._catalog_neuron_sort_key(entry[1].get('neuron_id', '')),
                    entry[0])
            elif column == 'side':
                ranks = {'Left': 0, 'Right': 1, 'Unknown': 2, 'Checking': 3}
                key = lambda entry: (ranks.get(entry[2], 9), entry[0])
            else:
                key = lambda entry: (str(entry[position]).lower(), entry[0])
            visible.sort(
                key=key, reverse=getattr(self, "_catalog_sort_reverse", False))
        return visible

    def _render_neuron_catalog_rows(self, result=None):
        table = getattr(self, "neuron_catalog_table", None)
        if table is None:
            return
        source = result if result is not None else getattr(
            self, "_catalog_snapshot", None)
        rows = (source or {}).get("rows") or []
        visible = self._catalog_filtered_rows(rows)
        children = list(table.get_children())
        filter_variable = getattr(self, "_catalog_filter_var", None)
        region_variable = getattr(self, "_catalog_region_filter_var", None)
        region_filter = (
            region_variable.get().strip()
            if region_variable is not None else CATALOG_ALL_REGIONS)
        filters_active = (
            bool(filter_variable.get().strip()
                 if filter_variable is not None else "")
            or (
                bool(region_filter)
                and region_filter != CATALOG_ALL_REGIONS
            ))
        in_place = (
            not filters_active and getattr(
                self, "_catalog_sort_column", None) is None
            and len(children) == len(visible))
        if not in_place:
            for item in children:
                table.delete(item)
            children = []
        else:
            self._catalog_rows_by_iid.clear()
        for position, (index, row, side, region) in enumerate(visible):
            iid = f"neuron-{index}"
            self._catalog_rows_by_iid[iid] = row
            _side, tag = self._catalog_side_value(
                row, self._catalog_view_side_result,
                self._catalog_view_side_state)
            if in_place and children[position] == iid:
                table.item(
                    iid, values=(side, row["neuron_id"], region), tags=(tag,))
            else:
                if in_place:
                    table.delete(children[position])
                table.insert(
                    '', 'end', iid=iid, values=(side, row["neuron_id"], region),
                    tags=(tag,))
        variable = getattr(self, "neuron_catalog_visible_count", None)
        if variable is not None:
            variable.set(f"Showing {len(visible)} / {len(rows)}")
        self._update_neuron_catalog_headings()

    def _update_neuron_catalog_headings(self):
        table = getattr(self, "neuron_catalog_table", None)
        if table is None or not callable(getattr(table, "heading", None)):
            return
        labels = {'side': 'Side', 'neuron_id': 'SWC ID',
                  'portal_region': 'Ion_NMT_region'}
        for column, label in labels.items():
            suffix = ""
            if getattr(self, "_catalog_sort_column", None) == column:
                suffix = " ↓" if getattr(
                    self, "_catalog_sort_reverse", False) else " ↑"
            table.heading(column, text=f"{label}{suffix}")

    def _schedule_neuron_catalog_filter(self, *_args):
        if getattr(self, "_catalog_filter_after", None) is not None:
            try:
                self.root.after_cancel(self._catalog_filter_after)
            except Exception:
                pass
        self._catalog_filter_after = self.root.after(
            120, self._apply_neuron_catalog_filter)

    def _apply_neuron_catalog_filter(self):
        self._catalog_filter_after = None
        if (getattr(self, "_neuron_catalog_window", None) is not None
                and getattr(self, "_catalog_snapshot", None) is not None):
            self._render_neuron_catalog_rows(self._catalog_snapshot)

    def _sort_neuron_catalog(self, column):
        if column not in {'side', 'neuron_id', 'portal_region'}:
            return
        if self._catalog_sort_column == column:
            self._catalog_sort_reverse = not self._catalog_sort_reverse
        else:
            self._catalog_sort_column = column
            self._catalog_sort_reverse = False
        self._apply_neuron_catalog_filter()

    def _start_catalog_side_load(self, snapshot):
        """Load all visible sides through VisPa's shared side mechanism."""
        if not snapshot or not snapshot.get("rows"):
            self._catalog_side_result = {
                "status": "complete", "results": {},
                "counts": {"Left": 0, "Right": 0, "Unknown": 0},
                "source": {"method": "empty_catalog"},
            }
            self._catalog_side_snapshot_id = snapshot.get("snapshot_id") if snapshot else None
            self._catalog_side_state = "complete"
            return
        self._catalog_side_request_id += 1
        request_id = self._catalog_side_request_id
        sample_id = snapshot["sample_id"]
        snapshot_id = snapshot.get("snapshot_id")
        self._catalog_side_snapshot_id = snapshot_id
        self._catalog_side_result = None
        self._catalog_side_state = "checking"
        if self.neuron_catalog_export_button is not None:
            self.neuron_catalog_export_button.configure(state='disabled')
        neuron_ids = [row["neuron_id"] for row in snapshot.get("rows", ())]

        def worker():
            try:
                result = IT.acquire_neuron_sides(
                    sample_id, neuron_ids, self._side_config)
                error = None
            except Exception as exc:
                result, error = None, str(exc)
            self._ui_call(
                self._apply_catalog_side_load,
                request_id, sample_id, snapshot_id, result, error)

        threading.Thread(target=worker, name="vispa-catalog-sides", daemon=True).start()

    def _apply_catalog_side_load(self, request_id, sample_id, snapshot_id,
                                 result, error):
        window = self._neuron_catalog_window
        snapshot = self._catalog_snapshot
        if request_id != self._catalog_side_request_id:
            return
        if (window is None or not window.winfo_exists()
                or snapshot is None
                or not IT.catalog_matches_sample(sample_id, self.sample_id.get())
                or self._catalog_sample_id != sample_id
                or self._catalog_snapshot is None
                or self._catalog_snapshot.get("snapshot_id") != snapshot_id
                or not IT.catalog_snapshot_unchanged(snapshot)):
            return
        if error:
            result = {
                "status": "unavailable",
                "results": {},
                "counts": {"Left": 0, "Right": 0, "Unknown": snapshot["count"]},
                "source": {"method": "unavailable", "reason": error},
            }
        self._catalog_side_result = result
        self._catalog_side_snapshot_id = snapshot_id
        self._catalog_side_state = "complete"
        for neuron_id, side_record in (result.get("results") or {}).items():
            self._neuron_side_cache[(sample_id, neuron_id)] = side_record
        self._populate_neuron_catalog(
            snapshot, side_result=result, side_state="complete")
        if self.neuron_catalog_export_button is not None:
            self.neuron_catalog_export_button.configure(state='normal')
        self._update_neuron_status()
        counts = result.get("counts") or {}
        if result.get("status") == "unavailable":
            self.update_status("Side lookup unavailable; the neuron table can still be saved")
        else:
            self.update_status(
                f"Side lookup complete · Left {counts.get('Left', 0)} · "
                f"Right {counts.get('Right', 0)} · Unknown {counts.get('Unknown', 0)}")

    def save_neuron_catalog_table(self):
        """Prompt for a CSV destination and save the current catalog record."""
        snapshot = self._catalog_snapshot
        side_result = self._catalog_side_result
        sample_id = self._catalog_sample_id
        if snapshot is None or side_result is None or sample_id is None:
            self.update_status("Load the neuron list and finish side lookup before saving")
            return
        if (not IT.catalog_matches_sample(sample_id, self.sample_id.get())
                or not IT.catalog_snapshot_unchanged(snapshot)):
            self.update_status("The current neuron table is stale; reload it before saving")
            return
        monkey = (snapshot.get("monkey_id") or "").strip()
        if not monkey:
            try:
                from .config import load as load_config
                monkey = (load_config(self.config_path).get("samples", {})
                          .get(sample_id, {}).get("monkey") or "")
            except Exception:
                monkey = ""
        default_folder = Path(
            getattr(self, "output_root", "") or self._configured_output_root()
        ) / "table" / "ion_neuronlists"
        try:
            default_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.update_status(f"Could not prepare default table folder: {exc}")
            return
        default_name = IT.neuron_catalog_table_filename(
            snapshot, monkey or "unmapped")
        chosen = filedialog.asksaveasfilename(
            parent=self._neuron_catalog_window or self.root,
            title="Save neuron catalog table",
            initialdir=str(default_folder),
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=(("CSV table", "*.csv"), ("All files", "*.*")))
        if not chosen:
            self.update_status("Neuron table save cancelled")
            return
        try:
            result = IT.write_neuron_catalog_table(
                snapshot, side_result, Path(chosen).parent,
                monkey or "unmapped", output_path=chosen)
        except Exception as exc:
            self.update_status(f"Could not save the neuron table: {exc}")
            self._append_log(f"Neuron table save failed: {exc}")
            return
        self.update_status(
            f"Saved {result['row_count']} neuron records to {result['path']}")
        self._append_log(
            f"Neuron table saved: {result['path']} · SHA-256 {result['sha256']}")
        self.neuron_catalog_info.set(f"Saved record · {result['path']}")

    def _on_template_brain_view(self):
        """Pass current identity and catalog region to the audited OpenGL hook."""
        sample_id = self.sample_id.get().strip()
        neuron_id = self.neuron_id.get().strip()
        if not sample_id or not neuron_id:
            self.update_status("Enter a sample and neuron ID before opening the template view")
            return
        portal_region = self._current_portal_region(sample_id, neuron_id)
        self.launch_template_brain_view(sample_id, neuron_id, portal_region)

    def _current_portal_region(self, sample_id, neuron_id):
        """Return the current cached catalog region when its snapshot is valid."""
        if sample_id != self.sample_id.get().strip():
            return ""
        snapshot = self._catalog_snapshot
        if self._catalog_sample_id == sample_id and snapshot is not None:
            if not IT.catalog_snapshot_unchanged(snapshot):
                return ""
            return next((
                row["portal_region"] for row in self._catalog_rows_by_iid.values()
                if row["neuron_id"] == neuron_id), "")
        snapshot = getattr(self, "_portal_region_snapshots", {}).get(sample_id)
        if snapshot is None or not IT.catalog_snapshot_unchanged(snapshot):
            return ""
        return self._portal_region_cache.get(sample_id, {}).get(neuron_id, "")

    def _on_fnt_tracer(self):
        """Run the borrowed legacy FNT-tools sequence in the background."""
        sample_id = self.sample_id.get().strip()
        neuron_id = self.neuron_id.get().strip()
        if not sample_id or not neuron_id:
            self.update_status("Enter a sample and neuron ID before opening fnt-tracer")
            return
        self._log_operation(
            "FNT tools", "requested", sample=sample_id, neuron=neuron_id,
            config=self.config_path)
        self.update_status(f"Running FNT tools for {sample_id}/{neuron_id}…")

        def worker():
            try:
                from .config import load
                from .fnt import swc_fnt_tracer
                configuration = load(self.config_path)
                result = swc_fnt_tracer(configuration, sample_id, neuron_id)
            except Exception as exc:
                self._ui_call(messagebox.showerror, 'fnt-tracer', f'Could not start fnt-tracer:\n{exc}')
                self._log_operation(
                    "FNT tools", "failed", sample=sample_id, neuron=neuron_id,
                    error=exc)
            else:
                self._ui_call(self.update_status, f"fnt-tracer process started: {sample_id}/{neuron_id}; pixels unverified")
                self._log_operation(
                    "FNT tools", "started", command=result.get("command"),
                    pid=result.get("pid"), project=result.get("project_path"),
                    converter=result.get("converter"),
                    tracer_log=result.get("log_path"),
                    receipt=result.get("receipt_path"),
                    pixels="unverified")

        threading.Thread(target=worker, name='vispa-fnt-tools', daemon=True).start()

    def _on_fnt_setup(self):
        """Open the FNT section for the optional fnt-tracer program."""
        self._open_config_yaml(section='FNT')

    def _on_bulk_review(self):
        """Open the receipt-backed whole-animal review operator."""
        try:
            from .review_bulk_dialog import BulkReviewDialog
            BulkReviewDialog(self.root, sample=self.sample_id.get().strip(),
                             config_path=self.config_path, log=self._log_operation)
        except (OSError, ValueError, KeyError) as exc:
            self._log_operation("Bulk review", "failed", error=exc)
            messagebox.showerror("Bulk review", str(exc), parent=self.root)

    def launch_template_brain_view(self, sample_id: str, neuron_id: str,
                                   portal_region: str = ""):
        """Start the independently configured original OpenGL viewer process."""
        self._log_operation(
            "SWC Brain View interactive", "requested",
            sample=sample_id, neuron=neuron_id, region=portal_region,
            config=self.config_path)
        try:
            from .renderers.swc_brain_view import launch_configured_view
            process = launch_configured_view(
                sample_id, neuron_id, portal_region=portal_region,
                config_path=self.config_path)
        except Exception as exc:
            self.update_status(f"Could not launch template brain view: {exc}")
            self._log_operation(
                "SWC Brain View interactive", "failed", error=exc)
            return None
        self.update_status(f"Template brain view started for {sample_id}/{neuron_id}")
        plan = getattr(process, "vispa_plan", {}) or {}
        self._log_operation(
            "SWC Brain View interactive", "started",
            command=plan.get("worker_entry"), pid=getattr(process, "pid", None),
            config=plan.get("config_path"),
            mesh=(plan.get("mesh") or {}).get("path"),
            processed_swc=(plan.get("processed_swc") or {}).get("path"),
            sample=sample_id, neuron=neuron_id)
        resolution = plan.get("region_resolution", {})
        if resolution.get("status") == "selected":
            self._append_log(
                f"Region overlay selected: {getattr(process, 'vispa_plan')['region_mesh']['filename']}")
            self.update_status(
                f"Template brain view started · {getattr(process, 'vispa_plan')['region_mesh']['legend_label']}")
        elif portal_region:
            self._append_log(f"Region overlay omitted: {resolution.get('reason', 'no unique match')}")
            self.update_status("Template brain view started · soma region unavailable")

        def drain_process():
            stream = getattr(process, "stdout", None)
            if stream is not None:
                try:
                    for line in stream:
                        line = line.rstrip()
                        if line:
                            self._log_queue.put(line)
                except Exception as exc:
                    self._log_queue.put(f"Template brain view output error: {exc}")
            try:
                return_code = process.wait()
            except Exception as exc:
                self._log_queue.put(f"Template brain view monitor error: {exc}")
                return
            self._ui_call(
                self.update_status,
                f"Template brain view exited with code {return_code} for {sample_id}/{neuron_id}")

        threading.Thread(target=drain_process, daemon=True).start()
        return process

    def _on_neuron_catalog_selected(self, _event=None):
        sample_id = self._catalog_sample_id
        if (sample_id is None
                or not IT.catalog_matches_sample(sample_id, self.sample_id.get())):
            return
        # A queued Treeview event can arrive after WM_DELETE_WINDOW destroyed the
        # dialog. Do not inspect Tk widgets once the dialog has been closed.
        if self.neuron_catalog_table is None:
            return
        if (self._catalog_snapshot is None
                or not IT.catalog_snapshot_unchanged(self._catalog_snapshot)):
            self._catalog_sample_id = None
            self._catalog_snapshot = None
            self._catalog_rows_by_iid.clear()
            for item in self.neuron_catalog_table.get_children():
                self.neuron_catalog_table.delete(item)
            self.neuron_catalog_info.set("Portal snapshot changed; reload the neuron list before selecting.")
            return
        selected = self.neuron_catalog_table.selection()
        if not selected:
            return
        row = self._catalog_rows_by_iid.get(selected[0])
        if row is not None:
            selected_id = IT.catalog_selection_id(
                sample_id, self.sample_id.get(), self._catalog_snapshot, row)
            if selected_id is not None:
                # This is identity selection only; it does not load coordinates or render.
                self.neuron_id.set(selected_id)

    def load_selected_catalog_row(self):
        """Load the selected portal row through the normal identity path."""
        table = self.neuron_catalog_table
        if table is None:
            return
        selected = table.selection()
        if not selected:
            self.update_status("Select a portal neuron row to load")
            return
        row = self._catalog_rows_by_iid.get(selected[0])
        if row is None or self._catalog_snapshot is None:
            return
        selected_id = IT.catalog_selection_id(
            self._catalog_sample_id, self.sample_id.get(), self._catalog_snapshot, row)
        if selected_id is None:
            self.update_status("Catalog selection is stale; refresh the neuron list")
            return
        self.neuron_id.set(selected_id)
        if self.sample_id.get().strip():
            self.load_and_autofill()

    def _load_catalog_row_event(self, event=None):
        table = self.neuron_catalog_table
        if table is None:
            return
        if event is not None:
            row = table.identify_row(event.y)
            if row:
                table.selection_set(row)
        self.load_selected_catalog_row()

    def _refresh_portal_region(self):
        """Resolve the configured catalog region for the current neuron."""
        sample = self.sample_id.get().strip()
        neuron = self.neuron_id.get().strip()
        if not sample or not neuron:
            self._update_neuron_status()
            return
        mapping = self._portal_region_cache.get(sample)
        if mapping is not None:
            self._apply_portal_region(neuron, mapping)
            return
        self._update_neuron_status()

        def worker():
            try:
                from .config import load
                result = IT.list_neurons(sample, load(self.config_path))
                mapping = {
                    str(row["neuron_id"]): (row.get("portal_region") or "Unassigned")
                    for row in result["rows"]}
            except Exception as exc:
                self._ui_call(self._set_region_lookup_error, sample, neuron, str(exc))
                return
            self._ui_call(self._store_portal_regions, sample, mapping, result)

        threading.Thread(target=worker, daemon=True).start()

    def _store_portal_regions(self, sample, mapping, snapshot):
        self._portal_region_cache[sample] = mapping
        self._portal_region_snapshots[sample] = snapshot
        if self.sample_id.get().strip() == sample:
            self._apply_portal_region(self.neuron_id.get().strip(), mapping)

    def _apply_portal_region(self, neuron, mapping):
        self._update_neuron_status()

    def _set_neuron_status(self, message):
        variable = getattr(self, "neuron_status_var", None)
        if variable is not None:
            variable.set(message)

    def _set_region_status(self, message):
        variable = getattr(self, "region_status_var", None)
        if variable is not None:
            variable.set(message)

    def _set_region_lookup_error(self, sample, neuron, detail):
        if (self.sample_id.get().strip(), self.neuron_id.get().strip()) == (sample, neuron):
            self._set_region_status(f"Region: unavailable ({detail})")

    def _refresh_neuron_side(self):
        """Acquire exact-neuron side off the UI thread."""
        sample = self.sample_id.get().strip()
        neuron = self.neuron_id.get().strip()
        identity = (sample, neuron)
        self._update_nmt_coordinate_display()
        if (not sample or not neuron or identity in self._neuron_side_cache
                or identity in self._neuron_side_pending):
            return
        self._neuron_side_pending.add(identity)
        self._update_nmt_coordinate_display()

        def worker():
            try:
                from .data_input_adaptor import acquire_neuron_side
                result = acquire_neuron_side(sample, neuron, self._side_config)
            except Exception as exc:
                result = {'status': 'unknown', 'side': None,
                          'reason': f'side acquisition failed: {exc}', 'source': None}
            self._ui_call(self._store_neuron_side, identity, result)

        threading.Thread(target=worker, daemon=True).start()

    def _store_neuron_side(self, identity, result):
        self._neuron_side_pending.discard(identity)
        self._neuron_side_cache[identity] = result
        if (self.sample_id.get().strip(), self.neuron_id.get().strip()) != identity:
            return
        if result.get('status') == 'verified':
            source = result.get('source') or {}
            self._append_log(
                f"Neuron side {result['side']} via {source.get('method') or 'declared source'}: "
                f"{source.get('atlas_region') or source.get('soma_region') or 'region unavailable'} "
                f"({Path(str(source.get('atlas_path') or source.get('path') or '')).name})")
        self._update_neuron_status()

    def _update_nmt_coordinate_display(self):
        """Show the atlas voxel already resolved by VisPa's side lookup."""
        variables = tuple(getattr(self, name, None)
                          for name in ("nmt_x", "nmt_y", "nmt_z"))
        if any(variable is None for variable in variables):
            return
        sample_id = self.sample_id.get().strip()
        neuron_id = self.neuron_id.get().strip()
        identity = (sample_id, neuron_id)
        result = getattr(self, "_neuron_side_cache", {}).get(identity) or {}
        source = result.get("source") or {}
        voxel = source.get("atlas_voxel")
        if result.get("status") == "verified" and isinstance(voxel, (list, tuple)) and len(voxel) == 3:
            values = tuple(str(int(value)) for value in voxel)
        elif identity in getattr(self, "_neuron_side_pending", set()):
            values = ("…", "…", "…")
        else:
            values = ("—", "—", "—")
        for variable, value in zip(variables, values):
            variable.set(value)

    def _update_neuron_status(self):
        """Keep neuron lookup and region boxes current for the selected identity."""
        sample = self.sample_id.get().strip()
        neuron = self.neuron_id.get().strip()
        self._update_nmt_coordinate_display()
        if not sample or not neuron:
            self._set_neuron_status("Neuron status: not loaded")
            self._set_region_status("Region: unavailable")
            return
        mapping = self._portal_region_cache.get(sample) or {}
        region = mapping.get(neuron)
        side_result = getattr(self, '_neuron_side_cache', {}).get((sample, neuron)) or {}
        verified_side = (side_result.get('side') if
                         side_result.get('status') == 'verified' else None)
        state = getattr(self, "_neuron_lookup_state", "idle")
        self._set_region_status(
            (f"Region: {verified_side} {region}" if verified_side else
             f"Region: {region} · side unverified") if region else
            "Region: unavailable" if state == "not_found" else "Region: checking")
        if state == "found":
            cache_status = getattr(self, '_cache_status', '')
            cache_state = (cache_status.partition(":")[2].strip()
                           if cache_status.startswith("cached:") else "")
            suffix = (" · cached" if cache_state and cache_state not in
                      {"none", "checking", "not checked"} else "")
            self._set_neuron_status(f"Neuron status: found{suffix}")
        elif state == "not_found":
            self._set_neuron_status("Neuron status: not found")
        elif state == "error":
            detail = getattr(self, "_neuron_lookup_error", None)
            self._set_neuron_status(f"Neuron status: lookup failed{(': ' + str(detail)) if detail else ''}")
        elif state in {"checking", "waiting"}:
            self._set_neuron_status(f"Neuron status: {'checking' if state == 'checking' else 'waiting to load'}")
        else:
            self._set_neuron_status("Neuron status: not loaded")

    def _refresh_dataset_sources(self):
        sample = self.sample_id.get().strip() or 'sample'
        self.soma_source.set(
            "0.65 µm CH1 cubes · cached or fetched online · VisPa download cache")
        try:
            from .config import sample as sample_entry
            entry = sample_entry(sample) or {}
            resample = entry.get('resample_5um')
        except Exception:
            resample = None
        if resample:
            tail = "\\".join(Path(resample).parts[-2:])
            self.context_source.set(f"5 µm CH1 resample · …\\{tail}")
        else:
            self.context_source.set(
                "5 µm CH1 resample · not configured in the active VisPa settings")

    def _refresh_plot_state(self):
        """The soma NIfTI needs the Soma volume, so it follows the Soma plot tick."""
        enabled = bool(self.plot_soma.get())
        check = getattr(self, 'soma_nifti_check', None)
        if check is not None:
            check.configure(state='normal' if enabled else 'disabled',
                            fg=self.COLORS['text'] if enabled else self.COLORS['disabled'])

    def _preview_target_dir(self, request):
        """Where this run writes PNGs: the chosen folder, or a preview-only temp folder."""
        if request.save_outputs:
            return request.output_dir
        safe = lambda value: ''.join(ch if ch.isalnum() or ch in '-_.' else '_'
                                     for ch in value)
        target = os.path.join(tempfile.gettempdir(), 'visual_toolkit_preview',
                              f"{safe(request.sample_id)}_{safe(request.neuron_id)}")
        os.makedirs(target, exist_ok=True)
        return target

    @staticmethod
    def _panel_png(panel):
        return panel.get('output_png') if isinstance(panel, dict) else None

    @staticmethod
    def _panel_spec(panel):
        if not isinstance(panel, dict):
            return {}
        return {'fov_um': list(panel.get('fov_um') or []),
                'resolution_um': list(panel.get('resolution_um') or [])}

    @staticmethod
    def _soma_window_px(request):
        side = int(round(float(request.soma_cubes) * BLOCK_SIZE_PIXELS[0]))
        return (side, side)

    def _finish(self, request, paths, message, errors=None):
        if not identity_matches((request.sample_id, request.neuron_id),
                                self.sample_id.get(), self.neuron_id.get()):
            self.update_status(
                f"Render finished for {request.sample_id}/{request.neuron_id}; "
                "current selection kept in the preview.")
            return
        kept = [path for path in paths if path]
        self._ui_call(self._register_outputs, kept)
        self._cache_status = (
            f"cached: current ({len(kept)} figures)" if request.save_outputs and kept
            else "cached: preview only" if kept else "cached: none")
        self._update_neuron_status()
        folder = os.path.dirname(kept[0]) if kept else request.output_dir
        note = "" if request.save_outputs else "  ·  preview only (not saved)"
        if errors:
            summary = " · ".join(errors)
            for error in errors:
                self._append_log(f"Panel skipped: {error}")
            self.update_status(f"⚠️ {message}; skipped: {summary}")
            if not kept:
                self._show_render_failure(request, summary)
                self._ui_call(messagebox.showwarning, "Panel unavailable", summary)
            return
        self.update_status(f"✅ {message}{note}  ·  {folder}")

    def _begin_render_preview(self, request):
        """Make the active render visible without presenting a prior figure."""
        if getattr(self, 'preview_label', None) is None:
            return
        self.preview_files = {}
        self._ephemeral_images = {}
        self.current_preview = None
        self.current_role = None
        self._preview_photo = None
        after_id = getattr(self, '_preview_after', None)
        if after_id:
            self.root.after_cancel(after_id)
            self._preview_after = None
        self.preview_label.configure(image='', text='Rendering figures…\nPlease wait.')
        self.preview_caption.set(
            f"{request.sample_id}/{request.neuron_id} · rendering")
        self._refresh_preview_tabs()
        self.update_status(f"Rendering figures for {request.sample_id}/{request.neuron_id}…")

    def _show_render_failure(self, request, detail):
        if not identity_matches((request.sample_id, request.neuron_id),
                                self.sample_id.get(), self.neuron_id.get()):
            return
        self.preview_label.configure(image='', text=f'No figures rendered.\n{detail}')
        self.preview_caption.set(
            f"{request.sample_id}/{request.neuron_id} · render failed")

    @staticmethod
    def _friendly_error(exc):
        """Turn the known missing-source failures into an actionable sentence."""
        text = str(exc)
        if "registered cached raw SWC" in text or "Raw SWC is unavailable" in text:
            return ("no registered raw SWC for this sample yet — stage its SWC cache "
                    "or choose a sample that has one; the other panels still render")
        if "processed-DS" in text or "processed DS" in text:
            return "this sample has no registered processed-DS sagittal source"
        if "central low-resolution section" in text:
            return "no 5 µm section at this soma, so the Context panel is unavailable"
        return text

    def _refresh_sagittal_hint(self):
        """Show the DS00 file/direction and the Sagittal raw-SWC status."""
        label = getattr(self, 'sagittal_hint', None)
        if label is None:
            return
        sample = self.sample_id.get().strip()
        C = self.COLORS
        try:
            from .renderers.microscopy_panels import SAMPLE_PATHS
            entry = SAMPLE_PATHS.get(sample) or {}
            ds_path = entry.get('ds00_processed')
            ds_name = os.path.basename(str(ds_path)) if ds_path else None
            resolution = 'resolution unknown'
            if ds_name:
                size = re.search(r'(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)', ds_name)
                if size:
                    resolution = '×'.join(size.groups()) + ' µm'
            if not ds_path:
                ok, text = False, f"No DS00 source registered for {sample}"
            else:
                ok, text = True, (
                    f"DS00 processed volume · {resolution}\n"
                    f"File: {ds_name}")
        except Exception as exc:
            ok, text = False, f"Sagittal: source check failed ({exc})"
        label.configure(text=text, fg=C['muted'] if ok else '#b45309')

    def _register_outputs(self, paths):
        if getattr(self, 'preview_label', None) is None:
            return
        mapping = {}
        for path in paths or []:
            if not path or not os.path.isfile(path):
                continue
            name = os.path.basename(path)
            if name.endswith('_Soma_Plot.png'):
                role = 'Soma'
            elif name.endswith('_Context_Plot.png'):
                role = 'Context'
            elif name.endswith('_Sagittal_Plot.png'):
                role = 'Sagittal'
            elif 'TriPlot' in name or 'PairPlot' in name:
                role = 'TrioPlot'
            elif name.endswith('_3D_SWC.png'):
                role = 'SWC3D'
            else:
                continue
            mapping[role] = os.path.abspath(path)
        if not mapping:
            return
        # Preview-only panels land in the temp root: hold the image in memory and
        # remove the file, while saved panels stay on disk.
        temp_root = os.path.abspath(os.path.join(tempfile.gettempdir(),
                                                 'visual_toolkit_preview'))
        ephemeral = {role: path for role, path in mapping.items()
                     if os.path.abspath(path).startswith(temp_root + os.sep)}
        if ephemeral:
            self._ephemeral_images = getattr(self, '_ephemeral_images', {})
            for role, path in ephemeral.items():
                try:
                    if Image is not None:
                        with Image.open(path) as image:
                            self._ephemeral_images[role] = image.copy()
                except Exception:
                    pass
            for path in ephemeral.values():
                try:
                    os.remove(path)
                except OSError:
                    pass
            for folder in {os.path.dirname(path) for path in ephemeral.values()}:
                try:
                    if os.path.isdir(folder) and not os.listdir(folder):
                        os.rmdir(folder)
                except OSError:
                    pass
        self.preview_files.update(mapping)
        self._refresh_preview_tabs()
        for role in ('SWC3D', 'Soma', 'Context', 'Sagittal', 'TrioPlot'):
            if role in mapping:
                self._show_role(role)
                break

    def _show_role(self, role):
        path = getattr(self, 'preview_files', {}).get(role)
        if path:
            self.current_role = role
            self.show_preview(path, role=role)
        elif role == 'SWC3D':
            self._render_swc3d()

    def _render_swc3d(self):
        """Render the current processed SWC on the configured template mesh."""
        if self._operation_running:
            messagebox.showwarning("Busy", "A VisPa operation is already running.")
            return
        sample = self.sample_id.get().strip()
        neuron = self.neuron_id.get().strip()
        if not sample or not neuron:
            messagebox.showwarning("SWC Brain View", "Choose a sample and neuron first.")
            return
        portal_region = self._current_portal_region(sample, neuron)
        save = bool(self.save_outputs.get())
        folder = self.output_dir.get().strip()
        if not folder:
            folder = self._generate_default_path(sample)
            self.output_dir.set(folder)
        if save:
            os.makedirs(folder, exist_ok=True)
        else:
            folder = os.path.join(
                tempfile.gettempdir(), 'visual_toolkit_preview',
                ''.join(ch if ch.isalnum() or ch in '-_.' else '_'
                        for ch in f"{sample}_{neuron}"))
            os.makedirs(folder, exist_ok=True)
        snapshot = os.path.join(
            folder,
            f"{sample}_{neuron.removesuffix('.swc')}_{_stamp()}_{time.time_ns() % 1000000:06d}_3D_SWC.png")
        self.current_role = 'SWC3D'
        self.current_preview = None
        self._preview_photo = None
        if getattr(self, '_preview_after', None):
            self.root.after_cancel(self._preview_after)
            self._preview_after = None
        self.preview_label.configure(image='', text='Rendering SWC Brain View…')
        self.preview_caption.set(f'SWC Brain View · {sample}/{neuron} · rendering')
        self.update_status("SWC Brain View · rendering template mesh and trace…")
        self._log_operation(
            "SWC Brain View snapshot worker", "start",
            sample=sample, neuron=neuron, config=self.config_path,
            snapshot=snapshot, save=save)

        def worker():
            try:
                self._ui_call(self._show_progress)
                from .renderers.swc_brain_view import render_configured_snapshot
                receipt = render_configured_snapshot(
                    sample, neuron, snapshot,
                    portal_region=portal_region, config_path=self.config_path)
            except Exception as exc:
                self._ui_call(self._hide_progress)
                self._ui_call(self._show_swc3d_error, sample, neuron, str(exc))
                self._ui_call(messagebox.showerror, "SWC Brain View", f"Could not render:\n{exc}")
            else:
                self._ui_call(
                    self._finish_swc3d, sample, neuron, snapshot,
                    receipt.get("receipt"), save)
                resolution = receipt.get("region_resolution", {})
                if resolution.get("status") == "selected":
                    self._ui_call(
                        self._append_log,
                        f"Region overlay selected: {receipt['region_mesh']['filename']}")
                    self._ui_call(
                        self.update_status,
                        f"SWC Brain View rendered · {receipt['region_mesh']['legend_label']}")
                elif portal_region:
                    self._ui_call(
                        self._append_log,
                        f"Region overlay omitted: {resolution.get('reason', 'no unique match')}")
                    self._ui_call(
                        self.update_status,
                        "SWC Brain View rendered · soma region unavailable")

        self._launch_processing(worker)

    def _show_swc3d_error(self, sample, neuron, error):
        if identity_matches((sample, neuron), self.sample_id.get(), self.neuron_id.get()):
            self.preview_label.configure(image='', text=f'SWC Brain View failed:\n{error}')
            self.preview_caption.set(f'SWC Brain View · {sample}/{neuron} · failed')
        self.update_status(f'SWC Brain View failed: {error}')
        self._append_log(f'SWC Brain View failed for {sample}/{neuron}: {error}')

    def _finish_swc3d(self, sample, neuron, image_path, receipt_path, save):
        """Publish a completed SWC Brain View snapshot to the preview tab."""
        self._hide_progress()
        if not identity_matches(
                (sample, neuron), self.sample_id.get(), self.neuron_id.get()):
            for path in (image_path, receipt_path):
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            self.update_status("Discarded stale SWC Brain View result")
            return
        self._ephemeral_images = getattr(self, '_ephemeral_images', {})
        if not save and Image is not None:
            try:
                with Image.open(image_path) as image:
                    self._ephemeral_images['SWC3D'] = image.copy()
            except Exception:
                pass
        self.preview_files['SWC3D'] = os.path.abspath(image_path)
        self._refresh_preview_tabs()
        self._show_role('SWC3D')
        if not save:
            for path in (image_path, receipt_path):
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        self.update_status(f"SWC Brain View rendered for {sample}/{neuron}")
        self._append_log(f"SWC Brain View rendered: {image_path}")

    def show_preview(self, path, role=None):
        if getattr(self, 'preview_label', None) is None:
            return
        if Image is None:
            self.preview_label.configure(image='',
                                         text=f"{os.path.basename(path)}\n"
                                              "(Pillow not available for preview)")
            return
        ephemeral = (getattr(self, '_ephemeral_images', {}).get(role)
                     if role is not None else None)
        try:
            image = ephemeral.copy() if ephemeral is not None else Image.open(path)
        except Exception as exc:
            self.preview_label.configure(image='',
                                         text=f"Cannot display {os.path.basename(path)}\n{exc}")
            return
        width = max(220, self.preview_holder.winfo_width() - 20)
        height = max(220, self.preview_holder.winfo_height() - 20)
        try:
            image.thumbnail((width, height), Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
        except Exception as exc:
            self.preview_label.configure(image='',
                                         text=f"Cannot display {os.path.basename(path)}\n{exc}")
            return
        self._preview_photo = photo
        self.current_preview = os.path.abspath(path)
        self.current_role = role
        self.preview_label.configure(image=photo, text='')
        suffix = "  ·  preview only" if ephemeral is not None else ""
        self.preview_caption.set(f"{os.path.basename(path)}{suffix}")

    def _on_preview_resize(self, event):
        if not getattr(self, 'current_preview', None):
            return
        if getattr(self, '_preview_after', None):
            try:
                self.root.after_cancel(self._preview_after)
            except Exception:
                pass
        self._preview_after = self.root.after(
            150, lambda: self.show_preview(
                self.current_preview, role=self.current_role))

    def _refresh_preview_tabs(self):
        files = getattr(self, 'preview_files', {})
        for role, button in getattr(self, 'preview_buttons', {}).items():
            try:
                if not button.winfo_exists():
                    continue
                available = role in files or (
                    role == 'SWC3D'
                    and bool(self.sample_id.get().strip())
                    and bool(self.neuron_id.get().strip()))
                state = 'normal' if available else 'disabled'
                button.configure(state=state,
                                 fg=self.COLORS['text'] if state == 'normal'
                                 else self.COLORS['disabled'])
            except tk.TclError:
                # The window may be closing between the deferred reload and
                # this refresh; a destroyed tab needs no state update.
                continue

    RECEIPT_NAME = 'visual_gui_receipt.json'

    def _fingerprint(self):
        """Current identity + render settings, or None when coordinates are invalid."""
        try:
            xyz = [round(float(self.x_coord.get()), 3), round(float(self.y_coord.get()), 3),
                   round(float(self.z_coord.get()), 3)]
            cubes = float(self.soma_cubes.get() or REVIEW_SETTINGS['soma_window']['cubes_xy'])
            context = [int(float(self.width_um.get())), int(float(self.height_um.get())),
                       int(float(self.depth_um.get()))]
        except Exception:
            return None
        return {
            'style_schema': '1.12.0.dev2',
            'gui_sha256': self._file_sha256(Path(__file__)),
            'renderer_sha256': {
                name: self._file_sha256(Path(__file__).parent / 'renderers' / name)
                for name in ('microscopy_panels.py', 'brain_volume_montage.py')},
            'sample': self.sample_id.get().strip(),
            'neuron': self.neuron_id.get().strip(),
            'soma_xyz': xyz,
            'soma_cubes': round(cubes, 3),
            'context_um': context,
            'review_settings': json.loads(json.dumps(REVIEW_SETTINGS)),
            'effective_marker': {'crosshair_arm_px': REVIEW_SETTINGS['marker']['crosshair_px'],
                                 'box_mode': REVIEW_SETTINGS['marker']['box_mode'],
                                 'box_side_scale': TARGET_BOX_SIDE_SCALE},
        }

    @staticmethod
    def _fingerprint_key(fingerprint):
        return hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True).encode('utf-8')).hexdigest()

    @staticmethod
    def _file_sha256(path):
        digest = hashlib.sha256()
        with open(path, 'rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()

    def _write_receipt(self, folder, fingerprint, outputs, specs=None, trio_path=None,
                       review_session_path=None, review_session_source=None,
                       review_session_event_id=None):
        """Record what was rendered, with settings and file hashes, for cache checks."""
        path = os.path.join(folder, self.RECEIPT_NAME)
        try:
            data = json.load(open(path, encoding='utf-8')) if os.path.isfile(path) else {}
        except Exception:
            data = {}
        entries = data.get('entries') or {}
        files = {}
        folder_abs = os.path.abspath(folder)
        specs = specs or {}
        for role, png in dict(outputs or {}).items():
            if (png and os.path.isfile(png)
                    and os.path.abspath(png).startswith(folder_abs + os.sep)):
                item = {'path': os.path.abspath(png),
                        'sha256': self._file_sha256(png),
                        'bytes': os.path.getsize(png)}
                spec = specs.get(role) or {}
                if spec.get('fov_um'):
                    item['fov_um'] = spec['fov_um']
                if spec.get('resolution_um'):
                    item['resolution_um'] = spec['resolution_um']
                files[role] = item
        if (trio_path and os.path.isfile(trio_path)
                and os.path.abspath(trio_path).startswith(folder_abs + os.sep)):
            files['TrioPlot'] = {'path': os.path.abspath(trio_path),
                                 'sha256': self._file_sha256(trio_path),
                                 'bytes': os.path.getsize(trio_path)}
        neuron = fingerprint['neuron'].removesuffix('.swc')
        entries[neuron] = {
            'sample': fingerprint['sample'], 'neuron': neuron,
            'rendered_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'fingerprint': fingerprint,
            'key': self._fingerprint_key(fingerprint),
            'roles': sorted(files),
            'outputs': files,
        }
        if review_session_path:
            source = {
                'kind': 'review_session',
                'path': os.path.abspath(review_session_path),
                'sample_id': fingerprint['sample'],
                'neuron_id': fingerprint['neuron'],
            }
            if review_session_source:
                source['fnt'] = {
                    'kind': review_session_source[0],
                    'path': review_session_source[1],
                    'sha256': review_session_source[2],
                }
            if review_session_event_id:
                source['event_id'] = review_session_event_id
            entries[neuron]['source'] = source
        os.makedirs(folder, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump({'schema': 1, 'entries': entries}, stream, indent=2, ensure_ascii=False)

    def _read_receipt(self, folder, neuron):
        path = os.path.join(folder, self.RECEIPT_NAME)
        if not os.path.isfile(path):
            return None
        try:
            data = json.load(open(path, encoding='utf-8'))
        except Exception:
            return None
        entries = data.get('entries') or {}
        key = str(neuron).removesuffix('.swc')
        return entries.get(key) or entries.get(f"{key}.swc")

    def _evaluate_cached(self, entry, roles=None):
        """Three-stage cache check: coordinates, settings key, file hashes."""
        current = self._fingerprint()
        if current is None:
            return 'no_coords', ['coordinates are not filled in']
        cached = entry.get('fingerprint') or {}
        notes = []
        same_coords = cached.get('soma_xyz') == current['soma_xyz']
        settings_now = {k: v for k, v in current.items() if k != 'soma_xyz'}
        settings_then = {k: v for k, v in cached.items() if k != 'soma_xyz'}
        same_settings = settings_now == settings_then
        same_key = entry.get('key') == self._fingerprint_key(current)
        outputs = entry.get('outputs') or {}
        if roles is not None:
            outputs = {role: outputs[role] for role in outputs if role in roles}
        same_files = all(
            os.path.isfile(item.get('path', ''))
            and self._file_sha256(item['path']) == item.get('sha256')
            for item in outputs.values())
        if not same_coords:
            notes.append('coordinates changed')
        if not same_settings:
            notes.append('settings changed')
        if not same_files:
            notes.append('cached files changed or missing')
        return ('same' if (same_coords and same_settings and same_key and same_files)
                else 'differs'), notes

    def _find_cached_figures(self, sample, neuron):
        """Cached PNGs and receipt from one current or legacy neuron folder."""
        folders = []
        current = self.output_dir.get().strip()
        if current:
            folders.append(current)
        root = getattr(self, 'output_root', None) or self._configured_output_root()
        if os.path.isdir(root):
            candidates = [os.path.join(root, name) for name in os.listdir(root)
                          if name.startswith(f"{sample}_")
                          and os.path.isdir(os.path.join(root, name))]
            candidates.sort(key=os.path.getmtime, reverse=True)
            folders.extend(candidates[:8])
        found, receipt_entry = {}, None
        unverified = {}
        for folder in dict.fromkeys(folders):
            if not os.path.isdir(folder):
                continue
            entry = self._read_receipt(folder, neuron)
            candidate = {}
            for name in os.listdir(folder):
                if not (name.startswith(f"{sample}_{neuron}")
                        and name.lower().endswith('.png')):
                    continue
                if name.endswith('_Soma_Plot.png'):
                    role = 'Soma'
                elif name.endswith('_Context_Plot.png'):
                    role = 'Context'
                elif name.endswith('_Sagittal_Plot.png'):
                    role = 'Sagittal'
                elif 'TriPlot' in name or 'PairPlot' in name:
                    role = 'TrioPlot'
                else:
                    continue
                path = os.path.join(folder, name)
                if role not in candidate or os.path.getmtime(path) > os.path.getmtime(candidate[role]):
                    candidate[role] = path
            if entry and candidate:
                found, receipt_entry = candidate, entry
                break
            if candidate and not unverified:
                unverified = candidate
        if not found:
            found = unverified
        return folders, found, receipt_entry

    def _reload_existing(self, quiet=False, rerender_if_stale=True):
        """Update the preview from the newest cached rendering data."""
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return
        sample = self.sample_id.get().strip()
        neuron = self.neuron_id.get().strip().removesuffix('.swc')
        if not sample or not neuron:
            if not quiet:
                self.update_status("Choose a sample and neuron first")
            return
        self._activate_cached_figures(
            sample, neuron, quiet=quiet, start_fnt=not quiet,
            rerender_if_stale=rerender_if_stale)

    def _activate_cached_figures(self, sample, neuron, *, quiet=False,
                                 start_fnt=False, rerender_if_stale=False):
        """Load cached rendering data without prompting or re-rendering."""
        _folders, found, receipt_entry = self._find_cached_figures(sample, neuron)
        root = getattr(self, 'output_root', None) or self._configured_output_root()
        if not found:
            self._cache_status = "cached: none"
            self._update_neuron_status()
            if rerender_if_stale:
                self.update_status(
                    f"No cached rendering data for {sample}/{neuron}; rendering now.")
                self.run_selected(force_rerender=True)
                return False
            if not quiet:
                self.update_status(
                    f"No cached rendering data for {sample}/{neuron} under {root}")
            return False
        folder = os.path.dirname(next(iter(found.values())))
        state, notes = (self._evaluate_cached(receipt_entry) if receipt_entry
                        else ('no_receipt', ['no render receipt recorded']))
        if rerender_if_stale and state != 'same':
            self._cache_status = "cached: stale · rendering"
            self._update_neuron_status()
            self.update_status(
                "Cached figures do not match current coordinates/settings; "
                "updating from existing acquisition cache.")
            self.run_selected(force_rerender=True)
            return False
        self.preview_files.update(found)
        self._refresh_preview_tabs()
        for role in ('Soma', 'Context', 'Sagittal', 'TrioPlot'):
            if role in found:
                self._show_role(role)
                break
        state_label = {
            "same": "cached: current",
            "differs": "cached: stale",
            "no_receipt": "cached: unverified",
            "no_coords": "cached: coordinates unavailable",
        }.get(state, f"cached: {state}")
        self._cache_status = (
            f"{state_label} ({len(found)} figure{'s' if len(found) != 1 else ''})")
        self._update_neuron_status()
        note = "" if state == 'same' else f" · {', '.join(notes)}"
        self.update_status(
            f"Loaded cached rendering data from output {folder}{note}")
        if start_fnt:
            self._start_fnt_fetch(sample, neuron)
        return True

    def _start_fnt_fetch(self, sample, neuron):
        """Fetch a matching FNT in the background without delaying cached figures."""
        key = (sample, neuron)
        active = getattr(self, '_fnt_fetch_active', set())
        if key in active:
            return
        active.add(key)
        self._fnt_fetch_active = active

        def worker():
            try:
                self._fetch_fnt(sample, neuron)
            finally:
                self._ui_call(active.discard, key)
        threading.Thread(target=worker, name='vispa-fnt-fetch', daemon=True).start()

    def _fetch_fnt(self, sample, neuron):
        """Preflight the borrowed tools; only the FNT action fetches or converts."""
        try:
            from .config import load
            from .fnt import swc_fnt_tracer
            configuration = load(self.config_path)
            result = swc_fnt_tracer(configuration, sample, neuron, dry_run=True)
            self._ui_call(self._append_log, f"FNT tools {result['status']}: {sample}/{neuron} (launch not tested)")
        except Exception as exc:
            self._ui_call(self._append_log, f"FNT unavailable for {sample}/{neuron}: {exc}")

    def _open_output_folder(self):
        folder = self.output_dir.get().strip()
        self._log_operation(
            "Open output folder", "requested", path=folder)
        try:
            if not folder:
                folder = self._generate_default_path(self.sample_id.get())
                self.output_dir.set(folder)
            folder = os.path.abspath(folder)
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
            self.update_status(f"Opened output folder: {folder}")
            self._log_operation("Open output folder", "finished", path=folder)
        except Exception as exc:
            self.update_status(f"Could not open output folder: {folder}")
            self._log_operation(
                "Open output folder", "failed", path=folder, error=exc)
            messagebox.showerror("Open folder", f"Could not open {folder}:\n{exc}")

    def _open_config_yaml(self, section=None):
        import hashlib
        from .config import config_path, packaged_config_path
        from .config import FIELDS, parse_text, dump_text, field_value, apply_fields
        path = str(Path(self.config_path or config_path()).resolve())
        self._log_operation(
            "Settings editor", "requested", path=path,
            section=section or "current")
        raw_label = 'Raw JSON' if Path(path).suffix.lower() == '.json' else 'Raw YAML'
        window = getattr(self, '_config_window', None)
        if window is not None and window.winfo_exists():
            if section in {group for group, _, _, _ in FIELDS}:
                window._settings_section.set(section)
                window._settings_tabs.select(0)
            window.lift()
            window.focus_force()
            self._log_operation(
                "Settings editor", "focused", path=path,
                section=section or "current")
            return
        packaged_default = packaged_config_path().read_bytes()
        default_path = Path(path).with_name('vispa_config.default.yaml')
        default_warning = ''
        try:
            with default_path.open('xb') as stream:
                stream.write(packaged_default)
        except FileExistsError:
            pass
        except OSError as exc:
            default_warning = f'Local default copy unavailable ({exc}); showing installed profile.'
        try:
            default_content = default_path.read_text(encoding='utf-8')
            parse_text(default_content, default_path)
            default_source = str(default_path)
        except Exception as exc:
            default_content = packaged_default.decode('utf-8')
            default_source = 'Installed VisPa profile (local copy unavailable)'
            default_warning = f'Local default copy could not be used ({exc}); showing installed profile.'
        window = tk.Toplevel(self.root)
        self._config_window = window
        window.title(f"VisPa {__version__} settings — {Path(path).name}")
        window.geometry("920x700")
        window.configure(bg=self.COLORS['page'])
        header = tk.Frame(window, bg=self.COLORS['header'])
        header.pack(fill='x')
        tk.Label(header, text=f"VisPa {__version__} settings · active configuration", bg=self.COLORS['header'],
                 fg=self.COLORS['header_text'], font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=12, pady=(8, 0))
        tk.Label(header, text=path, bg=self.COLORS['header'],
                 fg=self.COLORS['header_text'], font=('Consolas', 9),
                 wraplength=880, justify='left').pack(anchor='w', padx=12, pady=(0, 8))
        tabs = ttk.Notebook(window)
        window._settings_tabs = tabs
        tabs.pack(fill='both', expand=True, padx=8, pady=8)
        form_outer = ttk.Frame(tabs)
        tabs.add(form_outer, text='Organized editor')
        section_names = tuple(dict.fromkeys(group for group, _, _, _ in FIELDS))
        editor_body = ttk.Frame(form_outer)
        editor_body.pack(fill='both', expand=True, padx=8, pady=8)
        section_bar = ttk.Frame(editor_body)
        section_bar.pack(side='left', fill='y', padx=(0, 8))
        ttk.Label(section_bar, text='Sections').pack(anchor='w', padx=4, pady=(2, 6))
        selected_section = tk.StringVar(value=section if section in section_names else section_names[0])
        window._settings_section = selected_section
        section_list = tk.Listbox(section_bar, exportselection=False, width=19,
                                  height=len(section_names), font=('Segoe UI', 10),
                                  bg=self.COLORS['card'], fg=self.COLORS['text'],
                                  selectbackground=self.COLORS['accent'],
                                  selectforeground=self.COLORS['header_text'],
                                  highlightthickness=0, relief='flat')
        for name in section_names:
            section_list.insert('end', name)
        section_list.pack(fill='x')
        form_canvas = tk.Canvas(editor_body, bg=self.COLORS['page'],
                                highlightthickness=0)
        form_scroll = ttk.Scrollbar(editor_body, orient='vertical', command=form_canvas.yview)
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_canvas.pack(side='left', fill='both', expand=True)
        form_scroll.pack(side='right', fill='y')
        form = ttk.Frame(form_canvas)
        form_id = form_canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda event: form_canvas.configure(scrollregion=form_canvas.bbox('all')))
        form_canvas.bind('<Configure>', lambda event: form_canvas.itemconfigure(form_id, width=event.width))
        advanced = ttk.Frame(tabs)
        tabs.add(advanced, text=raw_label)
        ttk.Label(advanced, text="Edit the complete configuration here. Switching to Organized editor updates its fields; Save settings writes the file.",
                  wraplength=850).pack(anchor='w', padx=8, pady=8)
        ttk.Label(advanced, text=FIXED_CROSSHAIR_NOTICE,
                  wraplength=850).pack(anchor='w', padx=8, pady=(0, 8))
        frame = ttk.Frame(advanced)
        frame.pack(fill='both', expand=True, padx=8, pady=4)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        text = tk.Text(frame, wrap='none', font=('Consolas', 9),
                       bg=self.COLORS['field'], fg=self.COLORS['text'],
                       insertbackground=self.COLORS['text'], undo=True)
        scroll_y = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        scroll_x = ttk.Scrollbar(frame, orient='horizontal', command=text.xview)
        text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        text.grid(row=0, column=0, sticky='nsew')
        scroll_y.grid(row=0, column=1, sticky='ns')
        scroll_x.grid(row=1, column=0, sticky='ew')
        default_tab = ttk.Frame(tabs)
        tabs.add(default_tab, text='Frozen default YAML')
        ttk.Label(default_tab, text=f'Read-only reference · {default_source}',
                  wraplength=850).pack(anchor='w', padx=8, pady=(8, 2))
        ttk.Label(default_tab, text='Reset to default stages this profile in the editor; Save settings writes only the active configuration.',
                  wraplength=850).pack(anchor='w', padx=8, pady=(0, 6))
        default_frame = ttk.Frame(default_tab)
        default_frame.pack(fill='both', expand=True, padx=8, pady=4)
        default_frame.grid_rowconfigure(0, weight=1)
        default_frame.grid_columnconfigure(0, weight=1)
        default_text = tk.Text(default_frame, wrap='none', font=('Consolas', 9),
                               bg=self.COLORS['field'], fg=self.COLORS['text'])
        default_text.insert('1.0', default_content)
        default_text.configure(state='disabled')
        default_scroll = ttk.Scrollbar(default_frame, orient='vertical', command=default_text.yview)
        default_scroll_x = ttk.Scrollbar(default_frame, orient='horizontal', command=default_text.xview)
        default_text.configure(yscrollcommand=default_scroll.set,
                               xscrollcommand=default_scroll_x.set)
        default_text.grid(row=0, column=0, sticky='nsew')
        default_scroll.grid(row=0, column=1, sticky='ns')
        default_scroll_x.grid(row=1, column=0, sticky='ew')
        window._default_text = default_text

        variables = {}
        widgets = {}
        sections = {}
        for group, dotted, label, kind in FIELDS:
            if group not in sections:
                box = ttk.LabelFrame(form, text=group)
                box.grid_columnconfigure(1, weight=1)
                sections[group] = [box, 0]
            box, row = sections[group]
            sections[group][1] += 1
            ttk.Label(box, text=label, wraplength=255, justify='left').grid(
                row=row, column=0, sticky='w', padx=8, pady=5)
            var = tk.BooleanVar() if kind == 'bool' else tk.StringVar()
            variables[dotted] = var
            if kind == 'bool':
                widget = ttk.Checkbutton(box, variable=var)
            elif kind == 'catalog_mode':
                widget = ttk.Combobox(box, textvariable=var,
                                      values=('live-iondata', 'csv'), state='readonly')
            else:
                widget = ttk.Entry(box, textvariable=var)
            widget.grid(row=row, column=1, sticky='ew', padx=8, pady=5)
            widgets[dotted] = widget
            if kind in ('dir', 'file'):
                def browse(field=dotted, mode=kind, title=label):
                    selected = (filedialog.askdirectory(parent=window, title=title)
                                if mode == 'dir' else filedialog.askopenfilename(parent=window, title=title))
                    if selected:
                        variables[field].set(selected)
                ttk.Button(box, text='Browse…', command=browse).grid(row=row, column=2, padx=8)
        def show_section(*_):
            index = section_names.index(selected_section.get())
            if section_list.curselection() != (index,):
                section_list.selection_clear(0, 'end')
                section_list.selection_set(index)
            for group, (box, _) in sections.items():
                box.pack_forget()
                if group == selected_section.get():
                    box.pack(fill='x', padx=12, pady=(8, 2))
            form_canvas.yview_moveto(0)

        section_list.bind('<<ListboxSelect>>', lambda _event: (
            selected_section.set(section_names[section_list.curselection()[0]])
            if section_list.curselection() else None))
        selected_section.trace_add('write', show_section)
        show_section()
        ttk.Label(form_outer, text=f"Sample-specific paths, geometry, provenance and display parameters remain in {raw_label}.",
                  wraplength=820).pack(anchor='w', padx=16, pady=8)
        error = tk.StringVar(value='')
        ttk.Label(window, textvariable=error, foreground='#b45309', wraplength=850).pack(anchor='w', padx=12)
        state = {'hash': None, 'raw': None, 'text': None, 'saved_raw': None,
                 'saved_text': None, 'tab': 'form', 'switching': False}

        def fill_form(raw):
            import math
            for _, dotted, _, kind in FIELDS:
                value = field_value(raw, dotted)
                if kind == 'bool' and value is not None and not isinstance(value, bool):
                    raise ValueError(f'{dotted}: use a YAML boolean (true or false)')
                if kind == 'positive_number' and value is not None and (
                        isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value <= 0):
                    raise ValueError(f'{dotted}: use a positive YAML number')
                if kind == 'positive_int' and value is not None and (
                        isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                    raise ValueError(f'{dotted}: use a positive YAML whole number')
            for _, dotted, _, kind in FIELDS:
                value = field_value(raw, dotted)
                variables[dotted].set(bool(value) if kind == 'bool' else '' if value is None else str(value))

        def load():
            try:
                raw_bytes = Path(path).read_bytes()
                content = raw_bytes.decode('utf-8')
            except Exception as exc:
                error.set(f"Could not read configuration: {exc}")
                return
            state.update(hash=hashlib.sha256(raw_bytes).hexdigest(), raw=None,
                         text=content, saved_raw=None, saved_text=content)
            text.delete('1.0', 'end')
            text.insert('1.0', content)
            try:
                raw = parse_text(content, path)
                fill_form(raw)
            except Exception as exc:
                state['tab'] = 'raw'
                tabs.select(advanced)
                error.set(f"Configuration needs correction in {raw_label}: {exc}")
                return
            state.update(raw=raw, saved_raw=raw)
            if tabs.select() != str(default_tab):
                state['tab'] = 'raw' if tabs.select() == str(advanced) else 'form'
            error.set(default_warning)

        def on_tab_changed(_event):
            if state['switching'] or tabs.select() == str(default_tab):
                return
            target = 'raw' if tabs.select() == str(advanced) else 'form'
            if target == state['tab']:
                return
            try:
                if target == 'raw':
                    if state['raw'] is None:
                        raise ValueError(f'Correct {raw_label} before using the organized editor.')
                    if text.get('1.0', 'end-1c') != state['text']:
                        raise ValueError(f'{raw_label} has unsaved edits; review them in {raw_label} before editing the form.')
                    raw = apply_fields(state['raw'], {key: var.get() for key, var in variables.items()})
                    if raw != state['raw']:
                        content = dump_text(raw, path)
                        text.delete('1.0', 'end')
                        text.insert('1.0', content)
                        state.update(raw=raw, text=content)
                else:
                    content = text.get('1.0', 'end-1c')
                    raw = parse_text(content, path)
                    fill_form(raw)
                    state.update(raw=raw, text=content)
                state['tab'] = target
                error.set('')
            except Exception as exc:
                state['switching'] = True
                tabs.select(advanced if state['tab'] == 'raw' else form_outer)
                state['switching'] = False
                error.set(str(exc))

        tabs.bind('<<NotebookTabChanged>>', on_tab_changed)

        def stage_content(content, source_path, label):
            try:
                raw = parse_text(content, source_path)
                fill_form(raw)
                staged = (content if Path(source_path).suffix.lower() == Path(path).suffix.lower()
                          else dump_text(raw, path))
            except Exception as exc:
                error.set(f'Could not stage {label}: {exc}')
                return
            text.delete('1.0', 'end')
            text.insert('1.0', staged)
            state.update(raw=raw, text=staged, tab='raw')
            tabs.select(advanced)
            error.set(f'{label} staged in {raw_label}; Save settings to write the active file.')

        def reset_to_default():
            stage_content(default_content, default_path, 'Default profile')

        def restore_backup():
            selected = filedialog.askopenfilename(
                parent=window, title='Restore a VisPa configuration backup',
                initialdir=str(Path(path).parent / 'config_backups'),
                filetypes=[('Configuration', '*.yaml *.yml *.json'), ('All files', '*.*')])
            if not selected:
                return
            try:
                content = Path(selected).read_text(encoding='utf-8')
            except Exception as exc:
                error.set(f'Could not read backup: {exc}')
                return
            stage_content(content, selected, f'Backup {Path(selected).name}')

        def save():
            try:
                if tabs.select() == str(default_tab):
                    raise ValueError('Default YAML is read-only. Choose Organized editor or Raw YAML before saving.')
                if hashlib.sha256(Path(path).read_bytes()).hexdigest() != state['hash']:
                    raise ValueError('The file changed outside this window. Reload it before saving.')
                if tabs.select() == str(advanced):
                    content = text.get('1.0', 'end-1c')
                    raw = parse_text(content, path)
                    fill_form(raw)
                else:
                    if text.get('1.0', 'end-1c') != state['text']:
                        raise ValueError(f'{raw_label} has unsaved edits. Switch to {raw_label} to review them.')
                    raw = apply_fields(state['raw'], {key: var.get() for key, var in variables.items()})
                    content = state['text'] if raw == state['raw'] else dump_text(raw, path)
                if (raw == state['saved_raw'] and
                        content.replace('\r\n', '\n') == state['saved_text'].replace('\r\n', '\n')):
                    error.set('No changes to save.')
                    return
            except Exception as exc:
                error.set(str(exc))
                return
            if self._save_config_text(path, content, expected_sha256=state['hash']):
                load()
                self._refresh_dataset_sources()
                self.update_status('Configuration saved; restart VisPa to apply changed source folders')

        load()
        buttons = tk.Frame(window)
        buttons.pack(pady=(0, 8))
        ttk.Button(buttons, text="Save settings", command=save).pack(side='left', padx=4)
        ttk.Button(buttons, text="Reload", command=load).pack(side='left', padx=4)
        ttk.Button(buttons, text="Reset to default", command=reset_to_default).pack(side='left', padx=4)
        ttk.Button(buttons, text="Restore backup…", command=restore_backup).pack(side='left', padx=4)
        tk.Label(window, text="Saving validates the complete configuration. Restart VisPa after changing source folders.",
                 bg=self.COLORS['page'], fg=self.COLORS['muted'],
                 font=('Segoe UI', 8)).pack(pady=(0, 6))

    def _save_config_text(self, path, content, expected_sha256=None):
        """Delegate validated atomic saves to the configuration module."""
        self._log_operation(
            "Save settings", "start", path=path,
            expected_sha256=expected_sha256)
        try:
            from .config import save_config
            result = save_config(path, content, expected_sha256=expected_sha256)
        except Exception as exc:
            self._log_operation(
                "Save settings", "failed", path=path, error=exc)
            messagebox.showerror("Config", f"Could not save configuration:\n{exc}")
            return False
        self._log_operation(
            "Save settings", "finished", path=path,
            changed=result.get("changed"), backup=result.get("backup"))
        return True

    def _show_progress(self, maximum=None):
        self.progress.stop()
        if maximum is None:
            self.progress.configure(mode='indeterminate')
        else:
            self.progress.configure(mode='determinate', maximum=max(1, int(maximum)), value=0)
        self.progress.pack(side='right', padx=14, pady=6)
        if maximum is None:
            self.progress.start()

    def _hide_progress(self):
        self.progress.stop()
        self.progress.pack_forget()
        self.progress.configure(value=0)

    def _set_progress(self, completed, total):
        """Update the determinate startup checklist bar on the Tk thread."""
        self.progress.configure(
            mode='determinate', maximum=max(1, int(total)),
            value=min(max(0, int(completed)), max(1, int(total))))
        self.root.update_idletasks()

    def _start_resource_check(self):
        """Run the shared data check without blocking startup or rendering."""
        if self._operation_running:
            self.root.after(500, self._start_resource_check)
            return
        identity = (self.sample_id.get().strip(), self.neuron_id.get().strip())
        self._log_operation(
            "Resource check", "start", sample=identity[0], neuron=identity[1],
            config=self.config_path,
            update_source=os.environ.get("VISPA_UPDATES_SOURCE")
                          or "checkout CHANGELOG.md")
        self.update_status("Checking VisPa resources…")
        self._show_progress(maximum=100)

        def worker():
            try:
                from .readiness import data_check
                report = data_check(
                    config=self.config_path,
                    sample_id=identity[0],
                    neuron_id=identity[1],
                    progress=lambda done, total: self._ui_call(
                        self._set_progress, done, total),
                )
            except Exception as exc:
                self._ui_call(self._finish_resource_check, identity, None, exc)
            else:
                self._ui_call(self._finish_resource_check, identity, report, None)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_resource_check(self, identity, report, error):
        """Show the startup checklist after the background readiness pass."""
        self._hide_progress()
        current = (self.sample_id.get().strip(), self.neuron_id.get().strip())
        if current != identity:
            self.update_status("Resource check discarded for a stale identity")
            return
        if error is not None:
            message = f"Resource check failed: {error}"
            self._log_operation("Resource check", "failed", error=error)
            messagebox.showwarning("VisPa data check", message)
            return
        self.last_data_check = report
        self._log_operation(
            "Resource check", "finished", ready=report["ready"],
            checked=report["checked"], issues=report["issues"])
        display_lines = [
            line.replace("[OK]", "✓", 1)
                .replace("[UPDATE]", "↑", 1)
                .replace("[MISSING]", "!", 1)
                .replace("[INFO]", "i", 1)
            for line in report["checklist"]
        ]
        for line in display_lines:
            self._append_log(line)
        if report["ready"]:
            self.update_status(f"All configured resources ready ({report['checked']}/{report['checked']})")
        else:
            self.update_status(f"Resource check: {report['issues']} required item(s) need attention")
        update_item = next(
            (item for item in report.get("checks", ())
             if item.get("role") == "update_status"),
            None)
        if update_item and update_item.get("status") == "update_available":
            messagebox.showinfo(
                "VisPa update available",
                f"{update_item['detail']}\n\n"
                "Review the update, then update the current local VisPa clone "
                "and reinstall its editable package. Use `vispa updates` for "
                "release details.")
        self._show_data_check(report)
        if (getattr(self, '_auto_fill_on_identity', True)
                and not getattr(self, '_autofill_identity', None)
                and self.sample_id.get().strip()
                and self.neuron_id.get().strip()):
            self.root.after(100, self._auto_fill_current_identity)

    def _show_data_check(self, report):
        """Render a readable, scrollable resource checklist on the Tk thread."""
        C = self.COLORS
        window = tk.Toplevel(self.root)
        window.title("VisPa resource check")
        window.configure(bg=C['page'])
        window.transient(self.root)
        width = min(self._px(660), self.root.winfo_screenwidth() - self._px(48))
        height = min(self._px(560), self.root.winfo_screenheight() - self._px(72))
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(self._px(560), self._px(430))
        window.columnconfigure(0, weight=1)
        window.rowconfigure(3, weight=1)

        ready = bool(report.get("ready"))
        status_color = C['accent'] if ready else '#b34a4a'
        header = tk.Frame(window, bg=C['header'], padx=self._px(20),
                          pady=self._px(14))
        header.grid(row=0, column=0, sticky='ew')
        header.grid_columnconfigure(0, weight=1)
        tk.Label(header, text="Resource check", bg=C['header'],
                 fg=C['header_text'], font=('Segoe UI', 14, 'bold'),
                 anchor='w').grid(row=0, column=0, sticky='ew')
        identity = " / ".join(
            value for value in (report.get("sample_id"), report.get("neuron_id"))
            if value
        )
        neuron_subtitle = (f"Neuron Loaded: {identity}"
                           if identity else "Neuron Loaded: no active neuron")
        tk.Label(header, text=neuron_subtitle,
                 bg=C['header'], fg=C['header_muted'],
                 font=('Segoe UI', 8), anchor='w').grid(
                     row=1, column=0, sticky='ew', pady=(self._px(2), 0))
        version_report = getattr(self, "version_report", {})
        versions = tk.Frame(header, bg=C['header'])
        versions.grid(row=2, column=0, sticky='ew', pady=(self._px(5), 0))
        versions.grid_columnconfigure(0, weight=1, uniform='versions')
        versions.grid_columnconfigure(1, weight=1, uniform='versions')
        version_rows = self._version_display_rows(version_report)
        version_colors = (C['accent'], '#b9a4e4')
        for column, ((label, value), color) in enumerate(
                zip(version_rows, version_colors)):
            block = tk.Frame(versions, bg=C['header'])
            block.grid(row=0, column=column, sticky='nsew',
                       padx=(0, self._px(12)) if column == 0 else
                       (self._px(12), 0))
            tk.Label(
                block, text=label, bg=C['header'], fg=color,
                font=('Segoe UI', 9, 'bold'), anchor='w').pack(fill='x')
            tk.Label(
                block, text=value, bg=C['header'], fg=C['header_text'],
                font=('Consolas', 10, 'bold'), anchor='w', justify='left',
                wraplength=max(self._px(220), width // 2 - self._px(36))).pack(
                    fill='x')
        tk.Label(header, text=f"{report.get('checked', 0)} checks",
                 bg=C['header'], fg=C['header_text'],
                 font=('Segoe UI', 9, 'bold')).grid(
                     row=0, column=1, rowspan=3, sticky='e')

        summary = tk.Frame(window, bg=status_color, padx=self._px(20),
                           pady=self._px(10))
        summary.grid(row=1, column=0, sticky='new')
        summary_text = ("All configured resources ready"
                        if ready else
                        f"{report.get('issues', 0)} required resource(s) need attention")
        tk.Label(summary, text=summary_text, bg=status_color, fg='white',
                 font=('Segoe UI', 11, 'bold'), anchor='w').pack(
                     fill='x')

        key_panel = tk.Frame(
            window, bg=C['page'], padx=self._px(18), pady=self._px(7))
        key_panel.grid(row=2, column=0, sticky='ew')
        key_panel.grid_columnconfigure(1, weight=1)
        try:
            from .config import load as load_config
            configuration = load_config(self.config_path)
            sample_entry = configuration["samples"].get(report.get("sample_id"), {})
        except Exception:
            configuration = {}
            sample_entry = {}
        defaults = configuration.get("defaults", {})
        sources = configuration.get("sources", {})
        visual = configuration.get("visual_toolkit", {})
        key_values = (
            ("Output", visual.get("output_root")),
            ("Download cache", defaults.get("cache_root")),
            ("IONData", sources.get("http_host")),
            ("Processed SWC", sources.get("brain_view", {}).get("processed_swc_root")),
            ("DS00", sample_entry.get("ds00_processed")),
        )
        for row_index, (label, value) in enumerate(key_values):
            tk.Label(
                key_panel, text=label, bg=C['page'], fg=C['muted'],
                font=('Segoe UI', 8, 'bold'), anchor='nw').grid(
                    row=row_index, column=0, sticky='nw',
                    padx=(0, self._px(10)), pady=self._px(2))
            tk.Label(
                key_panel, text=str(value) if value else "not configured",
                bg=C['page'], fg=C['text'], font=('Consolas', 8),
                anchor='w', justify='left',
                wraplength=max(self._px(300), width - self._px(150))).grid(
                    row=row_index, column=1, sticky='ew', pady=self._px(2))

        body = tk.Frame(window, bg=C['card'], highlightthickness=1,
                        highlightbackground=C['border'])
        body.grid(row=3, column=0, sticky='nsew',
                  padx=self._px(18), pady=(self._px(14), self._px(8)))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        canvas = tk.Canvas(body, bg=C['card'], highlightthickness=0,
                           bd=0)
        scrollbar = ttk.Scrollbar(body, orient='vertical',
                                  command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        rows = tk.Frame(canvas, bg=C['card'])
        rows_window = canvas.create_window((0, 0), window=rows, anchor='nw')
        rows.columnconfigure(1, weight=1)
        rows.bind(
            '<Configure>',
            lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind(
            '<Configure>',
            lambda event: canvas.itemconfigure(rows_window, width=event.width))
        for widget in (canvas, rows):
            widget.bind(
                '<MouseWheel>',
                lambda event: canvas.yview_scroll(int(-event.delta / 120), 'units'))

        for index, item in enumerate(report.get("checks") or []):
            item_ready = item.get("status") in {"ready", "configured"}
            row = tk.Frame(rows, bg=C['card'])
            row.grid(row=index, column=0, sticky='ew')
            row.columnconfigure(1, weight=1)
            tk.Label(
                row, text="✓" if item_ready else "!",
                bg=C['accent_soft'] if item_ready else '#493034',
                fg=C['header_text'] if item_ready else '#f0b9b9',
                font=('Segoe UI', 10, 'bold'), width=3,
                padx=self._px(2), pady=self._px(3),
            ).grid(row=0, column=0, rowspan=2, sticky='n',
                   padx=(self._px(12), self._px(10)),
                   pady=(self._px(10), self._px(8)))
            tk.Label(
                row, text=item.get("label") or item.get("role") or "Resource",
                bg=C['card'], fg=C['text'],
                font=('Segoe UI', 9, 'bold'), anchor='w',
            ).grid(row=0, column=1, sticky='ew',
                   padx=(0, self._px(14)), pady=(self._px(9), 0))
            detail = item.get("detail") or item.get("status") or ""
            tk.Label(
                row, text=detail, bg=C['card'], fg=C['muted'],
                font=('Segoe UI', 8), anchor='w', justify='left',
                wraplength=max(self._px(390), width - self._px(170)),
            ).grid(row=1, column=1, sticky='ew',
                   padx=(0, self._px(14)), pady=(self._px(1), 0))
            path = item.get("path")
            if path:
                tk.Label(
                    row, text=str(path), bg=C['card'], fg=C['muted'],
                    font=('Consolas', 8), anchor='w', justify='left',
                    wraplength=max(self._px(390), width - self._px(170)),
                ).grid(row=2, column=1, sticky='ew',
                       padx=(0, self._px(14)),
                       pady=(self._px(3), self._px(9)))
            else:
                row.grid_rowconfigure(2, minsize=self._px(9))
            tk.Frame(row, bg=C['border'], height=1).grid(
                row=3, column=0, columnspan=2, sticky='ew')

        # Bind the whole rendered list, including item labels and paths, so the
        # wheel scrolls while the pointer is directly over resource details.
        self._bind_settings_wheel(
            body, self._settings_wheel_handler(canvas))

        footer = tk.Frame(window, bg=C['page'], padx=self._px(18),
                          pady=self._px(10))
        footer.grid(row=4, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        tk.Label(
            footer,
            text="Remote services are verified when their data is first requested.",
            bg=C['page'], fg=C['muted'], font=('Segoe UI', 8),
            anchor='w', justify='left', wraplength=width - self._px(160),
        ).grid(row=0, column=0, sticky='ew')
        close_button = self._flat_button(footer, "Close", window.destroy,
                                         primary=True)
        close_button.grid(row=0, column=1, sticky='e')
        window.bind('<Escape>', lambda event: window.destroy())
        window.grab_set()
        close_button.focus_set()

    def _append_log(self, line):
        """Append one line to the process log and mirror it in the status strip."""
        widget = getattr(self, 'log_widget', None)
        if widget is None:
            return
        widget.configure(state='normal')
        widget.insert('end', str(line) + '\n')
        total = int(widget.index('end-1c').split('.')[0])
        if total > 400:
            widget.delete('1.0', f'{total - 400}.0')
        widget.see('end')
        widget.configure(state='disabled')
        text = str(line).strip()
        if text and not text.startswith('Plot saved:'):
            self.update_status(text)

    def _log_operation(self, operation, state, **details):
        """Write a structured GUI operation/script record to the process log."""
        append = getattr(self, "_append_log", None)
        if append is None:
            return
        fields = []
        for key, value in details.items():
            if value is None or value == "":
                continue
            if isinstance(value, (list, tuple)):
                value = subprocess.list2cmdline([str(item) for item in value])
            fields.append(f"{key}={value}")
        line = f"[{str(state).upper()}] {operation}"
        if fields:
            line += " | " + " | ".join(fields)
        ui_call = getattr(self, "_ui_call", None)
        if ui_call is None:
            append(line)
        else:
            ui_call(append, line)

    def _drain_log(self):
        try:
            while True:
                self._append_log(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(150, self._drain_log)

    def _numeric_values(self):
        """Parse the numeric form, naming the field in every validation error."""
        def parse(label, variable, cast, minimum=None):
            raw = variable.get().strip()
            if not raw:
                raise ValueError(
                    f"{label} is empty. Wait for automatic neuron lookup or type a value.")
            try:
                value = cast(raw)
            except ValueError:
                kind = 'whole number' if cast is int else 'number'
                raise ValueError(f"{label} must be a {kind}; got {raw!r}.") from None
            if minimum is not None and value < minimum:
                raise ValueError(f"{label} must be at least {minimum:g}; got {raw!r}.")
            return value

        return (
            parse("Soma X", self.x_coord, float),
            parse("Soma Y", self.y_coord, float),
            parse("Soma Z", self.z_coord, float),
            parse("Context width", self.width_um, int, 1),
            parse("Context height", self.height_um, int, 1),
            parse("Context depth", self.depth_um, int, 1),
            parse("Soma window", self.soma_cubes, float),
        )

    def validate_inputs(self):
        """Validate numeric inputs and report the exact offending field."""
        identity = (self.sample_id.get().strip(), self.neuron_id.get().strip())
        raw_soma = (
            self.x_coord.get().strip(),
            self.y_coord.get().strip(),
            self.z_coord.get().strip(),
        )
        if not all(raw_soma):
            messagebox.showwarning(
                "Load soma first",
                "Enter a valid Sample ID and Neuron ID; soma coordinates load automatically.",
            )
            return False
        try:
            placeholder = all(float(value) == 0 for value in raw_soma)
        except ValueError:
            placeholder = False
        if placeholder and self._autofill_identity != identity:
            messagebox.showwarning(
                "Load soma first",
                "Soma coordinates still contain the placeholder (0, 0, 0).\n"
                "Wait for automatic neuron lookup or type the coordinates.",
            )
            return False
        try:
            _x, _y, _z, _w, _h, _d, cubes = self._numeric_values()
            limit = float(REVIEW_SETTINGS['soma_window']['max_cubes_xy'])
            if not 0 < cubes <= limit:
                raise ValueError(
                    f"Soma window must be greater than 0 and at most {limit:g} blocks.")
            return True
        except ValueError as error:
            messagebox.showerror("Input Error", str(error))
            return False

    def browse_folder(self):
        """Open folder selection dialog."""
        selected_dir = filedialog.askdirectory(initialdir=self.output_dir.get(), title="Select Output Folder")
        if selected_dir:
            self.output_dir.set(selected_dir)
            self.manual_path_set = True

    def update_status(self, message):
        if threading.current_thread() is not threading.main_thread():
            self._ui_call(self.update_status, message)
            return
        self.status_text.set(message)
        self.root.update_idletasks()

    def _apply_review_event(self, event):
        """Apply a validated identity as one UI-thread update."""
        current = (self.sample_id.get().strip(), self.neuron_id.get().strip())
        self._review_event_key = event.key
        self._current_review_event = event
        if event.identity == current:
            self.update_status(
                f"Review source updated for {event.sample_id}/{event.neuron_id}; "
                "cached panels kept.")
            return
        self.sample_id.set(event.sample_id)
        self.neuron_id.set(event.neuron_id)
        # Traces clear soma values and preview state as the identity changes. Call
        # explicitly too so partially initialized or headless instances stay safe.
        self._on_identity_change()
        self._reload_existing(quiet=True, rerender_if_stale=False)
        self._review_session_error = None
        if not self._auto_fill_on_identity:
            self.update_status(
                f"Review session selected {event.sample_id}/{event.neuron_id}; "
                "automatic soma loading is disabled.")
        else:
            self.update_status(
                f"Selected {event.sample_id}/{event.neuron_id}; loading soma automatically…")
            self.load_and_autofill(silent_success=True, silent_failure=True)

    def _poll_review_session(self):
        """Poll the local JSON handoff; all identity and widget changes stay on Tk."""
        try:
            try:
                event, _payload = read_review_session(self.review_session_path)
            except (OSError, ValueError) as exc:
                message = f"Review session unavailable: {exc}"
                if message != self._review_session_error:
                    self._review_session_error = message
                    self.update_status(message)
            else:
                self._review_session_error = None
                if event.key != self._review_event_key:
                    self._review_event_key = event.key
                    if self._operation_running:
                        self._pending_review_event = event
                        self.update_status(
                            f"Review event queued until processing finishes: "
                            f"{event.sample_id}/{event.neuron_id}")
                    else:
                        self._pending_review_event = None
                        self._apply_review_event(event)
                pending = self._pending_review_event
                if pending is not None and not self._operation_running:
                    self._pending_review_event = None
                    self._apply_review_event(pending)
        finally:
            self.root.after(500, self._poll_review_session)

    def _ui_call(self, callback, *args, **kwargs):
        """Marshal widget calls from acquisition workers onto Tk's UI thread."""
        if threading.current_thread() is threading.main_thread():
            callback(*args, **kwargs)
            return
        try:
            self.root.after(0, lambda: callback(*args, **kwargs))
        except tk.TclError:
            # The window may be closing while an acquisition finishes.
            pass

    def prepare_output_dir(self):
        """Ensure output directory exists and return it."""
        path = self.output_dir.get().strip()

        # If empty, fallback to the calculated default
        if not path:
            path = self._generate_default_path(self.sample_id.get())
            self.output_dir.set(path)

        if not self.save_outputs.get():
            return path
        if not os.path.exists(path):
            try:
                os.makedirs(path)
                self.update_status(f"📁 Created output directory: {path}")
            except OSError as e:
                messagebox.showerror("Error", f"Could not create output directory:\n{e}")
                return None
        return path

    def auto_load_default_neuron(self):
        """Compatibility entry point for the current live identity lookup."""
        self._auto_fill_current_identity()

    def load_and_autofill(self, silent_success=False, silent_failure=False,
                          refresh=True, after_load=None):
        """Loads the neuron and automatically fills soma coordinates.

        Args:
            silent_success: If True, don't show success messagebox (for auto-load)
            silent_failure: If True, report lookup failure in the status panel only
            refresh: Check IONData on every load; False explicitly reads local cache only.
            after_load: Optional UI callback after coordinates and cache identity
                are current. Defaults to loading cached rendering data.
        """
        sample_id = self.sample_id.get().strip()
        neuron_id = self.neuron_id.get().strip()
        after_id = getattr(self, '_soma_autofill_after', None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._soma_autofill_after = None
        self._neuron_lookup_state = "checking"
        self._neuron_lookup_error = None
        self._update_neuron_status()
        self._log_operation(
            "Raw SWC load", "start", sample=sample_id, neuron=neuron_id,
            source="live refresh" if refresh else "local cache",
            config=getattr(self, "config_path", None))

        def worker():
            self._ui_call(self._show_progress)
            try:
                source_label = "IONData" if refresh else "local cache"
                self.update_status(f"Loading {sample_id}/{neuron_id} from {source_label}…")
                tree = IT.IONData().getRawNeuronTreeByID(
                    sample_id, neuron_id, refresh=refresh)
                if tree is None:
                    detail = (f"Could not load raw SWC for {sample_id}/{neuron_id} "
                              f"from {source_label}.")
                    def report_missing():
                        self._neuron_lookup_state = "not_found"
                        self._log_operation(
                            "Raw SWC load", "not_found", sample=sample_id,
                            neuron=neuron_id, source=source_label)
                        self._update_neuron_status()
                        if silent_failure:
                            self.update_status(detail)
                        else:
                            messagebox.showwarning("Not Found", detail)
                    self.root.after(0, report_missing)
                    return
                soma_xyz = tuple(float(value) for value in (tree.root.x, tree.root.y, tree.root.z))

                def apply_if_current():
                    if not identity_matches((sample_id, neuron_id), self.sample_id.get(), self.neuron_id.get()):
                        self.update_status(f"⚠️ Discarded stale auto-fill for {sample_id}/{neuron_id}")
                        return
                    self.x_coord.set(str(soma_xyz[0]))
                    self.y_coord.set(str(soma_xyz[1]))
                    self.z_coord.set(str(soma_xyz[2]))
                    self._autofill_identity = (sample_id, neuron_id)
                    self._neuron_lookup_state = "found"
                    self._neuron_lookup_error = None
                    self._log_operation(
                        "Raw SWC load", "finished", sample=sample_id,
                        neuron=neuron_id, source=source_label,
                        soma_xyz=soma_xyz)
                    self._update_neuron_status()
                    self.update_status(
                        f"✅ Loaded from {source_label}: "
                        f"{soma_xyz[0]:g}, {soma_xyz[1]:g}, {soma_xyz[2]:g}")
                    if not silent_success:
                        messagebox.showinfo("Success", "Neuron Loaded & Coordinates Auto-filled!")
                    if after_load is not None:
                        after_load(sample_id, neuron_id)
                    else:
                        self._activate_cached_figures(
                            sample_id, neuron_id.removesuffix(".swc"),
                            quiet=False, start_fnt=False)
                self.root.after(0, apply_if_current)
            except Exception as e:
                status = f"⚠️ Auto-load failed: {e}" if silent_success else f"⚠️ Load failed: {e}"
                error_text = str(e)
                def report_failure():
                    self._autofill_identity = None
                    self._neuron_lookup_state = "error"
                    self._neuron_lookup_error = error_text
                    self._log_operation(
                        "Raw SWC load", "failed", sample=sample_id,
                        neuron=neuron_id, error=error_text)
                    self._update_neuron_status()
                    if silent_failure:
                        self.update_status(status)
                    else:
                        messagebox.showerror("Load failed", status)
                    self._check_identity_cache()
                self.root.after(0, report_failure)
            finally:
                self._ui_call(self._hide_progress)

        self._launch_processing(worker)

    def _update_current_identity(self):
        """Refresh the SWC, then rerender using existing acquisition caches."""
        self.load_and_autofill(
            silent_success=True,
            after_load=lambda _sample, _neuron: self._render_from_acquisition_cache())

    def _render_from_acquisition_cache(self):
        """Force figure rendering while retaining downloaded cube/slice caches."""
        self._cache_status = "cached: updating figures"
        self._update_neuron_status()
        self.update_status("Updating figures from cached acquisition data.")
        self.run_selected(force_rerender=True, force_reprocess=False)

    def _reprocess_current_identity(self):
        """Refresh the SWC, then rebuild every panel from new acquisitions."""
        self.load_and_autofill(
            silent_success=True,
            after_load=lambda _sample, _neuron: self._reprocess_from_sources())

    def _reprocess_from_sources(self):
        """Force all panels to acquire source cubes and slices again."""
        self._cache_status = "cached: re-processing sources"
        self._update_neuron_status()
        self.update_status("Re-processing all figures with fresh source acquisition.")
        self.run_selected(
            roles=("Soma", "Context", "Sagittal"),
            force_review_figure=True, force_reprocess=True)

    def _capture_processing_request(self):
        if not self.validate_inputs():
            return None
        out_path = self.prepare_output_dir()
        if not out_path:
            return None
        try:
            def flag(name, default=True):
                variable = getattr(self, name, None)
                return bool(variable.get()) if variable is not None else default

            review_event = getattr(self, '_current_review_event', None)
            current_identity = (self.sample_id.get().strip(), self.neuron_id.get().strip())
            if review_event is not None and review_event.identity != current_identity:
                review_event = None

            return make_processing_request(
                self.sample_id.get(), self.neuron_id.get(),
                (self.x_coord.get(), self.y_coord.get(), self.z_coord.get()),
                self.grid_radius.get(), self.width_um.get(), self.height_um.get(),
                self.depth_um.get(), out_path, save_outputs=flag('save_outputs'),
                save_soma_nifti=flag('save_soma_nifti'),
                soma_cubes=(float(self.soma_cubes.get())
                            if hasattr(self, 'soma_cubes') else None),
                plot_soma=flag('plot_soma'), plot_context=flag('plot_context'),
                plot_sagittal=flag('plot_sagittal'),
                save_soma_png=flag('save_soma_png'),
                save_context_png=flag('save_context_png'),
                save_sagittal_png=flag('save_sagittal_png'),
                save_trio_png=flag('save_trio_png'),
                make_review_figure=flag('make_review_figure', False),
                review_session_path=(review_event.path if review_event else None),
                review_session_source=(review_event.source if review_event else None),
                review_session_event_id=(review_event.event_id if review_event else None),
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror("Input Error", f"Invalid processing request: {error}")
            return None

    def _launch_processing(self, process):
        if self._operation_running:
            messagebox.showwarning("Busy", "A VisPa operation is already running.")
            return
        self._operation_running = True

        def guarded():
            try:
                process()
            finally:
                self._ui_call(setattr, self, "_operation_running", False)

        threading.Thread(target=guarded, daemon=True).start()

    # ---------- render helpers (shared by the lane runner and the direct actions) ----------
    def _target_for(self, request, save_flag):
        """Write into the chosen folder only when that artifact's save tick is on."""
        if request.save_outputs and save_flag:
            return request.output_dir
        return self._preview_target_dir(request)

    def _render_soma(self, toolkit, request, target):
        vol, origin, res = toolkit.get_high_res_soma_window(
            request.soma_xyz, window_px=self._soma_window_px(request))
        if request.save_outputs and request.save_soma_nifti:
            toolkit.export_data(vol, origin, res, request.neuron_id,
                                suffix="SomaBlock", output_dir=request.output_dir)
        return toolkit.plot_soma_block(vol, origin, res, request.soma_xyz,
                                       request.neuron_id, output_dir=target)

    def _render_context(self, toolkit, ion, request, target):
        tree = ion.getRawNeuronTreeByID(request.sample_id, request.neuron_id)
        if tree is None:
            raise ValueError(f"Raw neuron {request.sample_id}/{request.neuron_id} was not found")
        vol, origin, res = toolkit.get_low_res_widefield(
            request.soma_xyz, width_um=request.width_um, height_um=request.height_um,
            depth_um=request.depth_um)
        return toolkit.plot_widefield_context(
            vol, origin, res, request.soma_xyz, request.neuron_id,
            swc_tree=tree, output_dir=target)

    def _render_sagittal(self, toolkit, request, target):
        from .renderers.microscopy_panels import SAMPLE_PATHS, resolve_swc_path
        neuron = request.neuron_id.removesuffix('.swc')
        swc, _ = resolve_swc_path(request.sample_id, neuron,
                                  SAMPLE_PATHS.get(request.sample_id) or {})
        if swc is None:
            # Trigger the portal download into VisPa's cache, then let the
            # adapter re-resolve; a network failure leaves the recorded reason.
            try:
                IT.IONData().getRawNeuronTreeByID(request.sample_id, request.neuron_id)
            except Exception as exc:
                self._log_queue.put(
                    f"Portal SWC fetch failed for {request.sample_id}/"
                    f"{request.neuron_id}: {exc}")
        panel = toolkit.render_sagittal_context_from_ds(
            request.neuron_id, request.soma_xyz, output_dir=target)['panel']
        self._ui_call(self._refresh_sagittal_hint)
        return panel

    def _run_worker(self, request, work, message, *, force_reprocess=False):
        """Shared thread body: request + toolkit lifecycle, errors and progress."""
        def process():
            toolkit = None
            try:
                self._ui_call(self._show_progress)
                self._log_operation(
                    "Render worker", "start",
                    sample=request.sample_id, neuron=request.neuron_id,
                    output=request.output_dir, save=request.save_outputs,
                    force_reprocess=force_reprocess)
                toolkit = VisPa(
                    request.sample_id, force_reprocess=force_reprocess)
                stream = getattr(self, '_log_stream', None)
                if stream is not None:
                    # Show the toolkit's fetch/download/render lines in the GUI log.
                    with contextlib.redirect_stdout(stream):
                        paths, errors = work(toolkit)
                else:
                    paths, errors = work(toolkit)
                self._ui_call(self._finish, request, paths, message(request), errors)
                self._log_operation(
                    "Render worker", "finished",
                    sample=request.sample_id, neuron=request.neuron_id,
                    outputs=len([path for path in paths if path]),
                    errors=len(errors))
            except Exception as e:
                self._ui_call(self._show_render_failure, request, str(e))
                self._ui_call(self.update_status, f"Render failed: {e}")
                self._log_operation(
                    "Render worker", "failed",
                    sample=request.sample_id, neuron=request.neuron_id,
                    error=e)
                self._ui_call(messagebox.showerror, "Processing Error", f"Error: {str(e)}")
            finally:
                self._fetch_fnt(request.sample_id, request.neuron_id.removesuffix('.swc'))
                self._ui_call(self._hide_progress)
                if toolkit:
                    toolkit.close()
        self._launch_processing(process)

    def run_selected(self, roles=None, force_review_figure=False,
                     force_rerender=False, force_reprocess=False):
        """Render the panel set; no per-panel or per-artifact selection is exposed."""
        if getattr(self, '_operation_running', False):
            messagebox.showwarning("Busy", "A VisPa operation is already running.")
            return
        request = self._capture_processing_request()
        if request is None:
            return
        if roles is None:
            roles = [role for role, enabled in (
                ("Soma", request.plot_soma), ("Context", request.plot_context),
                ("Sagittal", request.plot_sagittal)) if enabled]
        roles = list(roles)
        if not roles:
            messagebox.showwarning("Nothing to render", "Select at least one panel to render.")
            return

        rendered = []
        review_option = getattr(self, 'make_review_figure', None)
        make_review = force_review_figure or (
            bool(review_option.get()) if review_option is not None else False)
        force_option = getattr(self, 'force_rerender', None)
        force = force_rerender or force_reprocess or (
            bool(force_option.get()) if force_option is not None else False)
        fingerprint = self._fingerprint()

        if not force:
            try:
                needed = list(roles) + (["TrioPlot"] if make_review else [])
                _folders, found, entry = self._find_cached_figures(
                    request.sample_id, request.neuron_id.removesuffix('.swc'))
                if (entry and all(role in found for role in needed)
                        and getattr(self, 'preview_label', None) is not None):
                    state, _notes = self._evaluate_cached(entry, roles=needed)
                    if state == 'same':
                        self._cache_status = (
                            f"cached: current ({len(needed)} figures)")
                        self._update_neuron_status()
                        self.preview_files.update(
                            {role: found[role] for role in needed})
                        self._refresh_preview_tabs()
                        for role in ('Soma', 'Context', 'Sagittal', 'TrioPlot'):
                            if role in needed:
                                self._show_role(role)
                                break
                        self.update_status(
                            "Cached figures match; loaded without re-rendering.")
                        self._append_log("Cached figures reused; no re-render.")
                        self._start_fnt_fetch(
                            request.sample_id, request.neuron_id.removesuffix('.swc'))
                        return
            except Exception:
                # A partially built or headless instance renders normally.
                pass

        def work(toolkit):
            ion = IT.IONData() if "Context" in roles else None
            panels, paths, errors = {}, [], []
            for role in roles:
                self.update_status(f"{role} Plot · rendering…")
                try:
                    if role == "Soma":
                        panel = self._render_soma(
                            toolkit, request,
                            self._target_for(request, request.save_soma_png))
                    elif role == "Context":
                        panel = self._render_context(
                            toolkit, ion, request,
                            self._target_for(request, request.save_context_png))
                    else:
                        panel = self._render_sagittal(
                            toolkit, request,
                            self._target_for(request, request.save_sagittal_png))
                except Exception as exc:
                    # One unavailable panel must not discard the others.
                    self._ui_call(self._append_log, f"{role} render failed: {exc}")
                    errors.append(f"{role}: {self._friendly_error(exc)}")
                    continue
                panels[role] = panel
                paths.append(self._panel_png(panel))
                rendered.append(role)
            trio_path = None
            if len(panels) == 3 and make_review:
                self.update_status("Rendering review figure…")
                saving = request.save_outputs and request.save_trio_png
                trio_target = request.output_dir if saving else self._preview_target_dir(request)
                trio_path = toolkit.plot_tri_plot(
                    [panels["Soma"], panels["Context"], panels["Sagittal"]],
                    request.neuron_id, output_dir=trio_target, legend=False)
                paths.append(trio_path)
            elif make_review:
                missing = [role for role in ("Soma", "Context", "Sagittal")
                           if role not in panels]
                errors.append("TrioPlot: requires Soma, Context and Sagittal; "
                              f"missing {', '.join(missing)}")
            specs = {role: self._panel_spec(panel) for role, panel in panels.items()}
            if request.save_outputs and fingerprint is not None:
                self._write_receipt(
                    request.output_dir, fingerprint,
                    {role: self._panel_png(panel) for role, panel in panels.items()},
                    specs, trio_path=trio_path,
                    review_session_path=request.review_session_path,
                    review_session_source=request.review_session_source,
                    review_session_event_id=request.review_session_event_id)
            return paths, errors

        self._begin_render_preview(request)
        self._run_worker(
            request, work,
            lambda r: f"Rendered {' + '.join(rendered) if rendered else 'nothing'}",
            force_reprocess=force_reprocess)

    def run_highres(self):
        """Render the Soma panel with the current ticks (kept as a direct action)."""
        request = self._capture_processing_request()
        if request is None: return

        def work(toolkit):
            self.update_status("Soma Plot · acquiring soma-centred window…")
            panel = self._render_soma(
                toolkit, request, self._target_for(request, request.save_soma_png))
            return [self._panel_png(panel)], []

        self._run_worker(request, work, lambda r: "Soma plot ready")

    def run_lowres(self):
        """Render the Context panel with the current ticks."""
        request = self._capture_processing_request()
        if request is None: return

        def work(toolkit):
            self.update_status("Context Plot · acquiring 5 µm sections…")
            panel = self._render_context(
                toolkit, IT.IONData(), request,
                self._target_for(request, request.save_context_png))
            return [self._panel_png(panel)], []

        self._run_worker(request, work, lambda r: "Context plot ready")

    def run_both(self):
        """Render Soma and Context together (direct action)."""
        request = self._capture_processing_request()
        if request is None or not messagebox.askyesno("Confirm", "Render Soma and Context panels?"):
            return

        def work(toolkit):
            soma = self._render_soma(
                toolkit, request, self._target_for(request, request.save_soma_png))
            context = self._render_context(
                toolkit, IT.IONData(), request,
                self._target_for(request, request.save_context_png))
            return [self._panel_png(soma), self._panel_png(context)], []

        self._run_worker(request, work, lambda r: "Soma + Context ready")

    def run_sagittal(self):
        """Render the registered processed-DS sagittal panel for the current neuron."""
        request = self._capture_processing_request()
        if request is None: return

        def work(toolkit):
            self.update_status("Sagittal Context Plot · resolving processed-DS panel…")
            panel = self._render_sagittal(
                toolkit, request,
                self._target_for(request, request.save_sagittal_png))
            return [self._panel_png(panel)], []

        self._run_worker(request, work, lambda r: "Sagittal context ready")

    def run_all_panels(self):
        """Render all three panels and their TrioPlot."""
        self.run_selected(roles=("Soma", "Context", "Sagittal"),
                          force_review_figure=True)

# ==================== MAIN LAUNCHER ====================
def _parse_launch_args(argv=None):
    """Parse and validate launch arguments only; configuration is never read or created."""
    parser = argparse.ArgumentParser(
        description=f"VisPa {__version__}: open one exact SampleID / NeuronID pair.",
        allow_abbrev=False)
    parser.add_argument("--sample", dest="sample_id", help="exact sample ID, including any suffix")
    parser.add_argument("--neuron", dest="neuron_id", help="neuron basename, with or without .swc")
    parser.add_argument("--config", help="explicit dataset and output configuration file")
    parser.add_argument("--test", action="store_true",
                        help="use the selected config's local test-output overrides")
    parser.add_argument("--review-session", metavar="PATH",
                        help="read a projectome.neuron-review.v1 JSON identity handoff")
    parser.add_argument("--watch-session", action="store_true",
                        help="watch the session file for later identity events")
    parser.add_argument("--no-autoload", action="store_true",
                        help="do not load soma coordinates automatically")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate and print resolved launch settings without opening the GUI")
    args = parser.parse_args(argv)
    if (args.sample_id is None) != (args.neuron_id is None):
        parser.error("--sample and --neuron must be provided together")
    if args.watch_session and not args.review_session:
        parser.error("--watch-session requires --review-session PATH")
    return parser, args


def _resolve_launch(parser, args):
    """Resolve the selected config and identity after argument validation."""
    try:
        from .config import load as load_config
        config = load_config(args.config)
        direct_identity = (normalize_review_identity(args.sample_id, args.neuron_id)
                           if args.sample_id is not None else None)
        session_event = None
        session_payload = None
        if args.review_session:
            session_event, session_payload = read_review_session(args.review_session)
        if direct_identity and session_event and direct_identity != session_event.identity:
            raise ValueError(
                "--sample/--neuron do not match the identity in --review-session")
        identity_input = session_event.identity if session_event else direct_identity
        auto_override = False if args.no_autoload else None
        if identity_input is None:
            identity, identity_source, effective_auto_load = resolve_gui_launch_defaults(
                config, auto_load=auto_override)
        else:
            identity, _, effective_auto_load = resolve_gui_launch_defaults(
                config, identity_input[0], identity_input[1], auto_override)
            identity_source = "review_session" if session_event else "explicit"
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    return identity, identity_source, effective_auto_load, config, session_event, session_payload


def _initialize_default_config_for_gui(args):
    """Initialize only a valid implicit first launch; explicit and read-only modes stay untouched."""
    if args.config or args.dry_run or args.test:
        return None
    if os.environ.get("VISPA_CONFIG"):
        return None
    from .config import initialize_default_config
    return initialize_default_config()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser, args = _parse_launch_args(argv)
    if args.test:
        os.environ["VISPA_TEST_MODE"] = "1"
    _initialize_default_config_for_gui(args)
    identity, identity_source, effective_auto_load, config, session_event, session_payload = _resolve_launch(parser, args)
    if args.config:
        os.environ["VISPA_CONFIG"] = str(Path(args.config).expanduser().resolve())
    if args.dry_run:
        from .config import config_version_report
        version_report = config_version_report(config)
        output_root, output_root_source = _resolve_output_root(args.config)
        figure_output_root, figure_output_root_source = _resolve_figure_output_root(args.config)
        settings = {
            "vispa_version": version_report["vispa_version"],
            "config_name": version_report["config_name"],
            "config_version": version_report["config_version"],
            "config_sha256": version_report["config_sha256"],
            "test_mode": bool(args.test),
            "sample_id": identity[0],
            "neuron_id": identity[1],
            "identity_source": identity_source,
            "config": str(config["path"]),
            "review_session": session_event.path if session_event else None,
            "watch_session": args.watch_session,
            "auto_load_soma": effective_auto_load,
            "effective_auto_load": effective_auto_load,
            "output_root": output_root,
            "output_root_source": output_root_source,
            "figure_output_root": figure_output_root,
            "figure_output_root_source": figure_output_root_source,
            "default_output_dir": _figure_folder(
                figure_output_root, identity[0], identity[1]),
        }
        if isinstance(session_payload, dict) and isinstance(session_payload.get("source"), dict):
            settings["source"] = {
                key: value for key, value in session_payload["source"].items()
                if key in ("kind", "path", "sha256") and isinstance(value, str)
            }
        print(json.dumps(settings, ensure_ascii=False, indent=2))
        return 0

    if "configure_data_sources" in globals():
        configure_data_sources(args.config)
    root = tk.Tk()
    app = NeuroVisGUI(root, sample_id=identity[0] or None, neuron_id=identity[1] or None,
                      auto_load=effective_auto_load,
                      review_session=session_event,
                      watch_session=args.watch_session,
                      config_path=args.config,
                      auto_fill_on_identity=not args.no_autoload,
                      test_mode=args.test)
    app.identity_source = identity_source
    root.mainloop()
    return 0

if __name__ == "__main__":
    main()
