# VisualToolkit change log

One consolidated history for the standalone package. `README.md` is the operator
guide; per-module headers carry `Version:` / `Last updated:` / `Change history:`
and point here.

Entries are newest first. "Local/unreleased" means the change is in the working
tree but has not been committed or published; dates are Asia/Shanghai.

## 1.11.0.dev0 — 2026-10-19 (local/unreleased)

- Added a one-command Windows installer (`install.cmd` + `tools/install.ps1`):
  it creates `%LOCALAPPDATA%\VisualToolkit\venv`, installs the newest wheel
  with `[3d]`, optionally uses an offline wheelhouse, registers the user PATH
  and config, creates a desktop shortcut, and launches the GUI. `-Source`
  installs the current GitHub checkout; `-DryRun` prints the resolved plan.
  Native pip/venv failures now stop the installer instead of reporting success.
- The Sample card now shows the current neuron's **Portal region** from the
  configured catalog (for example `PrCO_49`), refreshed on Sample/Neuron ID
  changes and cached per sample. The value is display metadata; it does not
  load coordinates or establish anatomical membership.
- Soma acquisition now reports the missing central cube index, sample, soma
  coordinates, HTTP source and last cache/HTTP error instead of a generic
  "cube is unavailable" message. No lower-resolution fallback was added: the
  legacy `get_high_res_block` path also required the central cube, and the
  three 252385 test neurons have no legacy SomaBlock.
- Renamed the full-stack extra to `[3d]` (2026-10-20): `pip install
  "visual-toolkit[3d]"` resolves the TIFF/NIfTI, SciPy/scikit-image, montage
  and legacy-GL packages, while the core stays NumPy/Matplotlib/Pillow/PyYAML.
  Third-party distributions are not embedded; the wheelhouse + `--no-index`
  route keeps offline setup fast.
- Redesigned the Tk review window to the approved single-column layout — titled
  **Review steps** block (the original LOAD/TARGET/ACQUIRE/FALLBACK/REVIEW copy
  plus an orange **3D VIEW** step), a primary teal **Neuron list** button beside
  **Load & Auto-Fill**, and a **Load selected** action with double-click loading
  in the portal list. Single click still only fills the Neuron ID.
- Merged the Soma Plot, Context Plot and Plotting cards into one **Plotting
  settings** block; the original block-size, cube-source, per-section and 5 µm
  resample text is retained. The per-panel ticks and Force re-render control
  were removed: **Render** always produces Soma, Context, Sagittal and
  TrioPlot, and cached figures are reused when the fingerprint matches.
- Saving is now an output-folder block only: path, **Browse…** and **Open output
  folder**; the per-artifact tick boxes were removed and the selected panels are
  always written. The bottom action bar has larger Render and orange 3D brain
  view buttons and no duplicate 3D description.
- Made the window geometry and left column DPI-proportional to the approved
  1298×1212 mockup (392-px column), so a 200 % display no longer clips the
  Target soma inputs, Plotting boxes or Saving block; the settings scrollbar
  hides itself when all cards fit.
- Numeric inputs are parsed through one validator that names the field and
  explains empty, non-numeric and out-of-range values instead of raising a bare
  `float('')`; deferred preview reloads and tab refreshes skip a window that is
  already closing.
- Added an **fnt-tracer** button beside **3D brain view**. It opens
  `<sample>_<neuron>.fnt` (falling back to `.decimate.fnt`) from the configured
  `visual_toolkit.fnt_tracer.project_root`, or starts fnt-tracer alone when no
  project file exists; the executable and root are validated and resolved by
  `dataset_config.load`, and unknown keys are rejected.
- Added portal raw-SWC acquisition. When a neuron is missing from the local
  caches and `sources.http_host` plus `sources.raw_swc_base` are configured,
  the SWC is fetched from `<project>/<sample>/swc_raw/<neuron>`, cached under
  `sources.legacy_raw_swc_root`, and reused by Load & Auto-Fill, Context and
  Sagittal. No new dependency is required.
