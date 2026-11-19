"""VisPa entry points for the shared ReMAP cohort progress report.

Version: 1.21.8.dev1 (local/unreleased)
Last updated: 2026-11-18
Change history: ../../CHANGELOG.md
2026-11-18: delegate the saved snapshot report and PNG export to ReMAP.
"""
from __future__ import annotations

from pathlib import Path

from ._version import __version__


def _progress_backend():
    try:
        from remap import cohort_progress
    except ImportError as exc:
        raise RuntimeError(
            "Cohort progress requires ReMAP 0.2.2.dev3 or later. "
            "Launch this checkout with run_vispa.py to use its sibling ReMAP source."
        ) from exc
    return cohort_progress


def build_report(snapshot, cohort=None, *, sample=None):
    """Load the shared data and preserve the VisPa receipt identity."""
    report = _progress_backend().build_report(snapshot, cohort, sample=sample)
    return dict(report, schema="vispa.cohort_progress.v1", vispa_version=__version__)


def make_figure(report):
    return _progress_backend().make_figure(report)


def export_report(report, output, *, dpi=168):
    return _progress_backend().export_report(report, output, dpi=dpi)


def run_progress(args):
    return _progress_backend().run_progress(args, build=build_report)


def open_progress_window(parent, *, log):
    """Select a saved snapshot and preview it in a native VisPa window."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    name = "Cohort progress"
    snapshot = filedialog.askopenfilename(
        parent=parent, title="Select the Progress Manager CSV",
        filetypes=[("Progress CSV", "*.csv")],
    )
    if not snapshot:
        return
    cohort = filedialog.askopenfilename(
        parent=parent, title="Select the matching ReMAP receipt (Cancel to use the CSV only)",
        filetypes=[("ReMAP receipt", "*.json")],
    )
    try:
        report = build_report(snapshot, cohort or None)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        log(name, "failed", error=exc)
        messagebox.showerror(name, str(exc), parent=parent)
        return

    window = tk.Toplevel(parent)
    window.title(f"VisPa {__version__} · {name}")
    width = min(1180, window.winfo_screenwidth() - 60)
    height = min(800, window.winfo_screenheight() - 100)
    window.geometry(f"{width}x{height}")
    window.minsize(min(width, 850), min(height, 600))
    figure = make_figure(report)
    canvas = FigureCanvasTkAgg(figure, master=window)
    canvas.get_tk_widget().pack(fill="both", expand=True)
    toolbar = ttk.Frame(window, padding=(12, 6))
    toolbar.pack(fill="x")
    location = tk.StringVar(value=Path(snapshot).name, master=window)
    ttk.Label(toolbar, textvariable=location).pack(side="left")

    def save():
        filename = filedialog.asksaveasfilename(
            parent=window, title="Save cohort progress chart",
            initialfile="insula_cohort_progress.png", defaultextension=".png",
            filetypes=[("PNG", "*.png")],
        )
        if not filename:
            return
        try:
            outputs = export_report(report, filename)
        except (OSError, ValueError) as exc:
            log(name, "save failed", error=exc)
            messagebox.showerror(name, str(exc), parent=window)
        else:
            location.set(Path(outputs["output"]).name)
            log(name, "saved", **outputs)

    ttk.Button(toolbar, text="Close", command=window.destroy).pack(side="right")
    ttk.Button(toolbar, text="Save PNG…", command=save).pack(side="right", padx=8)
    canvas.draw()
    log(name, "opened", neurons=report["totals"]["atlas_insula"], source=snapshot)
