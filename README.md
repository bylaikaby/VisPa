# VisPa — Visual Projectome Analysis tool

Primary standalone development workspace: `D:/VisPa`. Package/distribution: `vispa`; commands: `vispa`, `vispa-gui`. Existing `Visual_toolkit` imports/class and `visual-toolkit` commands remain compatibility aliases.

`VISPA_CONFIG`, `VISPA_PYTHON`, `VISPA_WHEELHOUSE` take precedence over their `VISUAL_TOOLKIT_*` counterparts; configuration falls back to `PROJECTOME_DATASETS`. Legacy per-user VisualToolkit config/cache/output discovery and `visual_toolkit` settings key remain supported unchanged. Existing `visual-toolkit.*.v1` schemas retain their wire identity. No existing config/cache/outputs are moved. Use a fresh environment: overlapping `visual-toolkit` distribution ownership is rejected by the installer.

Legacy leaf-module imports resolve to the same primary module objects and settings state; the legacy GL parent remains a state-free namespace. Optional OpenGL remains lazy. `python -m vispa` and `python -m Visual_toolkit` are supported, as are their GUI module launchers. The old class name aliases `VisPa`, without a second implementation.

New standalone run receipts, builds and candidate outputs live under `D:/VisPa/work/`. The living project journal remains `D:/projectome_analysis/docs/project_note.md`. Existing projectome receipts remain historical evidence; external scientific data/cache paths remain explicit configuration.

## Current operator guide

VisPa renders local macaque microscopy arrays into soma and context review figures. The source tree is packaged independently from projectome; the projectome checkout can connect its cohort scripts and configured lab data through the provider and configuration interfaces described below.

This checkout is **1.11.0.dev1, local and unreleased**. It preserves the existing rendering and source-verification algorithms. The DS00 sagittal panel retains its two documented axis hypotheses and its manifest, hash, geometry, and source checks; those hypotheses remain candidates pending independent anatomical validation. No study data, lab configuration, or private source tree is included. `extraction_manifest.json` records the historical extraction snapshot; today's build, installer selection and validation hashes are recorded in the shared project receipt.

## Quick start (Windows)

1. Clone from GitHub (first time only):

   ```powershell
   gh repo clone bylaikaby/VisPa D:\VisPa
   cd D:\VisPa
   ```

2. Install from the checkout:

   ```powershell
   .\install.cmd -Source
   ```

3. The GUI opens. A **VisPa** shortcut is added to the desktop for later use.

The installer defaults to the code in the current checkout and installs the full `[3d]` stack. If the repo is already cloned, only step 2 is needed. Pass `-Wheel PATH` to install a built wheel explicitly; `-Wheel` and `-Source` cannot be combined.

If the config is not set:

```powershell
.\install.cmd -Config C:\data\visual_toolkit_config.yaml
```

Offline / no download:

```powershell
.\install.cmd -Wheel C:\path\to\vispa-1.11.0.dev1-py3-none-any.whl -Wheelhouse C:\path\to\wheelhouse
```

Preview only:

```powershell
.\install.cmd -DryRun
```

Uninstall:

```powershell
vispa install-path --remove
Remove-Item -Recurse "$env:LOCALAPPDATA\VisPa\venv"
```

## Using the GUI

1. Enter a Sample ID and Neuron ID, or click **Neuron list** to choose one.
2. Click **Load & Auto-Fill Soma**.
3. Click **Render**; the output folder is shown in **Saving**.
4. Use **3D brain view** and **fnt-tracer** for the 3D and tracing views.

## Manual install

Use Python 3.10 or newer in a dedicated virtual environment; do not install into the projectome analysis interpreter. Create `.venv` with `py -3 -m venv .venv`, install the core with `.\.venv\Scripts\python.exe -m pip install .`, and add the full review/3D stack with `.\.venv\Scripts\python.exe -m pip install ".[3d]"`. The legacy SSH fallback is manual: `.\.venv\Scripts\python.exe -m pip install paramiko`. A wheel cannot embed third-party distributions; for offline setup, build a wheelhouse once with `pip download "vispa[3d]" -d wheelhouse` and install with `pip install --no-index --find-links wheelhouse "vispa[3d]"`. Run `vispa install-path` to expose the commands. `python -m build` creates distributions when the `build` tool is installed; `python -m unittest discover -s tests -v` runs the package checks.