- Renamed **Review steps** to **Step guide** and dropped the subtitle. The
  guide is a fixed-height scroll area so the rest of the window stays compact,
  with expanded per-step detail (portal/SWC cache, cube fallback, save behavior
  and fnt-tracer).
  The Sagittal hint now describes the DS00 processed volume (resolution and
  orientation) and its file inside its own bordered section; only the
  **Sagittal** title is bold, and the "sagittal X" phrase was removed.
- Enhanced the Context red SWC overlay against the legacy review renderer
  (`visual_review_20261002.py`: red 0.6 / alpha 0.8): a dark 1.4 / 0.55
  underlay now carries a 0.7 / 0.9 red trace, and the green-composite RGB is
  clipped to 0–1 before `imshow`. Validated by the same 20-neuron before/after
  Context montage.
- Added `context.swc_overlay_depth_um` (default 100 µm, soma-centred). The
  legacy July-2026 LowRes plots projected the full arbor, which is unrealistic
  for a local review; the image slab alone was too sparse. On 252385/050 the
  same crop gives 439k red pixels in the legacy PNG, 578k at all depths, 16k
  for the 30-µm slab, and 53k for the 100-µm window. The title now prints both
  `Depth: 30 µm | Trace from SWC ±50 µm`; the red legend entry is labeled
  **Trace from SWC**.
- The bottom bar has a **Save outputs** tick beside Render: unticked renders
  preview-only artifacts; ticked writes the selected panels and TrioPlot. The
  Saving card adds a **Save Soma NIfTI (.nii.gz)** tick.
- Added `visual-toolkit install-path`: it adds this venv's `Scripts` folder to
  the current user's PATH with dry-run, idempotent and `--remove` modes, and
  can also set `VISUAL_TOOLKIT_CONFIG`. The wheel never edits PATH at install
  time.
- Version advanced to 1.11.0.dev0. CLI, settings, config lifecycle and rendering
  behavior are otherwise unchanged.

## 1.10.0.dev0 — 2026-10-19 (local/unreleased)

- Completed the configuration lifecycle — so a first normal GUI launch creates one
  per-user YAML from the package template, an explicit `--config` or environment
  path is never created, and the prior per-user JSON is migrated only when
  `config-init` is run without `--output`. `config-init` now rejects non-YAML
  destinations and writes validated effective values for the review, brain-view and
  montage scopes, while declared scoped values are validated on load (the legacy
  `sources.brain_view.settings` block retains its worker-preflight behavior).
  A relative per-sample `swc_cache` stays relative to the config directory when no
  SWC root is declared instead of inheriting the per-user cache fallback. The GUI
  parses and validates arguments, with abbreviations disabled, before any implicit
  initialization. Validated by focused config/CLI/GUI tests, the full installed
  suite, and the Projectome compatibility suite; the user JSON was not migrated.

## 1.10.0.dev0 — 2026-10-18 (local/unreleased)

