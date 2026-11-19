## Flip comparison display 0.1.2 — 2026-11-18 (local/unreleased)
- Add receipt-checked plot-only effect summary with changed-pair counts, separate ARI rows, aligned neuron counts and relative Score distribution. No scientific recomputation; bounded9 and full490 plot-only renders passed, source artifact hashes verified and figure visually inspected.

# ReMAP change log

## Review renderer 0.1.14 — 2026-11-19 (local/unreleased)

- Added a receipt-bound atlas-insula display for the framed hierarchy. It preserves the applicable parent branches, labels, target order and color scale. The 490-to-309 render, pairwise merge heights, candidate labels and all 22 legend entries were checked. The CLI dry run and all 43 ReMAP source tests passed.

## Review renderer 0.1.13 — 2026-11-19 (local/unreleased)

- Moved hierarchy annotation keys into one light, bordered panel. Three sections use compact swatches, aligned counts and the study palette. Verified all 22 entries and frame fit, then visually inspected the 490-neuron result. The saved assignments, leaf order and region rows matched. All 43 ReMAP source tests passed.

## Review renderer 0.1.12 — 2026-11-19 (local/unreleased)

- Added explicit neuron-type, animal-ID and candidate-cluster legend rows with observed neuron counts. Matched the annotation-strip labels to the keys. The 490-neuron rerender preserved the saved candidate assignments, leaf order, 16 target rows and projection strengths. All 22 entries passed label/count and spacing checks. Full plot visually inspected and all 43 ReMAP source tests passed.

## 0.2.2.dev3 — 2026-11-18 (local/unreleased candidate)

- Added the progress CLI and shared report API for saved Projectome Progress Manager exports. The read-only join validates counts by sample, ARM parcel and soma hemisphere. PNG exports record source and renderer hashes. The 212-case pilot and full 309-case render passed. All 43 ReMAP tests passed in the existing pytest-capable environment.

## Insula area–function evidence 0.1.0 — 2026-11-18 (local/unreleased)
- Package the versioned CSV with source-localized evidence for each of the five insula labels. Published Iai terms, the Ig candidate and contextual observations carry explicit use statuses. Source resource access, schema, published term parity and coverage checks passed. See the reading resource for its SHA-256 and scope.

## Review renderer 0.1.11 — 2026-11-18 (local/unreleased)
- Match branch colors to the candidate cut, align cluster boundaries across the matrix, and distinguish zero values from positive strength on a common bilateral scale. Existing clustering and table contracts are preserved. The full 490-neuron replay matched the saved assignments, leaf order and region order. Final PNG visually checked.
- Add per-neuron projection fraction distributions with zero values, median and IQR. CLI options are --projection-distribution, --distribution-regions and --distribution-seed. Four focused package tests passed.

## Review renderer 0.1.9 — 2026-11-18 (local/unreleased)
- Added optional paper-inspired neuron-by-target strength, annotated dendrogram/distance and cluster-level projection styles. Public style, prevalence threshold, DPI and length-unit controls preserve existing defaults; clustering and workbook behavior are unchanged. Three bounded style tests and 490-neuron renders passed; saved assignment and leaf orders match, and figures were visually inspected. Strength uses the existing rounded log10(1 + retained atlas-voxel length) contract.

## FNT progress monitor 0.1.1 — 2026-11-18 (local/unreleased)
- Recognize complete prepared-distance and full-pipeline receipts only after checking expected pair metadata, joined/distance hashes, and producer source-record consistency. Both real receipt forms passed; wrong path/count, corrupted hash, incomplete source records and malformed JSON were rejected. No FNT calculations or outputs change.

## Matched flip comparison 0.1.1 — 2026-11-18 (local/unreleased)
- Normalized only provenance-only source_config, deliberately omitted by full FNT producer receipt serialization but retained in prepared-distance receipts. Resolved cases, source hashes, tools, preprocessing midline, decimation and clustering remain strictly matched; original receipts untouched. Bounded asymmetric-wrapper comparison passed and changed resolved decimation rejected; full490 comparison completed, output hashes verified and chart visually inspected.