The projectome main environment remains Python 3.10. On this machine, the standalone worker uses a full Windows x64 CPython 3.13.13 virtual environment at `.venv`, created from the neutral Miniconda base; `pyvenv.cfg` sets `include-system-site-packages = false`. Install its exact core plus TIFF, NIfTI and YAML dependency set from `requirements-runtime-win-py313.lock` with `& '.\.venv\Scripts\python.exe' -m pip install --require-hashes -r requirements-runtime-win-py313.lock`. To add the legacy OpenGL viewer, install both locks together by adding `-r requirements-legacy-gl-win-py313.lock` to that command. SSH dependencies are outside these locks. `pyproject.toml` keeps general package requirements, and this verification does not establish broader minimum or maximum supported versions.

The headless operator is `vispa render`. It accepts one local `.npy` array in ZYX or YX order, a declared soma coordinate, origin, voxel spacing, role, and output directory. The three coordinate triples use XYZ micrometres. TIFF, NIfTI, SSH, and YAML extras remain available to backend and GUI workflows. The first run should use `--dry-run`, which resolves the inputs, settings, output PNG and receipt without creating directories, reading image pixels, or accessing a source. A real run writes the PNG and its JSON receipt and refuses to overwrite either.

```text
vispa render --input cube.npy --sample sample-01 --neuron 0007 --soma 120 240 30 --origin 0 0 0 --resolution 0.65 0.65 3 --coordinate-frame sample-native-XYZ --role soma --output-dir review --dry-run
```

Use `--role context` for the 5 µm style. `--set PATH=VALUE` overrides review settings; scalar values and numeric sequences are supported, such as `--set figure.panel_dpi=400` or `--set soma_window.cubes_xy_steps=1.5,1.25,1`. Unknown keys, out-of-range values and invalid combinations fail before changing global settings. Run `vispa settings` to print each setting's default, current value, valid range and effect as JSON. Python callers can use `review_settings_schema()` and pass a mapping or a list of `PATH=VALUE` strings to `apply_setting_overrides()`. The single-panel review figure includes the image and target marker legend and labels the displayed plane as native X/Y. The cyan target box and cross mark the supplied coordinate; they do not validate anatomy, orientation, or laterality. The labeled single-panel CLI review reserves font-measured clearance between its axes and shared legend; multi-panel and unlabeled figures retain the legacy layout.

`vispa gui` starts the optional Tk interface. `vispa --help`, `vispa --version`, and `python -m vispa --help` do not load image libraries, open windows, or acquire data. Package import does not change `sys.path` or import `IONData`.

## One-volume DS00 montage

`vispa montage` renders one explicitly named 3D NIfTI into the preserved five DS00 views. It does not discover cohorts, read workbooks, choose files, or apply a transform. The affine must yield LPS voxel axis codes, as in the source montage. NIfTI affines map voxel indices into RAS+ world coordinates; each panel labels increasing projected anatomical directions in RAS+ millimetres. The header must declare millimetres, or the operator must explicitly declare `--units mm` when the header units are unknown; known non-mm units are rejected. The output includes a compact intensity-image legend. The `[3d]` extra provides the montage dependencies.

```powershell
& '.\.venv\Scripts\vispa.exe' montage --input 'D:\data\sample.nii.gz' --output 'D:\review\sample-5view.png' --units mm --max-voxels 64000000 --set display_gamma=0.88 --dry-run
```

Review the resolved header, affine, setting values, output path, and receipt path. Remove `--dry-run` to write a new PNG and adjacent JSON receipt. The command requires the explicit `--units mm` declaration, refuses existing outputs and input overwrite; it hashes the source before and after rendering and removes partial outputs if rendering fails. The default bound is 64 million voxels; `--max-voxels` can change that bound explicitly. `--set KEY=JSON_VALUE` is repeatable and only accepts the settings below. The Python mapping `vispa.volume_montage.SETTING_SPECS` also provides each parameter's default, effect, unit, and validated range.

