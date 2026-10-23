# VisPa change log

## 1.11.0.dev7 — 2026-10-23 (local/unreleased)
- Remove the `Visual_toolkit` Python compatibility namespace, `Visual_toolkit`
  class alias, and `visual-toolkit`/`visual-toolkit-gui` entry points. `vispa`
  and `vispa-gui` are now the only supported imports and commands. Existing
  `visual_toolkit` settings blocks and `visual-toolkit.*.v1` receipt schemas
  remain readable data contracts.
- Restrict installer and Windows-VM payload verification to `src/vispa`, so a
  fresh installation can no longer succeed by resolving retired forwarding
  files. This also reduces the packaged Python/YAML set from 48 to the files
  actually implemented by VisPa.
- Remove the public-neuron example from the organized GUI and Settings form.
  The bounded `vispa example` CLI remains available as a separate optional
  morphology-only command. Six focused config-editor tests and the real Tk
  Settings-window regression passed.
- Convert the normal operator surface to Python modules only. Remove the
  generated `vispa`/`vispa-gui` console scripts, `install.cmd`, `VisPa.cmd`,
  custom Miniforge bootstrap, installer harness, and VM launcher. Conda now
  creates the environment from `environment.yml`; use
  `python -m vispa` or `python -m vispa.gui` from the IDE or terminal.
- Include `PyGLM==2.8.3` and `glfw==2.11.0` in the Conda environment's pip
  section, replacing the dependency step formerly performed by the custom
  installer and making the 3D renderer installable from the clone alone.
- Validation: the full source and editable-installed suites each pass 131/131
  with zero skips; Conda environment solve and module/GUI dry runs pass; the
  editable package imports from `D:/VisPa/src/vispa`, and the Conda environment
  contains no VisPa/VisualToolkit console scripts. The current 252385/044 demo
  config, recorded panel hashes and 3D snapshot remain valid.