## Review renderer 0.1.8 — 2026-11-18 (local/unreleased)
- Improved space between review rows and separated overlapping cluster labels with leader lines; clustering, neuron order, and projection data are unchanged. Focused rendering tests passed 2/2; the 490-neuron folded-data rerender matched the original neuron and region orders and was visually inspected.

## Matched flip comparison 0.1.0 — 2026-11-18 (local/unreleased)
- Added compare_flip.py for source/hash/plan-controlled unordered FNT pair comparison and frozen-profile ARI plus optimally label-aligned reassignment. Existing nine-neuron initial comparison and reversed/duplicate pair checks passed; hardened rerun pending. No changes to FNT computation or workbook layout.

## Review renderer 0.1.7 — 2026-11-18 (local/unreleased)
- Separate medoid/farthest morphology panels, external identities and common square physical extent; no changes to neuron selection, transforms or clustering. One-cluster bounded and full-nine rendering completed; visual review and identical example/source/transform records verified.

## Review renderer0.1.5 / profile0.1.3 � 2026-11-18 (local/unreleased)
- Added hash-bound medoid/farthest SWC review through existing preprocessing, root-centered display only, shared full shown-neuron extents and configurable coordinate planes. Nine-neuron rendering pending.
- Restored legacy square-root-fraction Euclidean projection silhouette as primary diagnostic; cosine remains separate sensitivity. Projection-derived types mean this is descriptive cross-channel evidence, not independent biological validation.

## FNT progress monitor0.1.0 � 2026-11-18 (local/unreleased)
- User-requested terminal/HTML progress for an existing worker, incremental complete-line counting, elapsed/approximate remaining time and receipt-gated completion. Public PID/path/interval/start-time/once options; no calculation restart or algorithm change. Partial-line/no-double-count/completion tests passed; attached to full490 worker.

## Review renderer 0.1.4 � 2026-11-18 (local/unreleased)
- Connected optional producer-hash checks, diagnostics, unknown-label policy sensitivity and source-workbook evolution to existing review CLI. Zero-penalty duplicate omitted; completion receipt written only after requested artifacts finish. Nine-neuron integration run pending.

## Prepared-distance execution � 2026-11-18 (local/unreleased,0.2.2.dev2)
- Added hash/order/executable-checked distance-only API with public10..86400-second timeout, default4h; retains incomplete outputs on failure. Nine-neuron45-pair test and490-input dry run passed;15 comparison/review/FNT regression tests passed. Full490 uses explicit6h budget and identical retained joined FNT; no preprocessing/join repeat.

## Review profile 0.1.2 � 2026-11-18 (local/unreleased)
- Reuses fixed-matrix resampling and monkey holdouts through an explicit legacy-linkage callback; default arbitrary-distance linkage guard remains unchanged. Adds projection cosine silhouette using all bilateral fractions. Synthetic27-neuron fixture passed42 cuts and378 holdouts with exact fitted-label agreement. Actual regression modules running after correcting a nonexistent test-module name.

## Review renderer 0.1.3 � 2026-11-18 (local/unreleased)
- Optional aligned monkey strip with declared palette and legend. Synthetic nine-monkey layout rendered and inspected; header overlap identified and top margin adjusted, awaiting real-cohort visual check. Two review tests passed before margin-only adjustment.
- Cohort source workbook assembly completed:1727 rows, composite identity/unscored fixture passed, originals retained externally.

## Review profile 0.1.1 � 2026-11-18 (local/unreleased)
- Added explicit known_only unknown-type policy with legacy_label default preserved. Cohort profile keeps seven Unclassified labels and gray plot annotation; legacy comparator remains required. Policy/regression verification is running, not yet accepted.
- Extended clustered_table evolve with explicit all-samples composite identities; original single-sample API unchanged. Existing workbook regression passed. Added reusable cohort Summary assembly with per-row workbook SHA, source row and inclusion; composite-ID fixture and real assembly running. No packaging/install.

## Review renderer 0.1.2 � 2026-11-18 (local/unreleased)
- Added explicit missing-region-policy= sparse_zero for cross-workbook sparse projection columns; default remains error. Existing source cells must remain finite/nonnegative. Original exporter semantics inspected; all490 rows and134 bilateral L3 columns validated, two existing review tests pass. No source tables changed.