- Externalized source-validation and startup policies into validated configuration — so cohort-specific source and GUI defaults are supplied by the operator config while preserving current validation and startup behavior; malformed declarations fail closed and verified record provenance remains bound. Blank-identity dry-run output now uses the GUI's `sample_YYYYMMDD` fallback. Existing sagittal assumptions and coordinate calculations are unchanged and unresolved. Validated with synthetic config, completion-record, geometry-header, GUI-resolution, atomicity, and blank-launch regressions plus the projectome loader compatibility check.
- Fixed overlap in the labeled single-panel CLI review by deriving clearance from rendered text bounds; multi-panel and unlabeled figures retain the legacy grid spacing. Validated with compact single-panel, multi-panel compatibility, and impossible-height cleanup regressions.
- Added one scoped settings API for review, brain-view, and montage — so Python discovery, JSON/YAML configuration, GUI edits and CLI overrides share existing validators; settings can be layered in the existing config, invalid batches remain atomic, and render restores both review settings and cached renderer defaults after success or failure. The default `settings` command remains review-only, and explicit brain-view flags take precedence over duplicate `--set` values. Units/ranges are discoverable without optional feature imports. Validated by focused CLI, config, OpenGL-planning and montage tests.
- Added a no-argument `visual-toolkit-gui` executable that calls the existing Tk `main` without replacing the command-line interface; its focused entrypoint and mapped-app checks pass, while a native screenshot remains unverified.
- Extracted the original five-view DS00 volume renderer as `Visual_toolkit.volume_montage` and added a bounded single-NIfTI montage command — so operators can review one explicit local LPS volume without project cohort discovery; numeric frame parity matches the pre-extraction baseline; camera-derived anatomical axis labels, explicit millimetre checks and tunable figure dimensions/DPI are recorded, and the optional montage extra supplies nibabel/SciPy. Dry-run and PNG/receipt collision handling are covered by focused synthetic tests; no real-animal visual acceptance is claimed.
- Added an explicit stdlib CSV API for the dated full portal neuron snapshot and a
  compact GUI list/selection dialog — so operators can select any neuron in the exact
  sample without network access or the selected-462 cohort filter; source hash,
  date, count, exact IDs and blank-region status remain visible. Unsafe neuron
  basenames and non-string sample IDs are rejected without normalization; stale and
  post-close GUI callbacks are discarded safely. Validated with catalog loader and GUI
  selection/stale-result tests; native GUI visual review pending.
- Simplified the action bar to one selected-panel Render action and removed the
  Render all/F6 control. The GUI keeps 2D render behavior and launches the optional
  original OpenGL viewer in a separate configured worker; missing coordinate-frame
  and unit declarations remain missing for preflight rather than inheriting a
  project-specific default.
- Added a discoverable review-settings schema, atomic mapping/list overrides, and
  synchronized cached renderer defaults when process-global settings change — so
  displayed defaults, tuned values and actual PNG output stay aligned. Schema
  constraints preserve prior accepted positive values and add only mathematical
  or acquisition bounds; focused checks cover compatibility, no-partial updates,
  and rendered PNG dimensions/marker color.
- Preserved replacement of a cached TIFF whose header raises `TiffFileError` —
  so corrupt cache evidence can proceed through the existing bounded source path;
  validated with a local synthetic regression fixture.
- Extracted a standalone `src/Visual_toolkit` package with a safe, bounded local
  array CLI, lazy optional providers, explicit configuration and local SWC
  parsing — to let projectome consume the renderer as a dependency while
  preserving the uppercase import and rendering algorithms; headless import no
  longer requires `IONData`, mutates `sys.path`, or infers project paths.
- Preserved explicit `cache_dir=` output placement and scoped configured SSH
  sources to their declared sample; local SWC caches are checked before an
  optional registered provider, including the configured legacy local root.
- Added an optional `legacy-gl` worker route that reuses the original OpenGL
  renderer for one configured local root OBJ and processed SWC — to preserve the
  existing mesh/SWC display behavior while keeping OpenGL dependencies out of the
  core install. The frame and units must be declared; coordinates remain stored,
  without registration or mirroring. Interactive and snapshot views show role
  swatches; bounded PNG snapshots and interactive starts write hash-bound receipts.
  The numeric oblique camera is tunable display framing, not an anatomical
  orientation claim. Focused planner, worker-isolation, legacy geometry and actual
  render checks are recorded in the shared validation receipt.
- Validation: standalone import, relative config resolution, URL/remote path
  preservation, missing optional TIFF dependency, SWC graph validation and
  provider fallback, backend path compatibility, and SSH sample isolation
  covered by focused tests. CLI image/receipt checks are recorded with its test
  suite. License remains unresolved; this is not a public release.

### Standalone package module scope — 1.10.0.dev0