- Fresh-clone validation of the published `simplified` branch at
  `89cd4927639b06b757af4a3459a96c0b5d953f96`: cloned the public repository,
  created a clean Conda prefix from `environment.yml` including pip-installed
  PyGLM/GLFW, installed the package editable, and passed the full 131/131 suite
  plus version, config, and GUI dry runs. Hosted Windows Conda run
  [39918504013](https://github.com/bylaikaby/VisPa/actions/runs/39918504013)
  passed for the same commit. The cloned DS00 montage test module passed 10/10,
  and a real 251637 five-view montage rendered successfully with a role legend
  and plane-specific RAS+ axes. Projectome adapter/caller focused suites passed;
  the complete Projectome suite remains a separate pending check. No scientific
  or anatomical acceptance is implied.

## 1.11.0.dev6 — 2026-10-23 (local/unreleased)
- Replace the default Windows Python/venv install with a Conda-first source install. When Conda is absent, the installer downloads a pinned Miniforge installer and verifies its official SHA-256 before running it; the dedicated environment includes the review and 3D dependencies. The launcher uses the recorded per-user prefix without PATH edits or activation. Existing user configuration and cache are preserved on repeat installation. These behavior changes require a new environment; the dev5 venv remains historical.
- Add a bounded Windows VM operator that downloads the exact commit as an anonymous HTTP ZIP, tests bootstrap in an isolated process profile, installed CLI and GUI lifecycle, Settings callbacks, real public SWC technical rendering, and repeat-install preservation. It reports OpenGL context rendering separately from VisPa's actual brain-view operation and leaves the latter pending real local demo assets and visible review. The workflow invokes this operator and uploads its compact receipt and review figures.
- Remove the prominent Public neuron example button and Organized Settings section while keeping the compatibility CLI and editable raw source keys. The configured intranet neuron workflow remains the normal GUI path.
- Read a verified local image block cache before requiring an HTTP host, so an offline local demo can use valid cached blocks without a network source. A cache miss still requires the configured host and fails clearly; no image geometry or rendering math changed.
- Align package identity, headers, distribution source manifest, and the fresh-Windows guide with the dev6 candidate. Registration and rendering algorithms are unchanged.
- Validation so far: PowerShell VM operator parses, its dry-run resolves one bounded case, and the workflow YAML parses. The combined dev6 source suite passed 137/137 with zero skips using the existing dev5 runtime for dependencies. The isolated dev6 Conda environment passed its installed 137/137 suite, launcher/version/config checks from another working directory, and exact 48/48 source/runtime Python/YAML file-set and hash parity; repeat installation preserved the fresh profile and launcher handle hashes. A temporary local cache fixture rendered four panels through the source loader with network calls blocked; that fixture was superseded by a server-connected local example now in preparation and is not packaged. Hosted Windows run 39905581372 downloaded the exact commit ZIP and passed installer dry-run, then failed during fresh Miniforge bootstrap because child Windows PowerShell could not resolve Get-FileHash; a module-free streaming .NET SHA-256 replacement passed the Windows PowerShell 5.1 harness. Hosted run 39906305957 verified the Miniforge download and checksum, then its silent installer exited 2 under a profile path with spaces. Because Miniforge documents limitations for such paths, the installer now rejects an unsafe default bootstrap path before network activity and accepts an explicit writable ASCII no-space `-MiniforgeRoot`; the VisPa environment path remains independently selected. The Windows PowerShell 5.1 installer harness passed 10/10 with that override. Hosted rerun, graphics capability, and visible GUI review remain pending; exit 2's specific cause was not independently established.

- Hosted run 39907361693 bootstrapped Miniforge with the explicit no-space root and completed the Conda package transaction in a spaced VisPa environment, then failed when Conda's pip subsection invoked activation on that spaced prefix. The environment file now leaves pip as a Conda package and the installer runs the pinned PyGLM/glfw wheels through the target Python directly, avoiding Conda's pip activation. Windows PowerShell 5.1 installer harness passed 10/10; hosted rerun and installed validation remain pending.
- Hosted run 39908174068 passed fresh Conda installation, exact 48-file installed payload parity, CLI/config, public SWC technical rendering, repeat preservation, installed Tk Settings callbacks, and 137/137 installed tests without skips. The OpenGL context probe was unavailable or failed; its exact diagnostic was not saved, and actual VisPa brain-view operation remains unverified. The job exited nonzero only because the optional probe left PowerShell's `$LASTEXITCODE` set. The VM operator now returns success only after every mandatory gate passes, while retaining a partial-graphics receipt and bounded GL diagnostic; a hosted rerun of that operator change remains pending.
- Remove the now unreachable GUI-only Public example worker/queue after its visible control was removed; the `vispa example` CLI and existing preview-file handling remain. Reuse one strict public-source validator for config loading and direct example calls, retaining valid URL/source fields and checksum casing at config load while normalizing the render pin. These refactors do not change scientific render math. The source suite passed 136/136 after removing one obsolete private-GUI test; 71 focused CLI/config/example tests passed. Exact-byte Settings backup/default guards remain, while two display-text assertions now tolerate checkout line endings. Historical pip lockfiles and the CI-only VM runner remain tracked but are excluded from the source distribution; the 48-file wheel payload is unchanged pending a new build check.

## 1.11.0.dev5 — 2026-10-23 (local/unreleased)
- Organize Settings into six visible form sections, an editable Raw YAML/JSON tab, and a read-only Default YAML reference. Invalid active YAML remains visible in Raw for correction. On first open, preserve a named local copy of the installed default profile without replacing an existing copy; if unavailable or invalid, show the packaged profile with a warning. Reset and Restore backup stage a draft until Save. Save keeps validation and external-change guards, preserves no-op bytes, and writes unique, byte-identical prior-content backups; a failed backup blocks replacement. Explicit selection of either the frozen local default or packaged default as an active config is refused on Save. Changed form saves keep unknown keys but may reformat YAML comments and whitespace. Switching tabs keeps valid unsaved drafts; FNT setup opens FNT directly. No scientific processing behavior changed. Align current source, wrapper, installer and test headers with dev5. Validation: 8/8 focused config/editor tests and 136/136 final source tests pass without skips, covering startup correction, read-only default, draft preservation, reset/restore, distinct backups, backup failure and protected-default refusal. The final wheel and installed runtime match all 48 source Python/YAML files byte-for-byte, with zero extras or missing files; CLI reports dev5 and `pip check` passes. Installed Settings created a frozen local default copy matching the packaged profile without modifying the active config. Visible desktop review remains pending.

## 1.11.0.dev4 — 2026-10-22 (local/unreleased)
- Validate the installed config without probing declared microscopy shares: `config-check --validate-only` checks schema and path declarations, and the installer uses it before user PATH registration. UNC child resolution stays lexical when a share is offline; ordinary `config-check` still reports source availability. Validated with an offline UNC regression and the Windows installer harness.
- Correct first GUI launch when inherited legacy config environment variables are present: only the VisPa-specific explicit config suppresses own per-user config creation. The legacy paths remain untouched; verified by the source GUI regression and full suite.
- Make VisPa startup and the installer select VisPa-owned configuration and per-user cache/output paths. A fresh install creates `%APPDATA%\\VisPa\\vispa_config.yaml` from the packaged lab profile and registers `VISPA_CONFIG` and `VISPA_PYTHON`; an explicit `-Config` remains available for a local profile. Older VisualToolkit environment variables and files are preserved but require explicit selection for VisPa use, preventing stale project settings from becoming the normal active profile.
- Add a common settings editor for the active local YAML/JSON file with validated, atomic writes and change detection. Its controls include data roots, source endpoints, FNT settings and the public example; other scientific declarations remain in the same config file. The GUI title and header display the single package version.
- Add exact one-neuron FNT fetching with bounded response validation, source and catalog-bound project hashes, a reusable VisPa cache, and separate project/executable readiness. Existing explicitly configured projects take priority. A cached Render still checks the FNT resource; the normal workflow does not require a separate FNT application window or manual project folder.
- Extend the existing Windows installer and guide for ZIP-extracted source, per-user runtime, fresh setup, repeat installation and explicit offline wheelhouse use. Preserve existing config and cache on rerun; keep source/share data as candidate read-only references. No image geometry, anatomical acceptance, or renderer algorithm changed.
- Put ZIP extraction and `install.cmd -NoLaunch` first in the fresh-PC guide; Git remains an optional source-update path. The installer already autodetects the source checkout, so no command behavior changed.
- Validation: the current source suite passed 134/134 tests, the Windows PowerShell installer stub harness passed 9 checks, and all 48 Python/YAML payload files in the dated wheel matched current source bytes. The Windows Server VM fresh-install check and installed-runtime parity remain pending; this local candidate is unreleased. The VM workflow checks bounded public installation behavior and records evidence without asserting lab desktop, microscopy-source, anatomical or scientific acceptance.

## 1.11.0.dev3 — 2026-10-22 (local/unreleased)
- Configure a fresh per-user profile for the same-intranet IONData neuron catalog, ten known sample-to-AnimalID mappings, candidate microscopy links, and platform-resolved user caches/outputs. Keep image cubes, raw SWCs, and microscopy shares on separate providers; include no scientific data, credentials, local worker paths, or assumed anatomical acceptance. Existing user configurations remain in place.
- Add explicit Live IONData selection beside dated CSV snapshots in the neuron list. Preserve exact IDs and suffixes; show source, sample, row count, fetch time/date, URL/path, and SHA-256 provenance. Legacy CSV profiles keep CSV as default and may explicitly opt into Live IONData, with no silent fallback. Keep the table to SWC ID and Portal region and identify the cohort AnimalIDs in a small note without neuron-level INS classification.
- Add a bounded single-sample `config-check --catalog` operator path and resolve a persistent raw-SWC cache under the user data folder when both HTTP source endpoints are configured and no explicit cache root is supplied; config loading does not create that folder.
- Update the fresh-install, config-init, existing-config, live-catalog, and same-intranet source guidance. Synchronize package metadata, CLI/GUI identity, and module headers to `1.11.0.dev3`.
- Validation: Canonical source suite passed 109/109; 35 focused neuron-catalog, live-source, and CLI tests passed, including legacy CSV explicit-live opt-in, dry-run/no-network behavior, bounded response handling, stale selection guards, and provenance. The neutral `config-init --dry-run` selected package defaults only, and the default profile kept per-user caches/outputs while leaving worker/FNT paths and auto-load unset. Three bounded live catalog checks returned 234 (250432), 574 (251637), and 128 (252385) unique IDs; every exact ID set matched the registered 20261009 inventory, and CSV opt-in returned 234 unique 250432 IDs. A withdrawn-root Tk geometry smoke fitted the two-column list in a 560×600 window (content row 288 px within 536 px). These checks do not establish all intranet image/SWC sources are reachable on a fresh PC or provide visible-GUI, anatomy, or scientific acceptance.

## 1.11.0.dev2 — 2026-10-22 (local/unreleased)
- Repair fresh Windows installation startup by omitting `Start-Process -ArgumentList` when no config is selected and quoting a configured path so it arrives as one GUI argument. Report dependency installation separately from GUI launch and give a direct recovery command when launch fails; include the Windows PowerShell 5.1 regression harness in source archives for reproducible installer validation.
- Select Python 3.13 explicitly with the Python launcher by default, then try a validated `python` command if that launcher cannot provide the runtime; preserve `-Python` as one executable path. The PowerShell 5.1-safe probe reports executable, version and bitness without embedded quote-sensitive Python literals, and validates 64-bit Python 3.10+, pip and Tcl/Tk before environment creation and an existing target before pip.
- Synchronize the package, compatibility wrappers, module headers, GUI title and CLI metadata on `1.11.0.dev2`; the GUI title reads the package's single version source.
- Reject neuron IDs containing either slash style on every operating system, and defer packaged default YAML parsing until an actual toolkit instance is constructed. Sample-path lookup uses the activated config when present, so clean settings/help imports stay free of PyYAML while existing per-user YAML settings still apply at toolkit import.
- Add a public morphology-only macaque SWC example with checksum-pinned provenance and full-extent XY/XZ/YZ/3D views. The 3D axes are labeled Source X/Y/Z, the title identifies the SWC, and unknown coordinate frame/units remain explicit; no image cubes or atlas are paired with the morphology.
- Cap the default Matplotlib resolver at `<3.11.1`: the 3.11.0 reference runtime is validated, while a user-reported Linux/Python 3.13 labeled-layout failure occurred with 3.11.2. This retains resolution for the package's Python 3.10 minimum; 3.11.1 is not independently tested, and the reported failure was not reproduced here.
- Validation: Windows PowerShell 5.1 production-installer harness passed 10 checks, including the real CPython 3.13.13 JSON probe, default `py -3.13` selection, fallback when that launcher exits unsuccessfully, no-config launch, spaced config and Python paths, `-NoLaunch`, unsupported base Python rejection before environment creation, and invalid existing-target rejection before pip. The 10 OpenGL tests, 39 core/source-config tests, and 12 CLI contract tests passed in `.venv`; standalone import checks passed in a fresh subprocess, and an existing user YAML was confirmed to override the default marker color. Public example tests/render validation: six focused tests passed and a 14,086-node SWC rendered successfully. The source-tree CLI reports `1.11.0.dev2`; the full source suite passed 99/99 with canonical source imports and dependencies shared from the unchanged VisPa validation environment. The final wheel installed through the production PowerShell 5.1 installer passed the full 99/99 installed suite; both installed CLI aliases and the GUI title report `1.11.0.dev2`. A withdrawn-root Tk callback registered the public preview. The candidate environment reused dependencies from the unchanged validation environment with package-index access disabled; this was not a fresh isolated-PC/network installation. No visible GUI or scientific/image alignment acceptance is claimed.

## 1.11.0.dev1 — 2026-10-22 (local/unreleased)
- Document a complete fresh Windows setup using tested standard Python 3.13, public HTTPS Git or ZIP without a GitHub account, explicit interpreter/install verification and bounded troubleshooting; documentation checked against installer flags, not a fresh-PC execution.
- Rename standalone package/distribution/commands to VisPa (`vispa`), preserving legacy imports/class/commands, existing v1 protocol schemas and configuration/cache discovery. Legacy qualified imports share primary module objects; optional GL remains lazy. New VISPA_* environment names take precedence over old aliases. Installer uses a fresh VisPa location and rejects overlapping legacy distribution ownership. Current operator documentation and visible branding use VisPa while legacy user config/cache paths remain unchanged. Renderer settings propagation resolves the primary VisPa class; new/legacy environment overrides are isolated in test fixtures. Validated by 92/92 installed-wheel tests and 27/27 project-adapter tests. Scientific and full GUI acceptance remain pending.

# VisualToolkit change log

One consolidated history for the standalone package. `README.md` is the operator
guide; per-module headers carry `Version:` / `Last updated:` / `Change history:`
and point here.

Entries are newest first. "Local/unreleased" identifies a development build
that has not been released; Git history records when changes were committed or
published. Dates are Asia/Shanghai.

## 1.11.0.dev1 — 2026-10-22 (local/unreleased)
- Advance the local build identity for today's packaging and make the installer use its current source checkout by default; explicit `-Wheel` remains available, and conflicting source/wheel options fail clearly. This avoids choosing stale same-version distributions by filesystem mtime.
- Document explicit-wheel offline installation and preserve `extraction_manifest.json` as historical extraction provenance. No renderer algorithm or scientific result changed.
- Validation: installer selection dry-runs, source/sdist/wheel inspection, fresh isolated install, installed package and focused Projectome tests recorded in the shared validation receipt.

## 1.11.0.dev0 — 2026-10-22 (local/unreleased)
- Add measured outside-image role legends to every standalone panel PNG, preserving full image extent and indexed axes; no source/intensity changes.
- Route GUI review figures through the shared legend layout, expose true crop-pixel axes in Soma/Context single and combined views, and fingerprint GUI/toolkit code hashes so old strips are not silently reused under the same local package version.
- Default inline soma labels to none while retaining the cyan box/cross and role legend; expose marker.label_mode none/short/numbered through settings, with compact S or numbered callout alternatives. Shared single-panel and combined rendering use the same marker helper.
- Derive combined-figure footer wrapping, physical height and labeled-axis clearance from rendered font metrics; top-anchor full-extent panels to align titles/images across aspects. No image crop, resampling, intensity or coordinate change.
- Add a read-only exact-neuron resource inventory to `config-check` and strict FNT executable plus matching-project preflight; no binary version command is executed, unavailable shares remain unverified rather than missing.
- Add **FNT setup…** with executable/project-folder browsing and existing validated atomic YAML/JSON persistence; reject concurrent config edits. FNT launch now requires the matching project instead of silently opening an empty application.
- Validation: focused resolver and installed suite results are recorded in the project validation receipt; GUI visual review remains separate.

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