## 0.2.2.dev2 � 2026-11-18 (local/unreleased)
- FNT public settings accept explicit max_cases (default32, cap1000). Large joins use short hard-linked input names in a declared working directory to avoid Windows command-length overflow; preprocessing and distance algorithms unchanged. Existing12 FNT tests pass;490-source preflight passed;33-neuron compact-join workflow in progress. No build/install.

## Review renderer 0.1.1 — 2026-11-18 (local/unreleased)
- Added review_plot CLI/API driven by the reusable legacy profile: exact composite-identity table alignment, all-region projection normalization, shared scales, no-overwrite output and hash-bound receipts. Exposes DPI, top-region count and display cut. FNT production unchanged.
- Two focused tests passed; real251637 dry-run/render visually inspected; all42 assignments and16 displayed regions match saved baseline. Broader unittest attempt:37 passed, DS00 selection module unavailable because pytest is absent; not a complete-suite pass.

Package versions are listed below. Each script also keeps this brief history in its own header.

## 0.2.2.dev1 — 2026-11-17 (local/unreleased)

- Comparison runs now write hash-bound completion metadata after all CSV outputs; interrupted runs without metadata remain incomplete. Synthetic regression passed.

- Added explicit ratio-score sensitivity to saved-score comparison, reusing the existing validated Score / (Match + NoMatch) path. Raw remains default; 13 focused tests passed and four bounded 100-subsample runs completed.

- Identified the integrated changes as an unreleased candidate and added the package version to new comparison, plot and table metadata. CLI reports 0.2.2.dev1; focused operator tests passed.

- Added candidate saved-score comparison module using shared transformations and subsampling diagnostics. All four 212-neuron comparisons matched legacy candidate cuts exactly and diagnostics within 3.9e-14; 35 unittest cases passed.

- Added candidate score_plot module with validated FNT matrix, linkage and embedded input hashes; dry-run, 212-neuron render, metadata and existing-output guard verified; 34 focused unittest cases passed.

- Added experimental clustered-table export with exact identity checks, candidate-column validation, dry run and no-overwrite behavior. Small fixture, failure guards, full-workbook CLI dry-run and output readback passed against the independently checked candidate workbook; 33 unittest cases passed, including clustered-table coverage and deterministic missing-atlas simulation.

- Brought ReMAP into the VisPa repository at packages/remap from standalone commit 619fdd0e3e1bdfa04dcd5a3464ba30d93dcf70a7. Preserves the remap package and CLI.

## Script histories

### `run_analysis.py`
- 2026-10-25: `core.py` measured one declared SWC (`analyze_one`).
- 2026-11-10: Renamed `one_neuron.py`, then `run_analysis.py`.
- 2026-11-10: `remap run --case animal_id/neuron.swc` fills the cache from IONData and writes one workbook per animal. Several animals produce one grouped receipt.

### `population_operator.py`
- 2026-10-25: Step1 population plan and workbook receipt.
- 2026-11-10: Stable animal folder (`neuron_table/`, `report/report_plots`, `swc_plots`). Optional summary plots and SWC montage/each.
- 2026-11-10: Omitted atlas paths come from the designated fMOST profile. Cross-drive registration paths no longer drop the receipt.

### `region_analysis/neuron_table.py`
- 2026-11-09: Folded the small region workers into one workbook module.
- 2026-11-10: Laterality is applied before save. Soma side columns are `prefix_derived` and `location_derived`.
- 2026-11-10: SWC shape plots are off unless `montage` or `each`. Hierarchy fallback can use the designated atlas key.

### `region_analysis/neuron_loader.py`
- 2026-11-09: Cache hit stays as stored. Missing SWC, or refresh, fetches from IONData.
- 2026-11-10: Moved from the package root into `region_analysis/`.

### `region_analysis/neuron_swc.py`
- 2026-11-10: `NeuronTracer` moved here as the single-neuron load and shape-plot unit.

### `region_analysis/hierarchy.py`
- 2026-11-10: CHARM/SARM parent tables moved in from `hierarchy_table.py`. ARM key still repeats a label only inside its declared levels.

### `region_analysis/overview_plots.py`
- 2026-11-10: Renamed from `plotting.py`. Summary QC only. Unknown terminals and outlier counts stay in the terminal and projection-site reports.

