# VisPa — Visual Projectome Analysis tool

VisPa reviews macaque neuron and microscopy data configured by the DEB lab.
This checkout identifies as **1.11.0.dev14**, without a release tag. VisPa is a Python package
inside a Conda environment; `vispa` is a pip-generated Python launcher, not a
separately packaged application binary.

The default `config_deb.yaml` starts at **251637 / 004.swc** and uses the shared
server data and dependencies:

```text
\\10.102.8.200\microscopy_data\fMOST\resources\
├── config_deb.yaml
├── key_datasets\{CH00DS_datasets,5micron_datasets}
└── dependencies\
    ├── brain_view\
    └── fnt\
```

## Install on Windows

Install [Miniforge](https://github.com/conda-forge/miniforge). Open **Miniforge Prompt** in this checkout and run:

```powershell
conda env create -f environment.yml
conda activate vispa
python -m pip install --no-build-isolation -e ".[3d,tiff]"
python -m vispa
```

If `vispa` already exists, use the update commands below. Recloning the repository does not recreate the Conda environment.

For a downloaded ZIP, extract it locally and run the same commands in its folder. [Conda recommends activating the environment before pip installation](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html#using-pip-in-an-environment). The environment file selects conda-forge OpenBLAS; this avoids a reproduced Windows Matplotlib crash with the MKL-backed solve. Verify with `python -m pip check` and `python -m vispa --version`.

`python -m vispa check` verifies configured files and server/cache access. A disconnected lab share can make this check fail after a successful installation. TIFF support is included through the declared package extras.

`install.cmd` is an optional convenience wrapper. From Miniforge Prompt it uses Conda's base Python; otherwise it tries `%USERPROFILE%\miniconda3\python.exe`. Pass `-CondaBasePython PATH` if needed. It performs the same environment setup, pip install, and checks. `VisPa.cmd` forwards arguments to `python -m vispa` after `conda activate vispa`.

## Update an existing installation

In Miniforge Prompt, from the checkout:

```powershell
conda env update -n vispa -f environment.yml
conda activate vispa
python -m pip install --no-build-isolation -e ".[3d,tiff]"
python -m pip check
python -m vispa --version
```

To adopt new lab defaults, use **Settings → Default YAML → Reset to default → Save settings**, or launch with the shared profile directly:

```powershell
python -m vispa gui --config '\\10.102.8.200\microscopy_data\fMOST\resources\config_deb.yaml'
```

`python -m vispa check` must report **All configured resources ready** before rendering. Each line includes its resolved file, folder, or server location.

## Create or select a configuration

Create the per-user profile without overwriting an existing file:

```powershell
python -m vispa config-init --dry-run
python -m vispa config-init
```

Pass `--config PATH` to any command to select another profile. Relative paths
resolve from that YAML/JSON file. Binary assets, microscopy data and credentials
remain external.

### IDE setup

Find the exact interpreter:

```powershell
python -c "import sys; print(sys.executable)"
```

Select that interpreter in the IDE and use the cloned checkout as the working
directory.

## Commands explained

| Task | Simple command | What it does |
|---|---|---|
| Open the GUI | `python -m vispa` | Opens the normal review interface. |
| Check readiness | `python -m vispa check` | Prints a path-aware checklist for the configured sample and neuron. |
| Show version | `python -m vispa --version` | Prints the installed VisPa version. |
| Validate a config | `python -m vispa config-check --validate-only --config PATH` | Checks YAML/JSON structure without reading lab data. |
| Audit one resource set | `python -m vispa config-check --sample SAMPLE --neuron 004.swc` | Reports exact paths, hashes, geometry and cache references. |
| Open 3D view | `python -m vispa brain-view --sample 251637 --neuron 004.swc` | Opens the configured mesh and processed SWC. |
| Render a montage | `python -m vispa montage --input FILE --output FILE --units mm` | Creates a five-view DS00 montage. |
| Fetch FNT | `python -m vispa fnt-fetch --sample 251637 --neuron 004.swc` | Retrieves one exact FNT into the user cache. |
| Create user config | `python -m vispa config-init` | Creates the per-user profile without overwriting an existing file. |
| Run tests | `python -m unittest discover -s tests -v` | Runs all automated tests. |

The generated `vispa` command remains available in the installer environment;
`python -m vispa` is the stable Windows fallback when that generated launcher is
unavailable.

The [Windows Conda workflow](.github/workflows/windows-python-conda.yml) creates
the declared environment, installs the editable package, checks command entry
points and dry runs, and runs the source suite.

## GUI walkthrough

```powershell
python -m vispa
```

1. Wait for **VisPa data check**. A ready profile shows a check mark and the
   resolved location for every required resource.
2. Confirm the Sample ID and Neuron ID, or open **Neuron list** and select one.
3. A valid Sample ID and Neuron ID trigger the Soma lookup automatically. The
   status bar reports **Neuron: found**, **not found**, or a lookup error and
   shows the portal region when known.
4. Click **Render** after the coordinates appear, and wait for the progress bar
   to finish.
5. Review **Soma**, **Context**, **Sagittal**, **TrioPlot** and **3D SWC**. The
   **3D SWC** tab renders the current processed neuron on the template mesh.
6. Use **3D brain view** for the interactive viewer; use **fnt-tracer** for the
   matching annotation project.
7. Use **Check data** at any time to repeat the readiness checklist.

Clear **Save outputs** for preview only. Otherwise, the folder under **Saving**
receives the rendered panels.

The optional morphology-only example is CLI-only and separate from lab data:

```powershell
vispa example --dry-run
```

## Advanced operational details

Primary standalone development workspace: `D:/VisPa`. Package/distribution:
`vispa`. Activate the Conda environment and run `vispa`; the equivalent
IDE/troubleshooting forms remain `python -m vispa` and `python -m vispa.gui`.

`VISPA_CONFIG` and `VISPA_WHEELHOUSE` are the VisPa environment handles. Pass
`--config PATH` for a specific run; otherwise `VISPA_CONFIG` wins, then the own
per-user config at `%APPDATA%\VisPa\vispa_config.yaml`. Caches and outputs default
to `%LOCALAPPDATA%\VisPa`. Existing `visual_toolkit` settings blocks and
`visual-toolkit.*.v1` receipt schemas remain readable protocol data, but they do
not provide compatibility Python modules or commands.

The Python API is imported only as `vispa`. The legacy `Visual_toolkit`
forwarding package and class alias have been removed. Optional OpenGL remains
lazy. Use `vispa` for the CLI and `vispa gui` for the GUI.

New standalone run receipts, builds and candidate outputs live under `D:/VisPa/work/`. The [shared validation receipt](work/fnt_onboarding_20261022/run_receipt.json) records versioned milestones separately; [the Windows Conda workflow](.github/workflows/windows-python-conda.yml) validates the Python-only environment. The living project journal remains `D:/projectome_analysis/docs/project_note.md`. Existing projectome receipts remain historical evidence; external scientific data/cache paths remain explicit configuration.

### Repository status and compatibility

VisPa includes a live per-sample IONData neuron list for the configured lab intranet and review panels for configured local microscopy resources. The live list is fetched from the neuron API; image cubes, raw SWCs, and microscopy files use separate configured hosts or shares. The package contains only server addresses and candidate sample-resource links, not source data, credentials, or local project tools. These links and checksums do not establish current share availability or scientific acceptance.

This checkout is **1.11.0.dev14, without a release tag**. It preserves the
existing rendering and source-verification algorithms while removing the
retired `Visual_toolkit` compatibility namespace. The DS00 sagittal panel now
shows one provisional soma-location marker without A/B raw-SWC traces; its
manifest, hash, geometry, and source checks remain. Marker placement still
requires independent anatomical validation. No study data, credentials, or
private source files are included; the package profile declares server
endpoints and ten known sample mappings without copying images or SWCs.
`extraction_manifest.json` records the historical extraction snapshot and is
excluded from source distributions. The historical dev6 receipt does not
verify this dev11 candidate.


The supported Windows route is Conda plus `python -m`. Keep the VisPa environment
separate from the projectome analysis interpreter. Run the source test command
`python -m unittest discover -s tests -v` inside that environment. Older
pip/venv/executable artifacts are historical and are not required.

The headless operator is `vispa render`. It accepts one local `.npy` array in ZYX or YX order, a declared soma coordinate, origin, voxel spacing, role, and output directory. The three coordinate triples use XYZ micrometres. TIFF, NIfTI, SSH, and YAML extras remain available to backend and GUI workflows. The first run should use `--dry-run`, which resolves the inputs, settings, output PNG and receipt without creating directories, reading image pixels, or accessing a source. A real run writes the PNG and its JSON receipt and refuses to overwrite either.

```text
vispa render --input cube.npy --sample sample-01 --neuron 0007 --soma 120 240 30 --origin 0 0 0 --resolution 0.65 0.65 3 --coordinate-frame sample-native-XYZ --role soma --output-dir review --dry-run
```

Use `--role context` for the 5 µm style. `--set PATH=VALUE` overrides review settings; scalar values and numeric sequences are supported, such as `--set figure.panel_dpi=400` or `--set soma_window.cubes_xy_steps=1.5,1.25,1`. Unknown keys, out-of-range values and invalid combinations fail before changing global settings. Run `vispa settings` to print each setting's default, current value, valid range and effect as JSON. Python callers can use `review_settings_schema()` and pass a mapping or a list of `PATH=VALUE` strings to `apply_setting_overrides()`. The single-panel review figure includes the image and target marker legend and labels the displayed plane as native X/Y. The cyan target box and cross mark the supplied coordinate; they do not validate anatomy, orientation, or laterality. The labeled single-panel CLI review reserves font-measured clearance between its axes and shared legend; multi-panel and unlabeled figures retain the legacy layout.

`vispa gui` starts the optional Tk interface. `vispa --help` and `vispa --version` do not load image libraries, open windows, or acquire data. Package import does not change `sys.path` or import `IONData`.

The compatibility command `vispa example` fetches one public SWC for a morphology-only preview. It does not exercise the lab image, atlas, FNT, or brain-view paths. The cached source is checksum-pinned; its coordinate frame and units are unspecified. Preview its source URL and proposed output locations without network or file access first:

```powershell
vispa example --dry-run
```

The one-record operation accepts `--cache-dir`, `--output-dir`, and `--dpi` (100–240; default 160). It reuses an existing figure only when its receipt, source checksum, VisPa version, renderer-code checksum, DPI, full-extent declaration, and PNG hash match; changed renderer code, version, or DPI uses a named variant, and conflicting files are preserved. No sample configuration is required.

## One-volume DS00 montage

`vispa montage` renders one explicitly named 3D NIfTI into the preserved five DS00 views. It does not discover cohorts, read workbooks, choose files, or apply a transform. The affine must yield LPS voxel axis codes, as in the source montage. NIfTI affines map voxel indices into RAS+ world coordinates; each panel labels increasing projected anatomical directions in RAS+ millimetres. The header must declare millimetres, or the operator must explicitly declare `--units mm` when the header units are unknown; known non-mm units are rejected. The output includes a compact intensity-image legend. The `[3d]` extra provides the montage dependencies.

```powershell
vispa montage --input 'D:\data\sample.nii.gz' --output 'D:\review\sample-5view.png' --units mm --max-voxels 64000000 --set display_gamma=0.88 --dry-run
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

`environment.yml` installs the optional 3D dependencies in the Conda runtime. The legacy OpenGL viewer requires a local OBJ mesh, an explicit sample ID and processed
SWC filename, and explicit coordinate-frame and coordinate-unit declarations in
`sources.brain_view`; it does not resolve cohort identities, use raw SWCs, fetch remote
data, or apply registration/mirroring. Preview the resolved paths and display settings
before launching a window:

```powershell
vispa brain-view --sample 251637 --neuron 004.swc --config 'C:\data\vispa_config.yaml' --dry-run
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

## Explicit brain-view batches (local dev13 candidate)

Use [the batch guide](batch/README.md) and the placeholder [example jobs](batch/local_pilot.example.json) for selected mesh/neuron pairs. Keep machine-specific filled jobs outside version control. One job renders one existing OBJ mesh with one named processed SWC through the same VisPa OpenGL worker. This does not combine multiple neurons in one scene. A supplied region mesh must already be in the declared processed-SWC frame and units; VisPa applies no registration, scaling or mirror transform.

```mermaid
flowchart LR
  A[Jobs JSON: region OBJ + exact neuron IDs] --> B[Dry-run: hashes, frame, camera, output paths]
  C[VisPa dataset configuration] --> B
  B -->|--limit 1| D[Existing isolated brain-view worker]
  D --> E[One PNG and adjacent receipt per pair]
  E --> F[Shared batch receipt]
  F -. future handoff, no transfer yet .-> G[Multimodal_INS analysis_scripts]
```

```powershell
cd D:\VisPa_publish_20261023
python -m batch.render_brain_views --jobs work/jobs/filled-local-jobs.json --output-root work/results/brain-view-batch-new-run --limit 1 --dry-run
python -m batch.render_brain_views --jobs work/jobs/filled-local-jobs.json --output-root work/results/brain-view-batch-new-run --limit 1
```

`--limit N` selects N sorted jobs. Full execution requires both `allow_all: true` in jobs JSON and `--all`; outputs require a fresh root. Job groups expose `sample_id`, `region_id`, existing `mesh_path` (OBJ), `mesh_label` (1–18 printable characters), exact `neuron_ids`, matching `coordinate_frame` and `coordinate_units`, optional `portal_region`, and `camera_overrides` using the brain-view setting names and valid ranges above. The single-view CLI also accepts `--mesh-path` and `--mesh-label`; when absent, the configured whole-brain mesh and its legend remain the defaults. The prior local pilot used a pre-existing whole-brain OBJ and processed SWC; its privately stored PNG verifies technical rendering and legend readability only. Region OBJ overlay/framing and anatomical acceptance remain unverified. The canonical VisPa or ReMAP environments were not changed by the disposable shared Python 3.10 validation.

## Shared settings interface

`vispa settings` retains the review-only JSON schema by default. Use
`vispa settings --scope review|brain-view|montage|all` to discover the
three existing parameter groups; `all` is grouped JSON and loads no optional
feature dependencies. The root Python API is `vispa.settings_schema(scope="all")`,
`resolve_settings(scope, overrides=None, base=None, config=None)`, and
`apply_settings(scope, overrides, settings=None, config=None)`. The same APIs
are available from `vispa` directly. Values can be mappings or repeated
`KEY=VALUE` strings; JSON values such as arrays/numbers are decoded,
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
vispa brain-view --sample 251637 --neuron 004.swc --config 'D:\config.json' --dry-run --set camera_distance_scale=0.5 --camera-distance-scale 0.6
```

The resolved camera scale is `0.6`. Run `vispa settings --scope brain-view`
for defaults, units, display effects, valid ranges and the `eye_direction`/`up`
vector relationship; add `--config PATH` to include configured current values.

## Sources and configuration

The packaged `config_deb.yaml` profile starts on `251637/004.swc` and configures live IONData catalog access,
separate BAP image-cube and raw-SWC hosts, the shared DEB microscopy dataset
roots, brain-view dependencies, FNT executable/projects, and per-user VisPa
caches/outputs. Its sample-to-AnimalID and dataset links are candidate resource
references and may be unavailable off the lab network. No credentials or local
worker path is set. A new profile can be created with `vispa config-init`;
caches and outputs use `%LOCALAPPDATA%\VisPa`. Pass `--config PATH` to select
another profile. JSON works with the standard library; YAML is included in the
core install. Relative paths resolve from the config file's folder, or from the
optional top-level `base_dir`.

Create the per-user YAML without overwriting anything already present:

```powershell
vispa config-init --dry-run
vispa config-init
vispa config-init --output 'D:\review\vispa_config.yaml'
vispa config-init --from-config 'D:\old\visual_toolkit_config.json' --output 'D:\review\vispa_config.yaml'
```

`--output` must end in `.yaml` or `.yml`; an explicit destination is never
overwritten. Without `--output`, the VisPa per-user YAML is the target and uses
packaged defaults. Import an older config only with `--from-config`; its source
bytes remain unchanged.
Passing `--output` selects the packaged same-intranet template; it never overwrites an existing destination. A fresh install or normal GUI launch creates the per-user VisPa config when absent. Legacy VisualToolkit YAML/JSON and environment variables remain untouched and require explicit `--config` or `config-init --from-config` selection. Existing CSV-only catalogs remain CSV by default; the Neuron list source selector can explicitly query Live IONData when a catalog is configured. Choosing a source never triggers automatic fallback. The created file contains validated values for review, brain-view and montage scopes as well as the lab source profile. A relative per-sample `swc_cache` resolves from the config folder unless `swc_cache_root` or `swc_root` is declared. The GUI parses its arguments first (abbreviations are rejected) and initializes only a valid implicit launch; `--config`, `--dry-run` and a configured VisPa environment path never create a file.

All lab server addresses and source roots live in the editable profile. In the packaged profile, each sample's `ds00_relative` is resolved under `defaults.ds00_root`, and `sources.dataset_manifest_relative` follows the same root. The `resample_5um` entries follow `defaults.resample_5um_root`. Changing these roots redirects the declared paths without editing ten per-sample UNC strings; existing profiles that use `ds00_processed` keep their original path meaning. Relative child paths must stay within their declared root. The sample filenames and SHA-256 declarations remain candidate provenance; changing a root does not verify that files or geometry match. The optional `vispa example` CLI owns its checksum-pinned public source defaults and does not add example fields to the GUI profile.

For SSH sections, set `ssh_sample_id` alongside `ssh_remote_base`; that remote root is only eligible for the matching sample. `low_res_ssh_base=` is an explicit per-instance override. The GUI identity is selected from `visual_toolkit.default_sample` and `visual_toolkit.default_neuron`; the packaged profile starts on sample `251637` and `004.swc`, which has registered DS00 and 5 µm sources. A valid Sample/Neuron identity, including the configured startup identity, triggers automatic soma lookup unless `--no-autoload` is passed. The highlighted Sample-section status panel reports whether the neuron was found and its portal region. In the GUI, **Neuron list** uses the selected source and shows every API row for the exact sample ID, preserving zero-padded filenames and suffixes; selecting a row fills the Neuron ID and starts the same automatic lookup. The source selector offers Live IONData explicitly alongside a configured dated CSV; on older CSV-only profiles, CSV remains selected unless you choose Live IONData. The compact note lists the eight INS-cohort AnimalIDs from the megatable and separately identifies sample 250432 / AnimalID 747; it does not classify individual neuron rows. **Render** (F5) produces the complete panel set (Soma, Context, Sagittal and TrioPlot); there is no per-panel selection. **Save outputs** beside Render chooses whether the run writes files (unticked = preview only), and **Save Soma NIfTI (.nii.gz)** in Saving controls the soma volume. The **3D brain view** action carries the current sample, neuron ID, and any loaded portal region to the isolated original OpenGL worker, using the configured processed SWC only. **fnt-tracer** uses an explicitly configured matching project first, then an exact VisPa native FNT cache project; its executable is needed only to launch the external tracer. There is no bulk action.

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

The GUI's **Neuron list** uses `sources.neuron_catalog.mode: live-iondata` in the packaged profile and queries `http://10.10.48.110/neuronbrowser/api/user/selectNeurons?id=<sample-id>` with a bounded timeout and response size. It validates the JSON rows and keeps exact `sampleid` and `name` values, including leading zeroes and sample suffixes. The display has two columns, **SWC ID** and **Portal region**; provenance shows whether the list came from live IONData or a dated CSV, its row count, fetch time or source date, URL or file path, and SHA-256. To add a dated snapshot alongside live mode, set `sources.neuron_catalog.snapshot_path`; in a CSV-mode profile, `sources.neuron_catalog.path` selects the CSV. If both sources are available, choose explicitly in the GUI. On existing CSV-only profiles, Live IONData is an explicit option and uses the configured host or the intranet default; the current CSV remains the default. No source is silently substituted. For a bounded backend check, run `vispa config-check --catalog --sample 250432 --catalog-source live-iondata --dry-run` to inspect the resolved endpoint without fetching, or omit `--dry-run` to fetch just that sample's catalog and report its count and provenance. `vispa.sources.list_neurons(sample_id, config=None, source=None)` supports `live-iondata` and `csv` with the same explicit-source behavior.

The optional **3D brain view** action uses `sources.brain_view.mesh_path` and `processed_swc_root`, with declared `coordinate_frame` / `coordinate_units` and optional `settings`; `visual_toolkit.worker_python` selects its isolated worker when set. A generic config does not receive default anatomical frame or unit declarations: the worker preflight requires explicit values when 3D view is requested. The default projectome config points to the preserved root.obj and processed-SWC tree and declares their current stored convention. The handoff passes the exact current sample and neuron ID plus the portal snapshot's region when available. It never substitutes a raw SWC or downloads a model. The GUI starts the worker in a separate process, leaving the host Python imports isolated.

`vispa.sources.IONData()` reads the configured local SWC cache first. A project can register a fallback implementing `getRawNeuronTreeByID(sample_id, neuron_id)` using `set_iondata_provider_factory(factory)`. Without a registered factory, setting `sources.http_host` and `sources.raw_swc_base` enables the built-in portal fetch: it reads the sample's `project_id` from the portal and downloads `<project>/<sample>/swc_raw/<neuron>` into `sources.legacy_raw_swc_root`. The returned tree protocol exposes `root.x/y/z`, `root.xyz`, `points`, and iterable `edges` whose `.data` contains points with `.x/y/z` attributes. The local parser rejects malformed, disconnected, cyclic, and missing-parent trees.

The processed-DS sagittal implementation requires a resolved dataset manifest, `defaults.ds00_root`, a configured per-sample image path and checksum, and local SWC input or cache. It records source identity and geometry. The current panel shows only the provisional soma-location marker, without A/B trace overlays; marker placement remains unvalidated, and successful loading or rendering is not anatomical acceptance.

## API and projectome integration

The primary Python import is `vispa`. `vispa.VisPa`, `REVIEW_SETTINGS`, and the plotting helpers are exposed lazily from `vispa.toolkit`. Core rendering accepts in-memory arrays, so a consumer can integrate the package without adopting the standalone acquisition providers or source layout.

Projectome owns its cohort runners, montage adapter, source manifest, and
lab-specific configuration. It uses one explicit `projectome_vispa` adapter to
select that configuration and inject its lazy legacy `IONData` fallback. The
independent package contains only the generic single-volume DS00 renderer, not
the cohort montage adapter or its workbook/path/selection logic. It carries
candidate sample mappings and paths in its editable default profile, with no
cohort runner, workbook, image data, or source SWCs; `extraction_manifest.json`
preserves historical source path and hash provenance.

## Package checks

The package tests cover clean import without projectome or `IONData`, config-relative resolution, SWC validation and provider fallback, local coordinate geometry, a tiny-array render with its marker and receipt, DS00 frame parity, montage dry-run no-write behavior, and PNG/receipt output. No license is assigned by this staged extraction.

See [CHANGELOG.md](CHANGELOG.md) for the preserved toolkit history and extraction changes.


### Single-neuron resource and FNT preflight

Run `vispa config-check --config settings.yaml --sample 251637 --neuron 004.swc --dry-run` for a read-only JSON inventory (file hashes, source dates unknown as null, coordinate declarations, cache references and cube route/geometry). Add `--fnt` to require both a configured executable and an exact matching manual or native cached FNT project; this mode returns failure when either is unavailable and never starts the binary. The JSON also reports `project_ready` and `executable_ready` separately. Directory references are not recursively hashed; the inventory alone does not establish complete offline panel coverage or scientific acceptance.

The active VisPa profile can fetch one exact native FNT with `vispa fnt-fetch --config PATH --sample 251637 --neuron 004.swc --dry-run`; remove `--dry-run` to download and verify it into the VisPa cache. `visual_toolkit.fnt_tracer` exposes `auto_download` (boolean, default true), `cache_root` (optional path), `server_base_url` and `catalog_base_url` (plain HTTP(S) base URLs), `timeout_seconds` (positive integer, default 30), and `max_response_bytes` (positive integer, default 67108864). An explicit `project_root` keeps a matching annotated local project as first choice; otherwise the exact verified VisPa cache project is used. `config-check --fnt` stays read-only and reports project and executable readiness separately. The executable is required only to launch **fnt-tracer**. In the GUI, **Settings** opens the active config with five sections in **Organized editor**, complete editable **Raw YAML** (or **Raw JSON** for an explicit JSON config), and a read-only **Default YAML** reference. Choose Data folders, Sources, Brain view, FNT or Startup; use **Browse…** for paths. The public-neuron example is intentionally absent from the GUI. Raw mode includes sample-specific paths, geometry, provenance and display settings. Switching between the editing tabs transfers valid unsaved edits. No-op saves preserve exact bytes; changed form saves keep unknown keys but may reformat YAML comments and whitespace. Invalid active YAML opens in Raw for correction. On first open, VisPa copies its installed default profile to `vispa_config.default.yaml` beside the active config; an existing copy is never replaced. If that copy is unavailable or invalid, Default YAML shows the installed profile with a warning. **Reset to default** stages the frozen local profile; **Restore backup…** stages a selected historical YAML/JSON. Neither writes the active file until **Save settings**. Save validates the complete file, backs up its previous bytes under `config_backups/` with a unique timestamp, and refuses an externally changed file or failed backup. Default YAML cannot be edited or saved directly. **Reload** discards unsaved edits. Restart VisPa after changing source folders. The cache and FNT paths do not change scientific rendering parameters.

Combined review figures derive text wrapping, legend/footer height and labeled-axis separation from the selected font metrics and available axes width; panels retain full image extents and original aspect ratios, anchored at the top. These are automatic layout constraints rather than separate scientific parameters. Tune `figure.review_figsize` and `figure.review_dpi` through the existing settings interface.

Soma inline-label presentation: `--set marker.label_mode=none` (default, role legend only), `short` (S), or `numbered` (1 with a thin leader). Cyan box/cross coordinates are identical in all modes. Existing label font size and offset remain tunable; `vispa settings --scope review` lists the enum and effects.

GUI Render now uses the same combined legend layout as the bounded runner. Soma/Context use explicit crop-pixel index axes, all standalone PNG tabs carry role legends outside the image, and GUI cache keys include gui.py/toolkit.py hashes so local code changes invalidate earlier figure strips even when the package version stays unchanged.

## Python import boundary

`import vispa` is the only supported Python import. Existing
`visual-toolkit.*.v1` receipt schemas and `visual_toolkit` settings blocks remain
readable as data contracts, but the old Python namespace and command aliases are
removed. Existing installations, data, and historical manifests are not moved or
rewritten. The GitHub repository is `bylaikaby/VisPa`; each lab user can extract
it into their own local source folder.

The offline wheel command above uses an explicit placeholder path; substitute the exact built wheel recorded in the [current run receipt](work/fnt_onboarding_20261022/run_receipt.json). That receipt is the current installation and verification entry point.