| Setting | Default | Unit / valid range | Effect |
|---|---:|---|---|
| `figure_size_inches` | `[18.2,4.4]` | inches / 1–100 each | Single-volume figure width and height |
| `figure_dpi` | 120 | DPI / 36–600 | Single-volume PNG output resolution |
| `max_dimension` | 210 | voxels / 1–4096 | Maximum downsampled array dimension |
| `otsu_sample_stride` | 8 | samples / 1–4096 | Otsu histogram input stride |
| `otsu_clip_percentile` | 99.5 | % / 0–100 | Otsu upper clipping percentile |
| `intensity_high_percentile` | 99.3 | % / 0–100 | Upper display intensity percentile |
| `minimum_intensity_span` | 1.0 | input intensity / >0 | Minimum separation of low/high values |
| `blur_sigma_voxels` | `[0.45,0.45,0.95]` | voxels / 0–1000 each | Downsampled-volume Gaussian blur |
| `foreground_threshold` | 0.08 | normalized / 0–1 | Foreground bound threshold |
| `min_foreground_voxels` | 1000 | voxels / ≥1 | Minimum foreground count |
| `max_foreground_points` | 300000 | points / ≥1 | Maximum geometry samples |
| `view_extent_percentiles` | `[0.6,99.4]` | % / 0≤low<high≤100 | Projected image bounds |
| `depth_percentiles` | `[0.3,99.7]` | % / 0≤low<high≤100 | Ray depth bounds |
| `projection_padding_fraction` | 0.07 | fraction / 0–1 | Image-bound padding |
| `minimum_extent_mm` | 5.0 | mm / >0 | Minimum accepted view extent |
| `projection_bin_mm` | 0.36 | mm/pixel / >0 | Projected sampling interval |
| `horizontal_bins_px` | `[150,260]` | pixels / 1–4096 each | Output width bounds |
| `vertical_bins_px` | `[150,280]` | pixels / 1–4096 each | Output height bounds |
| `depth_step_mm` | 0.55 | mm/step / >0 | Nominal ray sampling interval |
| `depth_bins` | `[56,110]` | samples / 1–1024 each | Ray sample-count bounds |
| `ray_extinction` | 8.0 | unitless / >0 | Opacity growth along each ray |
| `layer_alpha_cap` | 0.88 | fraction / 0–1 | Maximum opacity per ray layer |
| `normalization_percentile` | 99.5 | % / 0–100 | Composite intensity normalization |
| `display_gamma` | 0.88 | unitless / >0 | Composite display gamma |
| `background_cutoff` | 0.012 | normalized / 0–1 | Dark-background suppression |
| `min_positive_pixels` | 200 | pixels / ≥1 | Minimum nonzero composite count |
| `min_filled_fraction` | 0.04 | fraction / 0–1 | Minimum filled-view fraction |
| `green_channel_scale` | 0.985 | fraction / 0–1 | Green-channel display tint |
| `blue_channel_scale` | 0.94 | fraction / 0–1 | Blue-channel display tint |

These are display settings inherited from the project montage. They do not change anatomy or establish registration or scientific acceptance.

The legacy OpenGL viewer is installed into the dedicated worker with
`& '.\.venv\Scripts\python.exe' -m pip install '.[3d]'`. It requires a local OBJ mesh, an explicit sample ID and processed
SWC filename, and explicit coordinate-frame and coordinate-unit declarations in
`sources.brain_view`; it does not resolve cohort identities, use raw SWCs, fetch remote
data, or apply registration/mirroring. Preview the resolved paths and display settings
before launching a window:

```powershell
& '.\.venv\Scripts\python.exe' -I -m vispa brain-view --sample 251637 --neuron 001.swc --config 'C:\data\visual_toolkit_config.yaml' --dry-run
```