### `morph_clustering/fnt_pipeline.py`
- 2026-10-29: Legacy FNT producer.
- 2026-11-10: Moved under `morph_clustering/`. Server FNT bin first, local bin after 8 seconds. Intermediates go to the FNT cache.
- 2026-11-10: A run that never writes `receipt.json` removes only the output directory it created.

### `morph_clustering/neurom_analysis.py`
- 2026-11-09: NeuroM dendritic features beside the region workbook.
- 2026-11-10: Moved under `morph_clustering/`. No package-root copy.

### `morph_clustering/clustering_validation.py`
- 2026-10-30: Distance-matrix and linkage checks.
- 2026-11-10: Moved under `morph_clustering/`.

### `ds_normalisation/coordinates.py`
- 2026-11-03: `CoordinateRoute` for raw, native, pitch, and NMT points.
- 2026-11-10: `ProinsDs00Route` follows the Pro_INS stages. The rigid frame is supplied per DS00 case.
- 2026-11-10: Moved into `ds_normalisation/`.

### `ds_normalisation/ds00_selection.py`
- 2026-11-03: Read-only DS00 selection registry. `region_ready` stays false.
- 2026-11-10: Moved into `ds_normalisation/`.

### `atlas_profile.py`
- 2026-11-09: Designated fMOST share atlas from VisPa `config_deb.yaml`. Explicit paths still win.

### `registration_path.py`
- 2026-11-09: Same-drive paths stay relative. A Windows cross-drive pair keeps the finished output path.

### `config.py`
- 2026-11-10: Packaged YAML profile for resources, cache, and output.

### `cli.py`
- 2026-11-09: `one`, `population`, FNT, table, and DS00 selection commands.
- 2026-11-10: `one` and `population` use designated atlas defaults. `run` starts from animal and neuron IDs.
- 2026-11-10: Imports follow `ds_normalisation/`, `morph_clustering/`, and `run_analysis.py`.

## 0.2.1 - 2026-11-10 (local/unreleased candidate)

- Reconciled `origin/main`: designated fMOST atlas profile, cross-drive registration paths, and removal of an FNT output directory that never received `receipt.json`. Local module layout is unchanged.
- Renamed `one_neuron.py` to `run_analysis.py`. `remap run --case animal_id/neuron.swc` loads each SWC from cache or IONData and writes that animal's workbook. Repeating the case for other animals writes one grouped receipt.

## 0.2.0 - 2026-11-10 (local/unreleased candidate)

- DS00 selection and point routes live in `ds_normalisation/` (`ds00_selection.py`, `coordinates.py`). The rigid reference frame is supplied per DS00 case.

## 0.1.0.dev46 - 2026-11-10 (local/unreleased candidate)

- Added `ProinsDs00Route` in `coordinates.py`. Point stages follow the Pro_INS DS00 chain: raw SWC, native NIfTI, N4 (same points), that case's rigid reference frame, sharedPitch10, selected NMT registration. The rigid frame is supplied per DS00 case. The older `CoordinateRoute` is unchanged.

## 0.1.0.dev45 - 2026-11-10 (local/unreleased candidate)

- Renamed `core.py` to `one_neuron.py` (`analyze_one`, `prepare_atlas`, `sha256`). No package-root `core` module.

## 0.1.0.dev44 - 2026-11-10 (local/unreleased candidate)

- Moved `neurom_analysis` into `morph_clustering/`. No package-root copy. `remap.neurom_*` lazy names still resolve.

## 0.1.0.dev43 - 2026-11-10 (local/unreleased candidate)

- Removed package-root `fnt_pipeline.py` and `clustering_validation.py` aliases. Import `remap.morph_clustering` only.

## 0.1.0.dev42 - 2026-11-10 (local/unreleased candidate)

- Soma side provenance columns are `prefix_derived` and `location_derived`. Removed `Soma_Side_Method` (and the old `Soma_Side_Name` / `Soma_Side_Reference` names). Final `Soma_Side` is unchanged: prefix first, then location fill for Unknown, conflict still forces Unknown.

## 0.1.0.dev41 - 2026-11-10 (local/unreleased candidate)

- Added `region_analysis/INSULA_NOTE.md`: ARM insula is the Full_Name-contains-insula set plus curated fine labels (not Ial alone). Documents rescue labels, the 2 mm potential-insula rule, and the 251637 full-table check (212 ARM-insula unchanged; 12 added neurons outside both rules).

