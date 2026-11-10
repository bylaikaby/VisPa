"""Tk controls for packaged, receipt-backed whole-animal review rendering.

Version: 1.21.7 (local/unreleased)
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
from .data_input_adaptor import list_neurons
from ._version import __version__


GRAPHITE = {
    "page": "#303637", "card": "#414a4c", "field": "#202728",
    "text": "#e4e4dc", "muted": "#c5cecb", "border": "#738183",
    "title": "#c5ddca", "log": "#182021",
}


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
        if values.get("brain_view"):
            command.append("--brain-view")
        command += ["--limit", "1"] if action == "prepare_one_preview" else ["--all"]
        if action == "prepare_one_preview":
            command.append("--dry-run")
        if values["allow_download"]:
            command.append("--allow-download")
        for region in sorted(values.get("regions") or []):
            command += ["--region", region]
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
    from .review_bulk_render import run_folder_name
    from .render_records import animal_receipt_path
    jobs_path = jobs_path.expanduser().resolve(strict=True)
    payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    sample = payload["sample_id"]
    if not isinstance(sample, str) or not sample.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Jobs file has an invalid sample ID")
    digest = hashlib.sha256(jobs_path.read_bytes()).hexdigest()
    root = output_root.expanduser().resolve()
    if payload.get("output_layout") == "sample_neurons_flat":
        return animal_receipt_path(root, sample)
    if payload.get("output_layout") == "sample_neurons":
        return root / sample / "bulk_runs" / run_folder_name(payload, digest) / "batch_receipt.json"
    return root / "batch_receipt.json"


class BulkReviewDialog:
    def __init__(self, parent, *, sample: str, config_path: str | None, log):
        self.parent = parent
        self.log = log
        self.window = tk.Toplevel(parent)
        self.window.title("VisPa · Bulk review")
        self.window.geometry("850x680")
        self.window.minsize(650, 500)
        self.window.configure(bg=GRAPHITE["page"])
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.busy = False
        self._receipt_poll_running = False
        self.values = {}
        self.status = tk.StringVar(value="Ready. Existing completed runs can be opened without rerendering.")
        config = load(config_path)
        resolved = config.get("path") or config_path
        if not resolved:
            raise ValueError("Bulk review needs a saved VisPa profile")
        self.config_path = str(Path(resolved).resolve(strict=True))
        self._config_sha = hashlib.sha256(Path(self.config_path).read_bytes()).hexdigest()[:8]
        self._jobs_manual = False
        cache = Path(config["defaults"]["cache_root"]) / "swc_raw"
        jobs = (Path(config["defaults"]["cache_root"]) / "review_jobs" /
                f"{sample or 'sample'}_review_flat_v{__version__}_{self._config_sha}_bv_jobs.json")
        defaults = {"sample": sample, "config": str(resolved), "csv": "",
                    "raw_roots": "", "source_receipt": "", "cache": str(cache),
                    "jobs": str(jobs),
                    "output": str(config["visual_toolkit"]["figure_output_root"])}
        style = ttk.Style(self.window)
        style.configure("Bulk.TFrame", background=GRAPHITE["page"])
        style.configure("Bulk.TLabel", background=GRAPHITE["page"],
                        foreground=GRAPHITE["text"], font=("Segoe UI", 9))
        style.configure("Bulk.Title.TLabel", background=GRAPHITE["page"],
                        foreground=GRAPHITE["title"], font=("Segoe UI", 11, "bold"))
        style.configure("Bulk.TButton", background=GRAPHITE["card"],
                        foreground=GRAPHITE["text"], padding=5)
        style.map("Bulk.TButton", background=[("active", "#465052")])
        style.configure("Bulk.TEntry", fieldbackground=GRAPHITE["field"],
                        foreground=GRAPHITE["text"], bordercolor=GRAPHITE["border"])
        style.configure("Bulk.TRadiobutton", background=GRAPHITE["page"],
                        foreground=GRAPHITE["text"])
        style.configure("Bulk.TCheckbutton", background=GRAPHITE["page"],
                        foreground=GRAPHITE["text"])
        canvas = tk.Canvas(self.window, bg=GRAPHITE["page"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.window, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        form = ttk.Frame(canvas, padding=12, style="Bulk.TFrame")
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(form_window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-1 if event.delta > 0 else 1, "units"))
        self.values["source"] = tk.StringVar(value="catalog")
        self.values["allow_download"] = tk.BooleanVar(value=False)
        self.values["brain_view"] = tk.BooleanVar(value=True)
        ttk.Label(form, text="One animal · four core review figures plus SWC Brain View",
                  style="Bulk.Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.region_labels = ()
        self.selected_regions = set()
        self._region_generation = 0
        self._region_after = None
        self._regions_loading = False
        self._region_error = None
        self._jobs_root = jobs.parent
        labels = [("sample", "Animal / sample ID", False),
                  ("output", "Figure output root · active profile", False),
                  ("config", "Active VisPa profile", False),
                  ("cache", "Managed raw cache · active profile", False),
                  ("jobs", "Prepared jobs JSON", True)]
        advanced = ttk.Frame(form, style="Bulk.TFrame")
        for row, (key, label, browse) in enumerate(labels, start=1):
            section = form if key in {"sample", "output"} else advanced
            visual_row = 1 if key == "sample" else 3 if key == "output" else row
            ttk.Label(section, text=label, style="Bulk.TLabel").grid(row=visual_row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=defaults[key])
            self.values[key] = var
            ttk.Entry(section, textvariable=var, style="Bulk.TEntry",
                      state="normal" if key == "sample" else "readonly").grid(
                          row=visual_row, column=1, sticky="ew", padx=8, pady=4)
            if browse:
                ttk.Button(section, text="Browse…", style="Bulk.TButton",
                           command=lambda k=key: self._browse(k)).grid(row=visual_row, column=2)
        form.columnconfigure(1, weight=1)
        advanced.columnconfigure(1, weight=1)
        ttk.Label(form, text="Atlas regions", style="Bulk.TLabel").grid(
            row=2, column=0, sticky="w", pady=4)
        self.region_button = tk.Menubutton(form, text="All regions ▾", relief="raised",
                                           bg=GRAPHITE["card"], fg=GRAPHITE["text"],
                                           activebackground="#465052", activeforeground=GRAPHITE["text"])
        self.region_button.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        self.region_menu = tk.Menu(self.region_button, tearoff=False,
                                   bg=GRAPHITE["card"], fg=GRAPHITE["text"],
                                   activebackground="#465052", activeforeground=GRAPHITE["text"])
        self.region_button.configure(menu=self.region_menu)
        self.values["sample"].trace_add("write", lambda *_: self._schedule_region_load())
        self._load_regions()
        ttk.Label(advanced, text="Source identities and raw SWC roots follow the active profile.",
                  style="Bulk.TLabel").grid(row=9, column=0, columnspan=3,
                                               sticky="w", pady=(7, 10))
        advanced_toggle = ttk.Button(form, text="Advanced ▸", style="Bulk.TButton")
        advanced_toggle.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 8))
        def toggle_advanced():
            if advanced.winfo_manager():
                advanced.grid_remove()
                advanced_toggle.configure(text="Advanced ▸")
            else:
                advanced.grid()
                advanced_toggle.configure(text="Advanced ▾")
        advanced_toggle.configure(command=toggle_advanced)
        advanced.grid(row=9, column=0, columnspan=3, sticky="ew", pady=5)
        advanced.grid_remove()
        actions = ttk.Frame(form, style="Bulk.TFrame")
        actions.grid(row=5, column=0, columnspan=3, sticky="w", pady=8)
        self.buttons = []
        ttk.Checkbutton(
            actions, text="SWC Brain View shot", variable=self.values["brain_view"],
            style="Bulk.TCheckbutton", command=self._review_options_changed
        ).pack(side="left", padx=(0, 12))
        for label, action in (("Check one", "check_one"),
                              ("Run / resume all", "run_resume_all")):
            button = ttk.Button(actions, text=label, style="Bulk.TButton",
                                command=lambda a=action: self._launch(a))
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)
        ttk.Button(actions, text="Open results", style="Bulk.TButton",
                   command=self._open_results).pack(side="left")
        result_actions = ttk.Frame(advanced, style="Bulk.TFrame")
        result_actions.grid(row=12, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Button(result_actions, text="Open process log", style="Bulk.TButton",
                   command=self._open_receipt).pack(side="left", padx=(0, 6))
        ttk.Button(result_actions, text="Choose existing jobs…", style="Bulk.TButton",
                   command=lambda: self._browse("jobs")).pack(side="left")
        ttk.Label(form, textvariable=self.status, wraplength=740, style="Bulk.TLabel").grid(row=6, column=0, columnspan=3, sticky="w", pady=5)
        self.receipt_status = tk.StringVar(value="No batch receipt selected.")
        ttk.Label(form, textvariable=self.receipt_status, wraplength=740, style="Bulk.TLabel").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=5)
        self.details = tk.Text(form, height=12, wrap="word", bg=GRAPHITE["log"],
                               fg=GRAPHITE["text"], insertbackground=GRAPHITE["text"],
                               highlightbackground=GRAPHITE["border"])
        self.details.grid(row=8, column=0, columnspan=3, sticky="nsew")
        self._poll_receipt()

    def _browse(self, key):
        if key != "jobs":
            return
        selected = filedialog.askopenfilename(parent=self.window)
        if selected:
            try:
                self._validate_jobs(Path(selected), self._snapshot(), require_exists=True,
                                    view_only=True)
                self.values["jobs"].set(selected)
                self._jobs_manual = True
            except (OSError, ValueError, KeyError, TypeError) as exc:
                messagebox.showerror("Bulk review", f"Could not use jobs: {exc}", parent=self.window)

    def _schedule_region_load(self):
        if self._region_after is not None:
            self.window.after_cancel(self._region_after)
        self._region_generation += 1
        self._regions_loading = True
        self.selected_regions.clear()
        self._jobs_manual = False
        self.region_button.configure(text="Loading atlas regions…")
        self._region_after = self.window.after(300, self._load_regions)

    def _load_regions(self):
        """Read exact catalog atlas labels without blocking the Tk event loop."""
        self._region_after = None
        self._region_generation += 1
        generation = self._region_generation
        sample = self.values["sample"].get().strip()
        self._regions_loading = True
        self._region_error = None
        self.selected_regions.clear()
        self.values["jobs"].set(str(self._default_jobs_path(sample, ())))
        self.region_button.configure(text="Loading atlas regions…")
        if not sample:
            self._regions_loading = False
            self.region_button.configure(text="All regions ▾")
            return

        def worker():
            try:
                rows = list_neurons(sample, load(self.config_path))["rows"]
                labels = sorted({str(row.get("portal_region") or "").strip()
                                 for row in rows if str(row.get("portal_region") or "").strip()})
                error = None
            except (OSError, ValueError, KeyError, TypeError) as exc:
                labels, error = [], str(exc)
            try:
                self.parent.after(0, lambda: self._show_regions(generation, labels, error))
            except tk.TclError:
                pass
        threading.Thread(target=worker, name="vispa-bulk-regions", daemon=True).start()

    def _show_regions(self, generation, labels, error):
        if generation != self._region_generation or not self.window.winfo_exists():
            return
        self.region_labels = tuple(labels)
        self._regions_loading = False
        self._region_error = error
        self.region_menu.delete(0, "end")
        self._region_vars = {}
        all_var = tk.BooleanVar(value=True)
        def select_all():
            for var in self._region_vars.values():
                var.set(False)
            self.selected_regions.clear()
            all_var.set(True)
            self._region_summary()
        self.region_menu.add_checkbutton(label="All regions", variable=all_var,
                                         command=select_all)
        if labels:
            self.region_menu.add_separator()
        for label in labels:
            var = tk.BooleanVar(value=False)
            self._region_vars[label] = var
            def select_region(name=label, selected=var):
                if selected.get():
                    self.selected_regions.add(name)
                else:
                    self.selected_regions.discard(name)
                all_var.set(not self.selected_regions)
                self._region_summary()
            self.region_menu.add_checkbutton(label=label, variable=var,
                                             command=select_region)
        self.region_button.configure(text="All regions ▾")
        if error:
            self.status.set(f"Atlas regions unavailable: {error}")

    def _region_summary(self):
        selected = sorted(self.selected_regions)
        self._jobs_manual = False
        self.values["jobs"].set(str(self._default_jobs_path(
            self.values["sample"].get().strip(), selected)))
        self.region_button.configure(text=("All regions ▾" if not selected else
                                           ", ".join(selected[:2]) +
                                           (f" +{len(selected) - 2} more ▾" if len(selected) > 2 else " ▾")))

    def _review_options_changed(self):
        self._region_summary()

    def _default_jobs_path(self, sample, regions):
        suffix = ("" if not regions else "_" + hashlib.sha256(
            json.dumps(sorted(regions), ensure_ascii=False).encode("utf-8")).hexdigest()[:8])
        values = getattr(self, "values", {})
        brain_view_var = values.get("brain_view")
        brain_view = "_bv" if brain_view_var and brain_view_var.get() else ""
        return self._jobs_root / (
            f"{sample or 'sample'}_review_flat_v{__version__}_{self._config_sha}"
            f"{brain_view}{suffix}_jobs.json")

    @staticmethod
    def _validate_jobs(jobs: Path, values: dict, *, require_exists=False,
                       view_only=False):
        if not jobs.is_file():
            if require_exists:
                raise FileNotFoundError(jobs)
            return
        payload = json.loads(jobs.read_text(encoding="utf-8"))
        declared = Path(payload["vispa_config"])
        if not declared.is_absolute():
            declared = jobs.parent / declared
        if declared.resolve() != Path(values["config"]).resolve():
            raise ValueError("Prepared jobs use another profile; keep the active VisPa profile")
        if payload.get("sample_id") != values["sample"]:
            raise ValueError("Prepared jobs use another animal/sample")
        if not view_only and payload.get("output_layout") != "sample_neurons_flat":
            raise ValueError("Prepared jobs use an older output layout; prepare new flat-layout jobs")
        frozen_regions = sorted((payload.get("region_filter") or {}).get("labels") or [])
        if frozen_regions != sorted(values.get("regions") or []):
            raise ValueError("Prepared jobs use another atlas region selection")
        frozen_roles = payload.get("review_roles", [
            "Soma", "Context", "Sagittal", "TrioPlot"])
        requested_brain_view = bool(values.get("brain_view"))
        if ("SWC3D" in frozen_roles) != requested_brain_view:
            raise ValueError("Prepared jobs use another SWC Brain View selection")
        if (payload.get("figure_output_root") and
                Path(payload["figure_output_root"]).resolve() != Path(values["output"]).resolve()):
            raise ValueError("Prepared jobs use another figure output root")
        if (not view_only and payload.get("cache_root") and
                Path(payload["cache_root"]).resolve() != Path(values["cache"]).resolve()):
            raise ValueError("Prepared jobs use another managed raw cache")
        if not view_only and payload.get("vispa_config_sha256") and (
                hashlib.sha256(Path(values["config"]).read_bytes()).hexdigest()
                != payload["vispa_config_sha256"]):
            raise ValueError("Prepared jobs use an older profile revision; prepare new jobs")

    def _close(self):
        if self.busy:
            messagebox.showinfo("Bulk review", "Wait for the current command to finish before closing.",
                                parent=self.window)
            return
        self.window.destroy()

    def _snapshot(self):
        config = load(self.config_path)
        current_sha = hashlib.sha256(Path(self.config_path).read_bytes()).hexdigest()[:8]
        if current_sha != self._config_sha:
            self._config_sha = current_sha
            self._jobs_root = Path(config["defaults"]["cache_root"]) / "review_jobs"
            if not self._jobs_manual:
                self.values["jobs"].set(str(self._default_jobs_path(
                    self.values["sample"].get().strip(), self.selected_regions)))
        if Path(config.get("path") or self.config_path).resolve() != Path(self.config_path):
            raise ValueError("Active VisPa profile changed while bulk review was open")
        values = {key: value.get() for key, value in self.values.items()}
        values.update({
            "config": self.config_path,
            "output": str(config["visual_toolkit"]["figure_output_root"]),
            "cache": str(Path(config["defaults"]["cache_root"]) / "swc_raw"),
            "source": "catalog", "csv": "", "raw_roots": "",
            "source_receipt": "", "allow_download": False,
            "regions": sorted(self.selected_regions),
        })
        self.values["config"].set(values["config"])
        self.values["output"].set(values["output"])
        self.values["cache"].set(values["cache"])
        return values

    def _launch(self, action):
        if self.busy:
            return
        if self._regions_loading or self._region_error:
            messagebox.showerror("Bulk review", self._region_error or
                                 "Wait for atlas regions to load.", parent=self.window)
            return
        try:
            values = self._snapshot()
            self._validate_jobs(Path(values["jobs"]), values)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Bulk review", str(exc), parent=self.window)
            return
        if action in {"check_one", "run_resume_all"}:
            self._launch_guided(action, values)
            return
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

    def _launch_guided(self, action, values):
        """Run the small visible path through the existing validated commands."""
        if action == "run_resume_all" and not messagebox.askyesno(
                "Bulk review", "Prepare any missing jobs and render or resume all neurons?",
                parent=self.window):
            return
        self.busy = True
        for button in self.buttons:
            button.state(["disabled"])
        self.status.set("Checking one neuron…" if action == "check_one" else "Preparing or resuming all…")
        self.details.delete("1.0", "end")
        self.log("Bulk review", "requested", action=action, sample=values["sample"])

        def worker():
            try:
                jobs = Path(values["jobs"]).expanduser()
                steps = ((["render_one_preview", "render_one"] if jobs.is_file() else
                          ["prepare_one_preview", "prepare_all", "render_one"])
                         if action == "check_one" else
                         (["resume_all"] if jobs.is_file() else ["prepare_all", "resume_all"]))
                for step in steps:
                    command = bulk_command(step, values)
                    self.parent.after(0, lambda s=step, c=command: self._show_command(s, c))
                    process = subprocess.run(command, text=True, capture_output=True,
                                             encoding="utf-8", errors="replace", check=False,
                                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    output = process.stdout.strip() or process.stderr.strip()
                    self.parent.after(0, lambda o=output, s=step:
                                      self.details.insert("end", f"{s}: {o}\n"))
                    if process.returncode:
                        self.parent.after(0, lambda s=step, c=process.returncode, o=output:
                                          self._finish(s, c, o, process.stderr))
                        return
                self.parent.after(0, lambda: self._finish(action, 0, "", ""))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.parent.after(0, lambda error=str(exc): self._finish(action, 2, error, ""))
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
        values = self._snapshot()
        self._validate_jobs(Path(values["jobs"]), values, require_exists=True,
                            view_only=True)
        return batch_receipt_path(Path(values["jobs"]), Path(values["output"]))

    def _open_results(self):
        self._open_selected("results")

    def _open_receipt(self):
        self._open_selected("receipt")

    def _open_selected(self, kind):
        try:
            values = self._snapshot()
            self._validate_jobs(Path(values["jobs"]), values, require_exists=True,
                                view_only=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._show_open_error(str(exc))
            return
        jobs = Path(values["jobs"])
        output = Path(values["output"])
        def worker():
            try:
                receipt = batch_receipt_path(jobs, output)
                path = (receipt.parent.parent.parent / "neurons"
                        if kind == "results" and receipt.parent.parent.name == "bulk_runs" else
                        receipt.parent / "neurons" if kind == "results" and
                        receipt.name == "process_log.json" else
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
        try:
            values = self._snapshot()
            self._validate_jobs(Path(values["jobs"]), values, view_only=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._receipt_poll_running = False
            self.receipt_status.set(f"Prepared jobs need review: {exc}")
            self.window.after(1500, self._poll_receipt)
            return
        jobs = values["jobs"]
        output = values["output"]
        def read_receipt():
            try:
                path = batch_receipt_path(Path(jobs), Path(output))
                if path.is_file():
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if path.name == "process_log.json":
                        batch = record.get("current_batch") or {}
                        completed = batch.get("completed", 0)
                        ready = batch.get("requested", "?")
                        status = batch.get("status", "unknown")
                    else:
                        completed = len(record.get("completed") or [])
                        ready = record.get("requested", "?")
                        status = record.get("status", "unknown")
                    message = f"Process log: {completed}/{ready} · {status} · {path}"
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