Remove `--dry-run` for an interactive review, or add `--snapshot 'D:\review\view.png'`
for one bounded PNG plus adjacent JSON receipt. Existing outputs are never overwritten.
The receipt records source hashes, frame/units as declared, camera/clipping settings,
worker/runtime and renderer hash. The initial pose uses a numeric oblique display vector;
it does not assert anatomical orientation. The renderer centers the stored mesh and SWC
together without changing their coordinates. To tune the display, set `sources.brain_view.settings`
keys `eye_direction`, `up`, `camera_distance_scale`, `line_width`, `soma_radius`,
`background`, `mesh_color`, `neuron_color`, and `window_size`, or pass the matching
`--eye-direction`, `--up`, `--camera-distance-scale`, `--line-width`, `--soma-radius`,
`--background`, `--mesh-color`, `--neuron-color`, and `--window-size` flags. The core
package remains installable without the `[3d]` OpenGL dependencies.

| Setting / CLI flag | Default | Effect | Valid range |
|---|---:|---|---|
| `eye_direction` / `--eye-direction X Y Z` | `[-1.3, 1.6, 1.5]` | Initial viewing direction in centered display coordinates | Three finite values; nonzero and not parallel to `up` |
| `up` / `--up X Y Z` | `[0, 0, 1]` | Initial camera up direction | Three finite values; nonzero and not parallel to `eye_direction` |
| `camera_distance_scale` / `--camera-distance-scale` | `0.40` | Scales the bounds-fit distance (`scale × √3 × mesh diagonal`) | Positive finite number |
| `line_width` / `--line-width` | `2.0` | Processed-neuron line width | Positive finite number |
| `soma_radius` / `--soma-radius` | `200.0` | Processed-neuron soma display radius | Positive finite number |
| `background` / `--background R G B` | `[0, 0, 0]` | Window background color | Each RGB component in `[0, 1]` |
| `mesh_color` / `--mesh-color R G B` | `[0.8, 0.8, 0.8]` | Brain-mesh display color | Each RGB component in `[0, 1]` |
| `neuron_color` / `--neuron-color R G B` | `[1, 0.5, 0]` | Processed-neuron display color | Each RGB component in `[0, 1]` |
| `window_size` / `--window-size WIDTH HEIGHT` | `[1100, 800]` | Initial viewer dimensions in pixels | Two integers, each at least 100 |

## Shared settings interface

`vispa settings` retains the review-only JSON schema by default. Use
`vispa settings --scope review|brain-view|montage|all` to discover the
three existing parameter groups; `all` is grouped JSON and loads no optional
feature dependencies. The root Python API is `vispa.settings_schema(scope="all")`,
`resolve_settings(scope, overrides=None, base=None, config=None)`, and
`apply_settings(scope, overrides, settings=None, config=None)`. The same APIs
are available through the compatibility `vispa` module alias. Values can be mappings or
repeated `KEY=VALUE` strings; JSON values such as arrays/numbers are decoded,
while review's historical comma sequences, hex colors, and `auto` remain accepted.
For the Context panel, `context.swc_overlay_depth_um` sets the total soma-centred
SWC projection window (default 100 µm, i.e. ±50 µm). The image slab stays
`context.depth_um`; both limits are printed in the panel title, and the red
legend entry is labeled **Trace from SWC**.
Resolution deep-copies input. `apply_settings` validates before updating a supplied
mutable target; only the existing review scope may update renderer globals without
a target.

An optional existing JSON/YAML config can hold the shared settings block; no new
config file is created by the package:

```yaml
visual_toolkit:
  settings:
    review:
      marker.color: "#ff00ff"
      figure.review_dpi: 90
    brain-view:
      camera_distance_scale: 0.45
    montage:
      display_gamma: 0.9
```

Resolution applies package/current defaults, then the caller's `base`, then
configuration values, then explicit API or CLI overrides. Brain-view also reads
the legacy `sources.brain_view.settings` block first; `visual_toolkit.settings.brain-view`
overrides those values. A specific brain-view flag wins over a duplicate `--set`
key. Supply `--config PATH` to `render`, `montage`, `brain-view`, or
`settings --config PATH` to show config-resolved current values. For review settings, the API resolves against the active toolkit defaults; toolkit
initialization may already have read the selected per-user or environment config.
Brain-view and montage default-scope resolution uses package defaults unless an
explicit config is supplied.