| Module | Version | Role |
|--------|---------|------|
| `toolkit.py` | 1.10.0.dev0 | rendering, configured acquisition, sagittal panels and review settings |
| `gui.py` | 1.10.0.dev0 | optional Tk operator GUI |
| `image_geometry.py` | 1.10.0.dev0 | native-coordinate and image geometry helpers |
| `dataset_config.py` | 1.10.0.dev0 | portable settings and data-link resolution |
| `context_resources.py` | 1.10.0.dev0 | bounded context source resource planning |
| `derived_context.py` | 1.10.0.dev0 | derived native context sampling |
| `review_lock.py` | 1.10.0.dev0 | cross-process exclusive output lock |
| `sources.py` | 1.10.0.dev0 | local SWC parser and explicit provider seam |
| `cli.py`, `__main__.py`, `__init__.py` | 1.10.0.dev0 | safe headless entry point and lazy public imports |
| `opengl.py` | 1.10.0.dev0 | explicit local-only planner and isolated legacy-viewer worker |
| `legacy_gl/` | 1.10.0.dev0 | bounded extraction of the existing OpenGL mesh/SWC renderer |
| `volume_montage.py` | 1.10.0.dev0 | generic five-view LPS NIfTI renderer and display settings |

The source snapshot below records the original projectome package history; it is
retained as provenance and does not describe the standalone package scope.

## Original source-tree module versions — 2026-10-18 snapshot

| Module | Version | Role |
|--------|---------|------|
| `gui.py` | 1.9.1 | Tkinter operator window; local/unreleased handoff follow-up |
| `toolkit.py` | 1.9.1 | rendering, acquisition, sagittal setup + `REVIEW_SETTINGS` |
| `montage.py` | 1.9.1 | nine-sample DS00 five-view cohort montage |
| `dataset_config.py` | 1.9.1 | dataset links / operator check |
| `visual_toolkit_config.yaml` | schema 1 | per-sample DS00, 5 µm, SWC cache, GUI output root |
| `run_bulk_visual_sample.py`, `bulk_visual_multi_monkey.py` | 1.9.1 | bulk wrappers (outside the package) |

All modules move with the package version until a released tag exists; an
unreleased change never claims a release.

## 1.9.1 — 2026-10-18 (local/unreleased; GUI follow-up)

- Added exact-pair VisualToolkit startup from the NeuronView review-session JSON,
  optional file watching, and a dry-run launch report — to carry one explicit
  `(SampleID, NeuronID)` selection into the existing GUI; identity changes clear
  stale soma values and preview state, the latest valid event waits while a render
  is active, same-identity source changes update provenance without reloading the
  soma, and saved review figures record captured session/FNT provenance. Session
  reads are bounded to 64 KiB, and session data never supplies commands or soma
  coordinates.
- Validation: all 19 focused GUI request tests pass, covering identity/source
  validation, dry-run startup without Tk/IONData/toolkit construction or file writes,
  deferred event ordering/coalescing, cached-preview loading, manual-ID provenance
  isolation and stale-preview clearing. No live Tk window or NeuronView session was
  exercised.

## 1.9.1 — 2026-10-17 (released 2867eef)

Sagittal consolidation
- Merged all processed-DS sagittal code from `sagittal.py` into `toolkit.py`: source
  manifest verification, raw-SWC resolution, sagittal plane extraction, candidate A/B
  mappings, legacy PIL rendering, shared review-panel preparation and source prefetch.
- Removed `sagittal.py`; the GUI and both bulk wrappers now import `SAMPLE_PATHS`,
  `resolve_swc_path`, `prepare_sagittal_source` and `prepare_sagittal_panel` directly
  from `VisualToolkit.toolkit`.
- The Review settings marker is now read directly rather than through a cross-module
  fallback, preserving the single shared visual style.

Validation
- Package, GUI and bulk-wrapper syntax checks pass.
- The combined suite passes **77 tests**, including three integration checks that
  verify the sagittal functions are owned by `toolkit.py`, the separate module is gone,
  and the shared marker settings remain identical.