## 0.1.0.dev40 - 2026-11-10 (local/unreleased candidate)

- SWC shape figures are off unless `swc_plots` is `montage` or `each`. `montage` draws at most 12 neurons on one sheet and leaves the rest undrawn. `--generate-plots` writes only the summary report plots.

## 0.1.0.dev39 - 2026-11-10 (local/unreleased candidate)

- Neuron-table output is `<output>/<sample-id>/neuron_table`, `report/report_plots`, and `swc_plots`. Text reports stay in `report`. The sample id is the animal folder.

## 0.1.0.dev38 - 2026-11-10 (local/unreleased candidate)

- Test temporary directories stay under this package's `work/test_tmp`. An explicit local FNT `output_root` keeps its intermediate cache beside that folder. Server `remap_outputs` and `cached_data/fnt` remain the defaults for a real run.

## 0.1.0.dev37 - 2026-11-10 (local/unreleased candidate)

- FNT results go to `\\10.102.8.200\microscopy_data\fMOST\remap_outputs`. Per-neuron converted SWC and FNT files go to `VisPa\cached_data\fnt`. `X:` on this machine is that microscopy_data share.

## 0.1.0.dev36 - 2026-11-10 (local/unreleased candidate)

- The server FNT bin check now gives up after 8 seconds and uses the local FNT 0.99.155 bin. A silent share no longer blocks the morph-clustering run.

## 0.1.0.dev35 - 2026-11-10 (local/unreleased candidate)

- Moved the FNT producer and clustering checks into `morph_clustering`. Executable lookup uses the shared server `fnt-tracer-0.99.155` bin first and `Downloads/fnt-0.99.155/bin` when that server bin is incomplete.

## 0.1.0.dev34 - 2026-11-10 (local/unreleased candidate)

- Moved `ensure_cached_swc` to `region_analysis/neuron_loader.py`. Cache hit, missing-file IONData fetch, and refresh stay the same. `remap.ensure_cached_swc` still resolves.

## 0.1.0.dev33 - 2026-11-10 (local/unreleased candidate)

- Moved side and ipsi/contra assignment into `region_analysis/neuron_table.py`. `process` applies it before `save_all`, so the workbook is written with `Soma_Side`, laterality counts, and the split projection lengths.

## 0.1.0.dev32 - 2026-11-10 (local/unreleased candidate)

- Merged `HierarchyTable` and `DualHierarchyTable` into `region_analysis/hierarchy.py`. The ARM key reader and the CHARM/SARM parent tables now live in that one module.

## 0.1.0.dev31 - 2026-11-10 (local/unreleased candidate)

- Named the sample workbook module `region_analysis/neuron_table.py`. The package stays `remap.region_analysis`.

## 0.1.0.dev30 - 2026-11-10 (local/unreleased candidate)

- Named the sample workbook module `region_analysis/region_table.py`. The package stays `remap.region_analysis`.

## 0.1.0.dev29 - 2026-11-10 (local/unreleased candidate)

- Named the sample workbook module `region_analysis/projection_analysis.py`. The package stays `remap.region_analysis`. Public names such as `parse_swc` and `PopulationRegionAnalysis` still load from that package. Summary figures are in `overview_plots.py`. The single-neuron loader is `neuron_swc.py`.

## 0.1.0.dev28 - 2026-11-10 (local/unreleased candidate)

- Moved `NeuronTracer` back to `region_analysis/neuron_tracer.py`. It is the single-neuron unit: load one SWC from text or the cache, fetch from IONData when the file is missing or refresh is set, and draw `plot_neuron`. `neuron_analysis.py` calls that unit once per neuron while building the workbook.

## 0.1.0.dev27 - 2026-11-10 (local/unreleased candidate)

- Folded the small region workers into `region_analysis/neuron_analysis.py`: label helpers, output folders, terminal/projection table helpers, `NeuronClassifier`, `AtlasHemisphereReference`, and `NeuronTracer`. Hierarchy, laterality, and summary plots stay in their own modules. Public lazy imports still resolve the same names.
- `ensure_cached_swc` reads the configured cache first. A missing SWC is fetched from `iondata_host` when download is allowed. `refresh=True`, config `refresh_swc`, or `remap population --refresh` fetches again and replaces a different cached file.