Brain-view adds repeatable `--set KEY=VALUE`; the existing specific flags take
precedence if the same key appears in both forms. Example:

```powershell
vispa brain-view --sample 251637 --neuron 001.swc --config 'D:\config.json' --dry-run --set camera_distance_scale=0.5 --camera-distance-scale 0.6
```

The resolved camera scale is `0.6`. Run `vispa settings --scope brain-view`
for defaults, units, display effects, valid ranges and the `eye_direction`/`up`
vector relationship; add `--config PATH` to include configured current values.

## Sources and configuration

No specimen, share, URL, SSH host, or project directory is configured by default. An absent config provides per-user cache and output folders only. Set `VISPA_CONFIG` or pass `--config PATH`; the older `PROJECTOME_DATASETS` environment variable remains accepted. JSON works with the standard library; YAML is included in the core install. Relative paths resolve from the config file's folder, or from the optional top-level `base_dir`.

Create the per-user YAML without overwriting anything already present:

```powershell
vispa config-init --dry-run
vispa config-init
vispa config-init --output 'D:\review\visual_toolkit_config.yaml'
vispa config-init --from-config 'D:\old\visual_toolkit_config.json' --output 'D:\review\visual_toolkit_config.yaml'
```

`--output` must end in `.yaml` or `.yml`; an explicit destination is never
overwritten. Without `--output`, the per-user YAML is the target and an existing
per-user JSON is copied once as a migration (the JSON is left byte-unchanged).
Passing `--output`, even for the same default path, selects the package template
instead of migrating. The created file contains validated effective values for the
review, brain-view and montage scopes, so it is complete rather than an implicit
set of defaults. A relative per-sample `swc_cache` resolves from the config folder
unless `swc_cache_root` or `swc_root` is declared. The GUI parses its arguments
first (abbreviations are rejected) and initializes only a valid implicit launch;
`--config`, `--dry-run` and a configured environment path never create a file.

For SSH sections, set `ssh_sample_id` alongside `ssh_remote_base`; that remote root is only eligible for the matching sample. `low_res_ssh_base=` is an explicit per-instance override. The GUI identity and auto-load behavior is selected from `visual_toolkit.default_sample`, `visual_toolkit.default_neuron`, and `visual_toolkit.auto_load`. A package-only config leaves these blank and disables startup auto-load; explicit CLI/constructor identities take precedence, and `--no-autoload` always disables it. Use the existing project YAML with `--config PATH` to preserve lab-specific paths and source settings. In the GUI, **Neuron list** loads the configured portal snapshot; selecting a row fills only the Neuron ID field. **Render** (F5) produces the complete panel set (Soma, Context, Sagittal and TrioPlot); there is no per-panel selection. **Save outputs** beside Render chooses whether the run writes files (unticked = preview only), and **Save Soma NIfTI (.nii.gz)** in Saving controls the soma volume. The **3D brain view** action carries the current sample, neuron ID, and any loaded portal region to the isolated original OpenGL worker, using the configured processed SWC only. **fnt-tracer** opens `<sample>_<neuron>.fnt` from `visual_toolkit.fnt_tracer.project_root`, and requires both a configured executable and that matching project. There is no bulk action.

Per-sample `ds00_expected_geometry` declares the expected `shape_ijk`,
`spacing_mm_ijk`, and `affine_diag` for validation and provenance. A configured
`resample_5um_corrected: true` requires a complete `resample_5um_policy` containing
the source-relative `completion_record`, identity field, required record values,
collection counts, fields expected to be empty, isolated `cache_namespace`, and
descriptive provenance. The loader checks descriptor structure and path safety;
the renderer checks the local completion record before using corrected sections.
Record hashes and selected record paths are computed facts and cannot be supplied
by the descriptive provenance mapping. For compatibility, absent expected-empty
fields in a record retain the prior falsey/empty behavior. These descriptors live
in external configuration rather than package code; generic samples without a
corrected-source declaration keep their existing source behavior. Geometry checks
validate the declared grid only; they do not resolve the existing sagittal mapping
hypotheses or establish anatomical orientation, and do not claim support for
heterogeneous or irregular-pitch grid mapping.