## 1.9.0 — 2026-10-17 (released 636197c)

Package integration
- Moved the DS00 five-view cohort montage implementation into
  `Visual_toolkit/montage.py`; it is now available as
  `python -m Visual_toolkit.montage`. The previous
  `tools/ch00ds_5view_montage.py` path remains a compatibility wrapper.
- Added `--source-root` and `--workbook` path overrides while preserving the existing
  source-hash checks, output-overwrite refusal, five-view cameras and JSON receipt.
- Confirmed the processed-DS sagittal renderer remains package-owned in
  `Visual_toolkit/sagittal.py` and continues to back the GUI and bulk wrappers.
- Added an offline montage regression module covering camera basis, label CLI,
  streamed hashing and the legacy wrapper import.

Validation
- Package and wrapper syntax checks pass.
- The combined seven-module suite passes **74 tests**, including five offline montage
  checks for camera geometry, label CLI, streamed hashing and legacy-wrapper import.

## 1.8.0 — 2026-10-17 (released c817ee19)

Operator release
- Publishes the consolidated VisualToolkit package: config-backed datasets, shared SWC
  resolution, Soma/Context/Sagittal panels, receipt-based cache reuse, timestamped
  figures, process logging and isolated panel failures.
- Finalises the Tkinter reviewer UI with Plotting/Saving lanes, Render all, output-folder
  access, editable in-app YAML configuration with backups, a scrollable five-stage load
  guide, aligned preview-ribbon identity/filename and the outlined **Update figures**
  action.
- Clarifies that Soma acquisition reuses local cubes and fetches only missing cubes
  online; changed saves create new timestamped PNGs while the optional fixed-name Soma
  NIfTI is overwritten.
- Adds the required version header to the package demo entry point and aligns both bulk
  wrapper version headers with the package.

Validation
- The established six-module suite passes **69 tests**.
- Live GUI checks cover the updated stage guide and scrolling, ribbon alignment,
  **Update figures**, cached-set prompt, four-panel reload and the refreshed Soma note.

## 1.7.2 — 2026-10-17 (local/unreleased)

Save lane and figure tracking
- Added a visible **Trio PNG** save tick (default on) beside **Soma NIfTI**; the
  TrioPlot is written only when its save tick is on, otherwise it is preview-only and
  the temp file is removed.
- The Soma card now explains the block arithmetic again: 1 downloaded block =
  360×360×90 voxels (234×234×270 µm); the window **diameter** of 1.5 blocks is
  ≈351 µm wide × 270 µm deep and downloads only the blocks it touches; the legacy
  **radius** r = 1/2/3 has diameter 2r−1 = 1/3/5 blocks and downloads 1/27/125.
  The visible Soma-card note now contains only the block dimensions; the
  1.5-block diameter and legacy-radius sentences are removed from the GUI.
- **Load & Auto-Fill Soma** now uses the filled teal primary style (it was an outline
  button), so the identity action reads as an action rather than a field.
- Card titles use 11 pt bold in the deep navy header colour (previously muted 9 pt); the
  header subtitle reads "DEB lab · fMOST neuron reviewer"; the settings column is 430 px
  and the action buttons are wider, keeping the column at 801 px.

Layout and readability
- Input boxes stretch to fill their card (Sample/Neuron, X/Y/Z, Context width/height/
  depth, Save-to); the Load & Auto-Fill Soma button spans the card width.
- The Context card carries a compact dataset line (5 µm sections 5×5×3 µm, default
  8×8 mm × 30 µm crop, DS00 ~100×90×100 µm).
- The figure preview has a purple top ribbon and its Soma/Context/Sagittal/TrioPlot
  tabs are a segmented grid with 1-px divider lines.
- The sample · neuron identity moved from the top-right header chip into the preview
  ribbon, immediately left of the file name; the preview caption shows only the file
  name (the "w×h shown" text is gone). The white identity and filename share the same
  lowered baseline rather than sitting at different vertical positions.