## 0.1.0.dev26 - 2026-11-09 (local/unreleased candidate)

- Added sibling `remap.neurom_analysis` for NeuroM/MorphIO dendritic features (Liu→fMOST bridge conventions). It sits beside `fnt_pipeline` and `region_analysis`; it is not part of the population workbook path. `neurom>=4.0.0` is a core package dependency.
- Per-monkey-run QC plots (including SWC shape PNGs) stay off by default. Enable with `generate_plots: true` on that run config or `remap population --generate-plots`. When enabled, `save_all` writes summary figures and `swc_shape_<id>.png` via `NeuronTracer.plot_neuron`.

## 0.1.0.dev25 - 2026-11-09 (local/unreleased candidate)

- Collapsed the `population_analysis` package into one module, `region_analysis/neuron_analysis.py`, holding `parse_swc`, `RegionAnalysisPerNeuron`, and `PopulationRegionAnalysis`. Public lazy imports still resolve the same objects.

## 0.1.0.dev24 - 2026-11-09 (local/unreleased candidate)

- Removed unused region-analysis helpers (hierarchy CSV loader, diagnostic printers, plot wrappers, snapshot export, and unused laterality/hierarchy/label aliases). `remap.region_analysis` now loads public names on access. `parse_swc` comes from `population_analysis.swc_validation` without importing the population workbook. `process` and `save_all` formulas are unchanged. `NeuronTracer.plot_neuron` remains.

## 0.1.0.dev23 - 2026-11-09 (local/unreleased candidate)

- Kept the legacy 3D SWC shape plot on `NeuronTracer.plot_neuron` (branch-order scatter, terminals, soma), with optional `save_path` / `show` and `source` or `nii` coordinates.

## 0.1.0.dev22 - 2026-11-09 (local/unreleased candidate)

- Matplotlib 3.11: `boxplot(..., labels=)` → `tick_labels=` in plotting and population projection-by-soma helpers so `projection_sites_count` and `laterality_summary` save again.

## 0.1.0.dev21 - 2026-11-09 (local/unreleased candidate)

- Grouped the population region operator with its SWC parser and per-neuron measurement under `remap.region_analysis.population_analysis`. `parse_swc`, `RegionAnalysisPerNeuron`, and `PopulationRegionAnalysis` are the same objects on `remap` and `remap.region_analysis`. Hemisphere, classifier, labels, hierarchy, plotting, output, and laterality stay separate. Reporting helpers stay in `region_analysis.utils` because plotting and laterality use them, and `population_analysis` re-exports those helpers.

## 0.1.0.dev20 - 2026-11-09 (local/unreleased candidate)

- Renamed population/config host key `http_host` to `iondata_host`.
- Pointed packaged atlas/template/hierarchy resources at the shared fMOST microscopy atlas share. Removed hard-coded `D:\projectome_analysis\...` fallbacks from hierarchy detection so ReMAP does not use that repository as a data or code dependency.

## 0.1.0.dev19 - 2026-11-09 (local/unreleased candidate)

- Removed the portal planner, `plan_processed_swc`, `load_processed_swc`, and the unused `neuro_tracer` alias. Neuron loading is `neuron_loader.ensure_cached_swc`: the configured cache is used when the file is already there, and IONData is used only to fill that cache.

## 0.1.0.dev18 - 2026-11-09 (local/unreleased candidate)

- Replaced `local_tracer.LocalNeuroTracer` with `neuron_tracer.NeuronTracer`. It parses a supplied SWC, a file already in the configured cache, or a file fetched into that cache. Hemisphere, label, and classifier modules stay separate.

## 0.1.0.dev17 - 2026-11-09 (local/unreleased candidate)

- Stored the shared profile in the package at `src/remap/configs/remap_config.yaml`. It has the VisPa split: `resources`, `cache.swc`, and `output`. `remap.load_config()` reads that file unless `REMAP_CONFIG` or `--config` selects another. `remap population` uses it by default; the SWC directory is `cache.swc/<sample-id>`.

## 0.1.0.dev16 - 2026-11-09 (local/unreleased candidate)