```json
{
  "version": 1,
  "defaults": {
    "cache_root": "./cache",
    "output_root": "./output",
    "swc_cache_root": "./swc",
    "ds00_root": "./processed_ds"
  },
  "samples": {
    "sample-01": {
      "monkey": "animal-01",
      "ds00_processed": "./sample-01.nii.gz",
      "ds00_sha256": "",
      "resample_5um": "./sample-01_sections",
      "swc_cache": "sample-01"
    }
  },
  "visual_toolkit": {"output_root": "./gui-review"},
  "sources": {
    "dataset_manifest": "./manifest.json",
    "brain_view": {
      "mesh_path": "./template.obj",
      "processed_swc_root": "./processed_swc",
      "coordinate_frame": "legacy-neuronvis-template-as-stored",
      "coordinate_units": "stored",
      "settings": {}
    },
    "neuron_catalog": {
      "path": "./portal_neuron_snapshot.csv",
      "source_date": "20261009",
      "columns": {
        "sample": "sample",
        "neuron_id": "neuron_id",
        "portal_region": "portal_region",
        "monkey": "registry_animal"
      }
    }
  }
}
```

`dataset_config.load(path=None, base_dir=None)` returns resolved `defaults`, `samples`, `visual_toolkit`, and `sources`. Backend cache/output roots use `defaults.cache_root` and `defaults.output_root`; `visual_toolkit.output_root` is the GUI review-output root. `dataset_config.default_config_path()` and `default_output_root()` provide per-user locations without creating them. A project adapter may call `toolkit.configure_data_sources(path)` after selecting its config; the selected config then applies to subsequent toolkit instances.

The GUI's **Neuron list** button opens a compact scrollable browser and reads only the configured dated CSV snapshot. Configure `sources.neuron_catalog.path`, its `source_date`, and the exact sample, neuron ID, portal region, and optional monkey columns. The list includes every matching sample row in that snapshot (not only the selected 462-neuron workbook), preserves zero-padded IDs and exact sample suffixes, and labels blank portal regions as `Unassigned`. Its visible provenance includes the resolved source path, source date, row count, and SHA-256. Selecting a row changes only the Neuron ID field; it does not load coordinates or start a render. The public `vispa.sources.list_neurons(sample_id, config=None)` function returns a provenance object with `rows` and raises on missing source configuration, missing columns, duplicate IDs, or unsafe neuron basenames. It makes no network calls.

The optional **3D brain view** action uses `sources.brain_view.mesh_path` and `processed_swc_root`, with declared `coordinate_frame` / `coordinate_units` and optional `settings`; `visual_toolkit.worker_python` selects its isolated worker when set. A generic config does not receive default anatomical frame or unit declarations: the worker preflight requires explicit values when 3D view is requested. The default projectome config points to the preserved root.obj and processed-SWC tree and declares their current stored convention. The handoff passes the exact current sample and neuron ID plus the portal snapshot's region when available. It never substitutes a raw SWC or downloads a model. The GUI starts the worker in a separate process, leaving the host Python imports isolated.

`vispa.sources.IONData()` reads the configured local SWC cache first. A project can register a fallback implementing `getRawNeuronTreeByID(sample_id, neuron_id)` using `set_iondata_provider_factory(factory)`. Without a registered factory, setting `sources.http_host` and `sources.raw_swc_base` enables the built-in portal fetch: it reads the sample's `project_id` from the portal and downloads `<project>/<sample>/swc_raw/<neuron>` into `sources.legacy_raw_swc_root`. The returned tree protocol exposes `root.x/y/z`, `root.xyz`, `points`, and iterable `edges` whose `.data` contains points with `.x/y/z` attributes. The local parser rejects malformed, disconnected, cyclic, and missing-parent trees.

The processed-DS sagittal implementation requires explicit `sources.dataset_manifest` and `defaults.ds00_root`, a configured per-sample image path and checksum, and local SWC input or cache. It records source identity and geometry. Its A/B mapping choices remain unresolved; successful loading or rendering is not anatomical acceptance.

