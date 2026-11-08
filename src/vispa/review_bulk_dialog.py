"""Tk controls for packaged, receipt-backed whole-animal review rendering.

Version: 1.21.0 (local/unreleased)
Last updated: 2026-11-08
Change history: ../../CHANGELOG.md
Status: candidate
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .config import load


def bulk_command(action: str, values: dict) -> list[str]:
    """Build an explicit, bounded CLI request from validated dialog values."""
    if action not in {"prepare_one_preview", "prepare_all", "render_one_preview",
                      "render_one", "render_all", "resume_all"}:
        raise ValueError("Unknown bulk review action")
    for key in ("config", "jobs", "output", "cache"):
        if not values[key].strip():
            raise ValueError(f"{key} path is empty")
    sample = values["sample"].strip()
    if not sample or not sample.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Sample ID must contain only letters, digits, _ or -")
    config = Path(values["config"]).expanduser().resolve(strict=True)
    if not config.is_file():
        raise ValueError("Config must be an existing file")
    jobs = Path(values["jobs"]).expanduser().resolve()
    output = Path(values["output"]).expanduser().resolve()
    if not jobs.name.lower().endswith(".json"):
        raise ValueError("Jobs path must end in .json")
    if action.startswith("prepare"):
        cache = Path(values["cache"]).expanduser().resolve()
        command = [sys.executable, "-m", "vispa.review_bulk_prepare",
                   "--config", str(config), "--sample", sample,
                   "--cache-root", str(cache), "--output-jobs", str(jobs)]
        if values["source"] == "catalog":
            command.append("--catalog")
        elif values["source"] == "csv":
            csv = Path(values["csv"]).expanduser().resolve(strict=True)
            if not csv.is_file():
                raise ValueError("Identity CSV must be an existing file")
            command += ["--identities", str(csv)]
        else:
            raise ValueError("Choose a catalog or identity CSV")
        roots = [item.strip() for item in values["raw_roots"].split(";") if item.strip()]
        for root in roots:
            path = Path(root).expanduser().resolve(strict=True)
            if not path.is_dir():
                raise ValueError(f"Raw root is not a directory: {path}")
            command += ["--raw-root", str(path)]
        if values["source_receipt"].strip():
            receipt = Path(values["source_receipt"]).expanduser().resolve(strict=True)
            command += ["--source-receipt", str(receipt)]
        command += ["--limit", "1"] if action == "prepare_one_preview" else ["--all"]
        if action == "prepare_one_preview":
            command.append("--dry-run")
        if values["allow_download"]:
            command.append("--allow-download")
    else:
        if not jobs.is_file():
            raise ValueError("Choose an existing prepared jobs JSON")
        payload = json.loads(jobs.read_text(encoding="utf-8"))
        if payload.get("sample_id") != sample:
            raise ValueError("Dialog sample differs from prepared jobs; choose jobs again")
        declared_config = Path(payload["vispa_config"])
        if not declared_config.is_absolute():
            declared_config = jobs.parent / declared_config
        if declared_config.resolve() != config:
            raise ValueError("Dialog profile differs from prepared jobs; choose jobs again")
        command = [sys.executable, "-m", "vispa.review_bulk_render",
                   "--jobs", str(jobs), "--output-root", str(output)]
        command += ["--limit", "1"] if action in {"render_one_preview", "render_one"} else ["--all"]
        if action == "render_one_preview":
            command.append("--dry-run")
        if action in {"render_all", "resume_all"}:
            command.append("--resume")
    return command


def batch_receipt_path(jobs_path: Path, output_root: Path) -> Path:
    jobs_path = jobs_path.expanduser().resolve(strict=True)
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    sample = payload["sample_id"]
    if not isinstance(sample, str) or not sample.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Jobs file has an invalid sample ID")
    digest = hashlib.sha256(jobs_path.read_bytes()).hexdigest()[:12]
    root = output_root.expanduser().resolve()
    if payload.get("output_layout") == "sample_neurons":
        return root / sample / "bulk_runs" / f"bulk_{digest}" / "batch_receipt.json"
    return root / "batch_receipt.json"


class BulkReviewDialog:
    def __init__(self, parent, *, sample: str, config_path: str | None, log):
        self.parent = parent
        self.log = log
        self.window = tk.Toplevel(parent)
        self.window.title("VisPa · Bulk review")
        self.window.geometry("850x710")
        self.window.minsize(750, 600)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.busy = False
        self._receipt_poll_running = False
        self.values = {}
        config = load(config_path)
        resolved = config.get("path") or config_path
        if not resolved:
            raise ValueError("Bulk review needs a saved VisPa profile")
        cache = Path(config["defaults"]["cache_root"]) / "review_bulk_raw"
        jobs = Path.home() / "VisPa" / "bulk_jobs" / f"{sample or 'sample'}_review_jobs.json"
        defaults = {"sample": sample, "config": str(resolved), "csv": "",
                    "raw_roots": "", "source_receipt": "", "cache": str(cache),
                    "jobs": str(jobs),
                    "output": str(config["visual_toolkit"]["figure_output_root"])}
        form = ttk.Frame(self.window, padding=12)
        form.pack(fill="both", expand=True)
        self.values["source"] = tk.StringVar(value="catalog")
        self.values["allow_download"] = tk.BooleanVar(value=False)
        ttk.Label(form, text="One animal · four candidate review figures per neuron",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        labels = [("sample", "Sample ID", False), ("config", "VisPa profile", True),
                  ("csv", "Identity CSV", True), ("raw_roots", "Raw source roots (; separated)", False),
                  ("source_receipt", "Source hash receipt", True),
                  ("cache", "Managed raw cache", True), ("jobs", "Prepared jobs JSON", True),
                  ("output", "Figure output root", True)]
        for row, (key, label, browse) in enumerate(labels, start=1):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=defaults[key])
            self.values[key] = var
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            if browse:
                ttk.Button(form, text="Browse…", command=lambda k=key: self._browse(k)).grid(row=row, column=2)
        form.columnconfigure(1, weight=1)
        options = ttk.Frame(form)
        options.grid(row=9, column=0, columnspan=3, sticky="w", pady=(7, 10))
        ttk.Label(options, text="Identities:").pack(side="left")
        ttk.Radiobutton(options, text="Live/configured catalog", variable=self.values["source"],
                        value="catalog").pack(side="left", padx=8)
        ttk.Radiobutton(options, text="CSV", variable=self.values["source"], value="csv").pack(side="left")
        ttk.Checkbutton(options, text="Allow raw SWC download", variable=self.values["allow_download"]).pack(side="left", padx=18)
        ttk.Label(form, text="First preview one, then prepare all. Rendering writes to <figure root>/<sample>/neurons/<ID>/bulk_<jobs hash>.",
                  wraplength=800).grid(row=10, column=0, columnspan=3, sticky="w", pady=4)
        actions = ttk.Frame(form)
        actions.grid(row=11, column=0, columnspan=3, sticky="w", pady=8)
        buttons = [("Preview one", "prepare_one_preview"), ("Prepare all", "prepare_all"),
                   ("Render one dry run", "render_one_preview"), ("Render one", "render_one"),
                   ("Render all", "render_all"), ("Resume all", "resume_all")]
        self.buttons = []
        for label, action in buttons:
            button = ttk.Button(actions, text=label, command=lambda a=action: self._launch(a))
            button.pack(side="left", padx=(0, 6))
            self.buttons.append(button)
        result_actions = ttk.Frame(form)
        result_actions.grid(row=12, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Button(result_actions, text="Open results", command=self._open_results).pack(side="left", padx=(0, 6))
        ttk.Button(result_actions, text="Open batch receipt", command=self._open_receipt).pack(side="left", padx=(0, 6))
        ttk.Button(result_actions, text="Choose existing jobs…", command=lambda: self._browse("jobs")).pack(side="left")
        self.status = tk.StringVar(value="Ready. Existing completed runs can be opened without rerendering.")
        ttk.Label(form, textvariable=self.status, wraplength=800).grid(row=13, column=0, columnspan=3, sticky="w", pady=5)
        self.receipt_status = tk.StringVar(value="No batch receipt selected.")
        ttk.Label(form, textvariable=self.receipt_status, wraplength=800).grid(
            row=15, column=0, columnspan=3, sticky="w", pady=5)
        self.details = tk.Text(form, height=13, wrap="word")
        self.details.grid(row=14, column=0, columnspan=3, sticky="nsew")
        form.rowconfigure(14, weight=1)
        self._poll_receipt()

    def _browse(self, key):
        directory = key in {"cache", "output"}
        selected = (filedialog.askdirectory(parent=self.window) if directory else
                    filedialog.askopenfilename(parent=self.window))
        if selected:
            self.values[key].set(selected)
            if key == "jobs":
                try:
                    payload = json.loads(Path(selected).read_text(encoding="utf-8"))
                    config = Path(payload["vispa_config"])
                    if not config.is_absolute():
                        config = Path(selected).parent / config
                    self.values["sample"].set(payload["sample_id"])
                    self.values["config"].set(str(config.resolve()))
                    if payload.get("cache_root"):
                        self.values["cache"].set(str(payload["cache_root"]))
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    messagebox.showerror("Bulk review", f"Could not read jobs: {exc}", parent=self.window)

    def _close(self):
        if self.busy:
            messagebox.showinfo("Bulk review", "Wait for the current command to finish before closing.",
                                parent=self.window)
            return
        self.window.destroy()

    def _snapshot(self):
        return {key: value.get() for key, value in self.values.items()}

    def _launch(self, action):
        if self.busy:
            return
        values = self._snapshot()
        if action in {"prepare_all", "render_all", "resume_all"}:
            verb = {"prepare_all": "Prepare all selected neurons?",
                    "render_all": "Verify completed neurons and render every remaining prepared neuron?",
                    "resume_all": "Verify completed neurons and retry incomplete ones?"}[action]
            if not messagebox.askyesno("Bulk review", verb, parent=self.window):
                return
        self.busy = True
        for button in self.buttons:
            button.state(["disabled"])
        self.status.set(f"Running {action.replace('_', ' ')}…")
        self.details.delete("1.0", "end")
        self.log("Bulk review", "requested", action=action, sample=values["sample"])

        def worker():
            try:
                command = bulk_command(action, values)
                try:
                    self.parent.after(0, lambda: self._show_command(action, command))
                except tk.TclError:
                    return
                process = subprocess.run(command, text=True, capture_output=True, encoding="utf-8",
                                         errors="replace", check=False,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                result = process.stdout.strip() or process.stderr.strip()
                try:
                    self.parent.after(0, lambda: self._finish(action, process.returncode, result, process.stderr))
                except tk.TclError:
                    pass
            except (OSError, ValueError, KeyError, TypeError) as exc:
                try:
                    self.parent.after(0, lambda error=str(exc): self._finish(action, 2, error, ""))
                except tk.TclError:
                    pass
        threading.Thread(target=worker, name="vispa-bulk-review", daemon=True).start()

    def _show_command(self, action, command):
        if self.window.winfo_exists():
            self.details.insert("end", subprocess.list2cmdline(command) + "\n")
            self.log("Bulk review", "start", action=action, command=command)

    def _finish(self, action, code, result, stderr):
        if not self.window.winfo_exists():
            return
        self.busy = False
        for button in self.buttons:
            button.state(["!disabled"])
        self.details.insert("end", result + ("\n" + stderr if stderr else "") + "\n")
        self.details.see("end")
        summary = f"{action.replace('_', ' ')}: {'completed' if code == 0 else 'failed/partial'} (exit {code})"
        if code and ("vispa_version" in result or "VisPa version" in result):
            summary += " · software version differs; existing figures remain viewable"
        self.status.set(summary)
        self.log("Bulk review", "finished" if code == 0 else "failed", action=action, exit_code=code)

    def _receipt(self):
        return batch_receipt_path(Path(self.values["jobs"].get()), Path(self.values["output"].get()))

    def _open_results(self):
        self._open_selected("results")

    def _open_receipt(self):
        self._open_selected("receipt")

    def _open_selected(self, kind):
        jobs = Path(self.values["jobs"].get())
        output = Path(self.values["output"].get())
        def worker():
            try:
                receipt = batch_receipt_path(jobs, output)
                path = (receipt.parent.parent.parent / "neurons"
                        if kind == "results" and receipt.parent.name.startswith("bulk_")
                        and receipt.parent.parent.name == "bulk_runs" else
                        receipt.parent if kind == "results" else receipt)
                if path.exists():
                    os.startfile(str(path))
                else:
                    raise FileNotFoundError(path)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                try:
                    self.parent.after(0, lambda error=str(exc): self._show_open_error(error))
                except tk.TclError:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def _show_open_error(self, error):
        if self.window.winfo_exists():
            messagebox.showerror("Bulk review", error, parent=self.window)

    def _poll_receipt(self):
        if not self.window.winfo_exists():
            return
        if self._receipt_poll_running:
            self.window.after(1500, self._poll_receipt)
            return
        self._receipt_poll_running = True
        jobs = self.values["jobs"].get()
        output = self.values["output"].get()
        def read_receipt():
            try:
                path = batch_receipt_path(Path(jobs), Path(output))
                if path.is_file():
                    record = json.loads(path.read_text(encoding="utf-8"))
                    completed = record.get("completed") or []
                    ready = record.get("requested", "?")
                    status = record.get("status", "unknown")
                    message = f"Run receipt: {len(completed)}/{ready} · {status} · {path}"
                    self.parent.after(0, lambda: self._show_receipt_status(message))
            except (OSError, ValueError, KeyError, TypeError, tk.TclError):
                pass
            finally:
                try:
                    self.parent.after(0, lambda: setattr(self, "_receipt_poll_running", False))
                except tk.TclError:
                    pass
        threading.Thread(target=read_receipt, name="vispa-bulk-progress", daemon=True).start()
        self.window.after(1500, self._poll_receipt)

    def _show_receipt_status(self, message):
        if self.window.winfo_exists():
            self.receipt_status.set(message)