- Public region-analysis names load from the package root on first use, in the VisPa style: `remap.parse_swc`, `remap.LocalNeuroTracer`, `remap.RegionAnalysisPerNeuron`. Removed the extra `remap.swc_validation` and `remap.neuron_analysis` modules so each function has one import path. The implementations remain in `remap.region_analysis`.

## 0.1.0.dev15 - 2026-11-09 (local/unreleased candidate)

- Moved the basic region-analysis functions into the package: `parse_swc` and `RegionAnalysisPerNeuron`. `LocalNeuroTracer` already lived there. `remap.swc_validation` and `remap.neuron_analysis` re-export the same objects. Measurement behavior is unchanged.

## 0.1.0.dev14 - 2026-11-09 (local/unreleased candidate)

- Added `remap.processed_source` as ReMAP's own processed-SWC processor. Population `processed_source: "portal"` now takes an explicit `http_host` and caches one exact `getSWC` response under `workspace_root/work/`. Dry-run plans the local path or URL without network access. A missing file is validated before an exclusive cache write, and a different cached byte string is refused. The tracer no longer imports VisPa. Historical `/250` indexing and the dev12 coordinate candidate are unchanged. Focused synthetic tests cover the plan, explicit source, and cache guards. A live portal fetch and a full population workbook remain unverified.

## 0.1.0.dev13 - 2026-11-03 (local/unreleased candidate)

- Restored exact processed-SWC source fallback for the legacy region tracer through a caller-supplied source. The population operator retains local-only default and adds explicit `vispa-portal` mode, a read-only exact-ID fetch plan, managed cache boundary under ReMAP work, and source hashes in the run receipt. The provider is imported lazily from VisPa; no ReMAP HTTP/cache implementation was added. A two-node tracer case passed in the projectome environment. Full population and live portal execution remain unverified; historical `/250` mapping and dev12 coordinate candidate remain unchanged.

## 0.1.0.dev12 - 2026-11-03 (local/unreleased candidate)

- Refined the existing README chart into a single code-grounded call/data overview: file containers, callable stadiums, data parallelograms and separate candidate styling. Corrected misleading implied parser-to-analysis calls. Documentation-only; no runtime changes.

- Added bidirectional CoordinateRoute and explicit forward/reverse SavedBridge chains for raw SWC, native DS00, prepared pitch and NMT grids; optional 5 um calibration and processed-SWC stored-coordinate binding use the same interface and fail when missing. Reuses VisPa acquisition geometry through supplied calibration, with parity checks; no mandatory VisPa dependency. In-memory SWC mapping preserves graph fields and source radii (no deformed morphometry claim).
- Six unittest cases pass, including VisPa helper parity, inverse axis mappings, unit/frame guards, optional routes and four hash-verified native roots. One real 945/048 saved ANTs route round trip returned within 0.176014 um and forward NMT RAS exactly reproduced the saved control at recorded precision. Raw-axis calibration remains provisional; real 5 um/processed-SWC bindings and live consumer wiring remain pending. No registration fit or image resampling.

## 0.1.0.dev11 - 2026-11-03 (local/unreleased candidate)

- Added a portable, explicit point-coordinate API for provisional raw A/B hypotheses, the verified special-747 converter permutation, historical `/250` with unknown source unit, bidirectional native voxel/RAS affine, RAS/LPS and µm/mm conversion, and caller-supplied saved point chains. It requires per-sample shape/spacing and declared frames; no Step1 adapter or scientific acceptance is implied. Four unittest cases pass, including four hash-verified 945 raw-root native IJK/RAS parity checks. Saved pitch/NMT chain execution has not been integrated or retested through this API.

## 0.1.0.dev11 - 2026-11-09 (brought in from origin/main)