## API and projectome integration

The primary Python import is `vispa`. `vispa.VisPa`, `REVIEW_SETTINGS`, and the plotting helpers are exposed lazily from `vispa.toolkit`. Core rendering accepts in-memory arrays, so a consumer can integrate the package without adopting the standalone acquisition providers or source layout.

Projectome owns its cohort runners, montage adapter, source manifest, and lab-specific configuration. It can depend on this distribution and keep a thin compatibility facade that maps its existing `Visual_toolkit` imports, injects the `IONData` provider, and supplies explicit data roots. The independent package contains only the generic single-volume DS00 renderer, not the cohort montage adapter or its workbook/path/selection logic. It carries no cohort YAML or source data; `extraction_manifest.json` preserves historical source path and hash provenance.

## Package checks

The package tests cover clean import without projectome or `IONData`, config-relative resolution, SWC validation and provider fallback, local coordinate geometry, a tiny-array render with its marker and receipt, DS00 frame parity, montage dry-run no-write behavior, and PNG/receipt output. No license is assigned by this staged extraction.

See [CHANGELOG.md](CHANGELOG.md) for the preserved toolkit history and extraction changes.


### Single-neuron resource and FNT preflight

Run `vispa config-check --config settings.yaml --sample 251637 --neuron 003.swc --dry-run` for a read-only JSON inventory (file hashes, source dates unknown as null, coordinate declarations, cache references and cube route/geometry). Add `--fnt` to require both the configured executable and the exact `<sample>_<neuron>.fnt` or `.decimate.fnt`; this mode returns failure when either is unavailable and never starts the binary. Directory references are not recursively hashed; the inventory alone does not establish complete offline panel coverage or scientific acceptance.

In the GUI, **FNT setup…** exposes **FNT executable** and **Project folder**, each with **Browse…**; **Save paths** persists absolute paths in the active config through the existing validated writer. A config changed while the dialog was open must be reopened before saving. **fnt-tracer** requires the matching project. These two paths default to null in neutral configs and do not change scientific rendering parameters.

Combined review figures derive text wrapping, legend/footer height and labeled-axis separation from the selected font metrics and available axes width; panels retain full image extents and original aspect ratios, anchored at the top. These are automatic layout constraints rather than separate scientific parameters. Tune `figure.review_figsize` and `figure.review_dpi` through the existing settings interface.

Soma inline-label presentation: `--set marker.label_mode=none` (default, role legend only), `short` (S), or `numbered` (1 with a thin leader). Cyan box/cross coordinates are identical in all modes. Existing label font size and offset remain tunable; `vispa settings --scope review` lists the enum and effects.

GUI Render now uses the same combined legend layout as the bounded runner. Soma/Context use explicit crop-pixel index axes, all standalone PNG tabs carry role legends outside the image, and GUI cache keys include gui.py/toolkit.py hashes so local code changes invalidate earlier figure strips even when the package version stays unchanged.

## Legacy compatibility

`import Visual_toolkit`, `Visual_toolkit.Visual_toolkit`, `python -m Visual_toolkit`, `python -m Visual_toolkit.gui`, `visual-toolkit` and `visual-toolkit-gui` remain aliases. Qualified legacy leaf modules share primary module objects; the legacy GL parent is a state-free namespace.

Existing `visual-toolkit.*.v1` receipt schemas, the `visual_toolkit` settings key, `visual_toolkit_config.yaml/json` filenames and per-user `VisualToolkit` configuration/cache/output folders remain unchanged. `VISUAL_TOOLKIT_CONFIG/PYTHON/WHEELHOUSE` remain fallbacks behind corresponding `VISPA_*` values. Existing installations, data and historical manifests are not moved or rewritten. The GitHub repository is `bylaikaby/VisPa`; clone it into `D:/VisPa` as above.

The offline wheel command above uses an explicit placeholder path; substitute the exact built wheel from the current receipt under `work/vispa_rename_20261022/run_receipt.json`. This repository receipt is the current rename verification entry point.