- **Update figures** is an outlined button at the right of the preview tab row, visually
  separate from the segmented panel selector; clicking it updates the preview from
  cached panels through the receipt check.
- Cards are titled **Plotting** and **Saving**; the header has a **Config YAML** button
  that opens `main_scripts/Visual_toolkit/visual_toolkit_config.yaml`.
- The Sample card has a compact scrollable stage guide for the load/acquire/review
  chain: portal raw SWC → saved `resource/swc_raw/<sample>/` file → target soma
  X/Y/Z → cached 0.65 µm Soma cubes with online fallback for missing cubes → render,
  save and **Update figures**. It states that Load & Auto-Fill does not prefetch image
  cubes. A changed save creates new timestamped PNGs, keeps older PNGs, and updates the
  receipt; the fixed-name Soma NIfTI is overwritten when selected. The Context card says
  the source dataset names (`0.65 µm CH1 blocks · 5 µm CH1 resample · CH00DS N4`); the
  Saving card explains the receipt file and the PNG-versus-NIfTI save behavior.
- Each plot card now carries its own one-line source under the fields: Soma →
  `cached or fetched online` plus `resource/cubes/<sample>/high_res_http`; Context →
  the configured 5 µm resample folder tail (or "not configured").
- The header **Config YAML** button opens an in-app **editable** viewer of
  `main_scripts/Visual_toolkit/visual_toolkit_config.yaml` with Save/Reload. Save
  validates the YAML and schema, copies the previous file to `config_backups/`, keeps a
  pristine `visual_toolkit_config.default.yaml`, and writes atomically. The loader
  falls back to the legacy `datasets.yaml` name when the new file is absent.
- Render selected/render all check the receipt and cached files first: a matching set
  loads without re-rendering (status "Cached figures reused"), and a **Force re-render**
  tick redraws even when the cache matches. Update figures remains the explicit browse
  path with the re-render prompt.