- Designated the fMOST share `resources\dependencies\atlas` tree as ReMAP's default atlas, using the exact `sources.atlas` paths from VisPa `config_deb.yaml` at `aed0077e` (config 1.0.12). The packaged profile is YAML at `src/remap/configs/config_deb.yaml`, with `coordinate_scale: 250`. `remap population` fills omitted `atlas`, `atlas_key`, and `hemisphere_mask` from that profile. `remap one` defaults `--atlas` and `--atlas-key` to that same volume and key. Explicit paths win. Template and hierarchy CSVs stay caller-supplied. Atlas binaries are not packaged. The dormant hierarchy-key search checks the share key and no longer consults `D:\projectome_analysis`.
- Population and table registration paths still use `os.path.relpath` when the output and the registry anchor share a drive. A Windows cross-drive pair no longer raises after the workbook or table exists; the receipt keeps that output path. A failed FNT run that never wrote `receipt.json` removes only the output directory it created, so a retry is not blocked. Finished outputs are still refused. Coordinate scale, declared space, hierarchy parsing, type bands, and the atlas loaders are unchanged.

## 0.1.0.dev10 - 2026-11-03 (local/unreleased candidate)

- Adopted the read-only shared DS00 selection reader and CLI from the local dev7 candidate into the dev9 published-main baseline. The reader verifies selected normalization bundle bytes and fails closed on processed-SWC frame binding; region analysis inputs and newer FNT behavior remain unchanged. Focused tests and CLI checks are recorded in the project journal; anatomical and scientific acceptance remain pending.

## 0.1.0.dev9 - 2026-10-30 (local/unreleased candidate)

- Documentation: clarified legacy all-compartment leaf, regional-length and type-proxy limits, their units and scientific review gate; no numerical behavior or package version changed. Verified against the current region-analysis implementation.

- Hardened offline saved-score analysis with a strict settings schema, receipt case projection and exact UID/hash binding; offline analysis no longer requires original SWCs or FNT executables. Boolean controls require real JSON booleans.
- Added explicitly optional undecimated geometry control, retaining the default legacy nodewise fold and 5000/5000 decimation. Existing decimated output compatibility is preserved; this control is not an anatomical acceptance.
- Weighted-distance validation records minima and allows only numerical negatives down to -1e-8; reports requested and realized cluster counts. Technical validation results are recorded in the release validation receipt; scientific review and final K remain pending.

## 0.1.0.dev6 - 2026-10-29 (local/unreleased candidate)

- Added bounded portable FNT production and saved-score analysis with explicit case identities, local binary/source hashes, strict pair coverage, no-clobber outputs, dry runs, and optional exploratory clustering. Defaults preserve the established local fold and 5000 distance/area decimation; no region-analysis formula changed.
- Hardened configuration and full SWC validation before writes, enforced the 32-case API bound, and synchronized CLI/help/receipt/package version. Included six portable focused tests; all six passed in the isolated release checkout. Existing full workbook parity was rechecked on 18 selected neuron instances across eight samples and a changed-type pilot, with all 14 sheets exact under zero numeric tolerance. Full-cohort and anatomical acceptance remain pending.

## 0.1.0.dev4 - 2026-10-25 (local/unreleased at source checkout; published core snapshot)

- Consolidated the package version in src/remap/_version.py and exposed it through CLI and package metadata. Moved console handling to cli.py while retaining python -m remap. Core algorithms were unchanged. Local source and installed-wheel version/dry-run checks were previously recorded in the source project's extraction manifest; this publication does not rerun tests.

## 0.1.0.dev3 - 2026-10-25 (historical source development)

- Added the portable full-population workbook producer with Summary, Soma_Hierarchy, Laterality, terminal/outlier, and L6/L3 projection worksheets. Added explicit-config dry run and bounded neuron selection. The manager registration receipt supplies analysis-source declarations without writing legacy progress files. Ten one-neuron technical parity pilots against original Step1 workbooks were recorded locally; full-cohort and scientific acceptance were not established.

## 0.1.0.dev2 - 2026-10-25 (historical; superseded)

- Tried a read-only progress-snapshot inspector and gate. Dev3 removed this gate so ReMAP analysis does not depend on a legacy PA progress snapshot.

## 0.1.0.dev1 - 2026-10-25 (historical source development)

- Extracted single-neuron SWC, region metric, and FNT distance operators with explicit coordinate mapping, exact identity, hashes, dry run, and no-overwrite output.


## Review-profile executor 0.1.0 — 2026-11-18 (local/unreleased)
- Added explicit legacy-profile clustering executor reusing existing Spearman/Ward.D2 functions; FNT production unchanged. Validated: all42 saved partitions exactly reproduced for both212 and260 cohorts. Plot-profile wiring remains pending.