- Entry borders use a deeper slate (#8fa3b2) so the fields read as inputs.

Bulk runners
- `native_ds_swc_path` now uses the same `resolve_swc_path` as the GUI, so bulk
  exports also resolve the legacy raw-SWC cache; 251637/002 renders the Sagittal panel
  from `resource/swc_raw` instead of failing.

Validation
- 69 tests pass (GUI request/actions, panel render, bulk decoupling, contrast,
  write safety, image loader).
- Live one-neuron checks: 252527/048 (all panels), 252385/025 (corrected 5 µm path),
  251637/002 (legacy raw SWC) complete; 252383/018 and 252718/142 report
  `partial=1` with the missing 5 µm source and still produce Soma + Sagittal.
- Hidden layout check: settings column 799 px inside 1280×980; a preview-only temp PNG
  is loaded, removed, and kept in memory; Reload prompt text is exercised by unit
  tests. Live visual check of the current-code window confirmed the white identity is
  immediately left of the filename on the same lowered baseline in the purple ribbon,
  **Update figures** has a visible outline, and clicking it updated the preview from four
  cached panels for 251637/003 without error. The stage-guide live check confirmed mouse
  wheel scrolling reaches its final save/update step.

## 1.7.1 — 2026-10-17 (local/unreleased)

GUI and source resolution
- Preview shows one panel at a time (Soma / Context / Sagittal tabs); the combined
  figure is the `TrioPlot` tab and is built only on request.
- **Render all** (F6) renders the three panels and always adds the TrioPlot; it is
  styled purple to separate it from the teal **Render selected** (F5).
- **Save selected** (default on) sits beside the render actions; when off, panels are
  preview-only, their temp PNGs are deleted after the preview loads, and no receipt or
  NIfTI is written. **Open output folder** sits to its right.
- **Reload figures** button plus an automatic scan of `<output_root>/<sample>_*` load
  existing panels without re-rendering. A per-folder `visual_gui_receipt.json` records
  coordinates, settings, role files and their hashes; reload checks coordinates, the
  settings key and the file hashes, then prompts "re-render?" when anything differs.
- Output root and auto-reload come from `visual_toolkit_config.yaml` (`visual_toolkit:` block);
  the GUI still exposes the folder per run.
- A missing raw SWC for the Sagittal panel triggers one portal fetch into
  `resource/swc_raw/`, then re-resolves; the Plot-lane hint names the neuron and
  the cached count instead of a sample-wide warning.
- The toolkit's fetch/download/render lines are mirrored in a **Process log** panel and
  in the status strip; the progress bar runs for the whole render.

Sources and package layout
- `sagittal.py`, `dataset_config.py` and the YAML config moved into this package;
  the toolkit, GUI and bulk wrappers import `VisualToolkit.sagittal` /
  `.dataset_config` (no copies under `tools/` or `config/`).
- `resolve_swc_path()` order: registered `swc_cache`, then
  `resource/swc_raw/<sample>/<neuron>.swc`; provenance records `swc.source`
  (`registered_cache` / `legacy_raw_cache`).
- Panel failures are isolated: one unavailable panel is reported and the others
  still render, save and preview.
- Figures are named `<sample>_<neuron>_<region>_<YYYYMMDD-HHMMSS>_<Role>_Plot.png`
  (role suffix last, so suffix readers keep working); the NIfTI name is unchanged.

Validation
- 68 tests at the time; a live F5 at 17:18 wrote timestamped Soma/Context/Sagittal
  PNGs, the Soma NIfTI and `visual_gui_receipt.json`, did not regenerate the TrioPlot
  with its tick off, and showed the fetch/download lines in the process log.

## 1.7.0 — 2026-10-17 (local/unreleased)

- Binavi-style two-column window: settings cards left, figure preview right, navy
  header, teal accent, pale borders.
- `Plot` lane (Soma / Context / Sagittal ticks) and `Save` lane (per-PNG ticks,
  Soma NIfTI, output folder; Context NIfTI kept out of the GUI).
- Default output moved from `resource/segmented_cubes/<sample>` to
  `work/visual_gui/<sample>_<YYYYMMDD>`, resolved from the module (not cwd).
- `plot_soma_block` / `plot_widefield_context` return `output_png` for the preview.

Validation
- 22 tests at the time; a live F5 run produced all three panels plus the TrioPlot, and
  the settings column measured 796 px inside the 1280×980 window.

## 1.6.0 — 2026-10-17 (local/unreleased)

- One target marker for all panels: cyan/turquoise (`#00e5ee`) box + cross on the
  exact mapped point, drawn by a single helper.
- `REVIEW_SETTINGS` as the shared settings source (marker, soma window, context,
  widefield gain/threshold, scale bars, figure sizes).
- Soma panel uses a soma-centred 1.5-cube window (≈351 µm) with descending centred
  steps and a recorded centre offset; resizable layout with a layout-derived
  minimum size.

Validation
- 63 tests; 252527 25/25 neurons at 1.5 cubes with ≤0.5 px centre offsets; a complete
  sample re-rendered byte-identically to the pre-fix output.

## 1.5.0

- Auto-load the default neuron (`003.swc`) on startup; silent coordinate fill;
  thread-safe status updates.

Validation not recorded in the original header; behaviour retained as the legacy
baseline and covered indirectly by the GUI request tests.

## 1.4.0

- Soma region and formatted coordinates in plot titles/filenames; optional cache
  directory for bulk processing.

Validation not recorded in the original header; behaviour retained as the legacy
baseline (titles/filenames only, no voxel changes).

## Earlier

- Pre-package GUI (`main_scripts/Visual_toolkit_gui.py`): Soma Plot / Wide-field
  Plot / Plot Both, fixed 700×700 window, output under
  `resource/segmented_cubes/<sample>`.
- Reference baseline for the v1.7.0 comparison; the fixed frame clipped the status bar
  once review actions were added, which v1.6.0/v1.7.0 fixed.
