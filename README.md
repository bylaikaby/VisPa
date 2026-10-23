# VisPa — Visual Projectome Analysis tool

VisPa reviews macaque neuron and microscopy data from configured lab sources. This checkout is 1.11.0.dev6, local and unreleased; the published main branch may still be older.

## Install on a fresh Windows PC

Use 64-bit Windows and Internet access. You do not need to install Python, Conda, Git, GitHub CLI, or create a GitHub account. VisPa bootstraps a checksum-verified per-user Miniforge installation when Conda is absent, then creates its dedicated Python 3.13 environment. A managed computer may require its normal IT approval for software installation.

1. After this dev6 candidate is published, select its exact branch or commit in [the VisPa repository](https://github.com/bylaikaby/VisPa), use **Code → Download ZIP**, and **Extract All** into a local user folder. The current main ZIP must not be assumed to contain dev6 until publication.
2. Open PowerShell in the extracted folder and run:

   ```powershell
   .\install.cmd -NoLaunch
   .\VisPa.cmd --version
   .\VisPa.cmd config-check --validate-only
   .\VisPa.cmd
   ```

The installer uses `%LOCALAPPDATA%\VisPa\conda-env` for its environment and `%APPDATA%\VisPa\vispa_config.yaml` for the active profile. It creates the profile from the packaged lab defaults only when absent. The desktop shortcut points to `VisPa.cmd`; no PATH edit or Conda activation is required. `-NoLaunch` lets you verify the install before opening the GUI. The package does not include private images, SWCs, credentials, or an FNT executable. The lab catalog, microscopy shares, image cubes, and raw SWCs have separate configured sources; inspect their availability on the lab network with `.\VisPa.cmd config-check`.

### Update, repair, and options

To update, extract a newer ZIP into a separate local folder and run its `.\install.cmd -NoLaunch`. Repeat installation preserves the active profile and user cache. Run `.\VisPa.cmd --version` from the new source folder afterward. If an existing environment is damaged or contains an incompatible older visual-toolkit distribution, select a new `-InstallDir` rather than deleting it without review.

`.\install.cmd -DryRun` prints the resolved Conda selection, source, environment, profile, cache, and launcher paths without installing. An existing Conda executable can be selected with `-Conda PATH`; `-NoBootstrap` fails clearly when Conda is absent. `-Config PATH` selects an existing active profile, `-Wheel PATH` selects an exact local VisPa wheel, and `-Wheelhouse PATH` provides local Python package wheels. A fully offline setup also needs Conda and its environment packages prepared locally; a pip wheelhouse alone does not replace the Conda environment solve. Keep the extracted source locally so `VisPa.cmd` can find its source-folder launcher.

If Conda is absent and `%LOCALAPPDATA%` contains spaces or non-ASCII characters, automatic Miniforge bootstrap stops before downloading. Choose an ASCII path without spaces that you own and can write, then run, for example, `.\install.cmd -NoLaunch -MiniforgeRoot D:\VisPaTools\miniforge3` on a writable D: drive. This flag changes only the Miniforge bootstrap location; the VisPa environment remains under `%LOCALAPPDATA%\VisPa\conda-env`. Reuse the same root when repeating installation. The installer changes neither user PATH nor Conda activation.

The [Windows installation workflow](.github/workflows/windows-install.yml) downloads an anonymous ZIP for the exact commit, runs a bounded install in a temporary user profile, checks installed runtime and Settings callbacks, and records graphics capability separately. Its result applies to that hosted Windows guest. Lab share access, visible desktop review, and scientific or anatomical acceptance remain separate.
## Using the GUI

1. Connect to the lab intranet. Enter a Sample ID and Neuron ID, or click **Neuron list** to choose one.
2. Click **Load & Auto-Fill Soma**.
3. Click **Render**; review the output folder shown in **Saving**.
4. Use **3D brain view** when a processed SWC and mesh are configured. **fnt-tracer** uses the exact VisPa cached native FNT project when available and requires a separately installed FNT executable to launch.

An optional local one-neuron example is being prepared at `demo/demo.yaml` with source evidence in `demo/README.md`. It selects real neuron 252385/044 through the normal configured intranet sources, so the lab network is required for fresh source access. The example config and outputs are ignored by Git and absent from the source ZIP. Once verified, launch it with `.\VisPa.cmd gui --config .\demo\demo.yaml`; inspect its receipt and figures before accepting any scientific result. The public morphology-only SWC command below exercises one limited path.

## Development and operator commands

Primary standalone development workspace: `D:/VisPa`. Package/distribution: `vispa`; commands: `vispa`, `vispa-gui`. Existing `Visual_toolkit` imports/class and `visual-toolkit` commands remain compatibility aliases.

`VISPA_CONFIG` and `VISPA_WHEELHOUSE` are the VisPa environment handles. Pass `--config PATH` for a specific run; otherwise `VISPA_CONFIG` wins, then the own per-user config at `%APPDATA%\VisPa\vispa_config.yaml`. The older `VISUAL_TOOLKIT_CONFIG` and `PROJECTOME_DATASETS` environment variables and VisualToolkit config files are left untouched and are not selected by normal VisPa startup. Pass an old file explicitly with `--config` or `config-init --from-config` only when you intend to use it. Caches and outputs default to `%LOCALAPPDATA%\VisPa`. The `visual_toolkit` settings key and existing `visual-toolkit.*.v1` schemas retain compatibility. Use a fresh environment: overlapping `visual-toolkit` distribution ownership is rejected by the installer.

Legacy leaf-module imports resolve to the same primary module objects and settings state; the legacy GL parent remains a state-free namespace. Optional OpenGL remains lazy. `python -m vispa` and `python -m Visual_toolkit` are supported, as are their GUI module launchers. The old class name aliases `VisPa`, without a second implementation.

New standalone run receipts, builds and candidate outputs live under `D:/VisPa/work/`. The [shared validation receipt](work/fnt_onboarding_20261022/run_receipt.json) records versioned milestones separately; [the Windows installation workflow](.github/workflows/windows-install.yml) will provide dev6 Windows Server VM evidence after publication and execution. The living project journal remains `D:/projectome_analysis/docs/project_note.md`. Existing projectome receipts remain historical evidence; external scientific data/cache paths remain explicit configuration.

### Repository status and compatibility

VisPa includes a live per-sample IONData neuron list for the configured lab intranet and review panels for configured local microscopy resources. The live list is fetched from the neuron API; image cubes, raw SWCs, and microscopy files use separate configured hosts or shares. The package contains only server addresses and candidate sample-resource links, not source data, credentials, or local project tools. These links and checksums do not establish current share availability or scientific acceptance.

This checkout is **1.11.0.dev6, local and unreleased**. It preserves the existing rendering and source-verification algorithms. The DS00 sagittal panel retains its two documented axis hypotheses and its manifest, hash, geometry, and source checks; those hypotheses remain candidates pending independent anatomical validation. No study data, credentials, or private source files are included; the package profile declares server endpoints and ten known sample mappings without copying images or SWCs. `extraction_manifest.json` records the historical extraction snapshot; the linked dev5 receipt does not verify this dev6 Conda candidate.


The supported Windows install route is Conda-first through `install.cmd`. Keep development environments separate from the projectome analysis interpreter. The source test command is `python -m unittest discover -s tests -v` from an environment with the declared dependencies. An explicit local wheel can be passed to `install.cmd -Wheel PATH`; the ordinary ZIP install uses the extracted source. The older pip/venv validation artifacts in this checkout are historical and do not establish this Conda candidate.

The headless operator is `vispa render`. It accepts one local `.npy` array in ZYX or YX order, a declared soma coordinate, origin, voxel spacing, role, and output directory. The three coordinate triples use XYZ micrometres. TIFF, NIfTI, SSH, and YAML extras remain available to backend and GUI workflows. The first run should use `--dry-run`, which resolves the inputs, settings, output PNG and receipt without creating directories, reading image pixels, or accessing a source. A real run writes the PNG and its JSON receipt and refuses to overwrite either.

```text
vispa render --input cube.npy --sample sample-01 --neuron 0007 --soma 120 240 30 --origin 0 0 0 --resolution 0.65 0.65 3 --coordinate-frame sample-native-XYZ --role soma --output-dir review --dry-run
```

Use `--role context` for the 5 µm style. `--set PATH=VALUE` overrides review settings; scalar values and numeric sequences are supported, such as `--set figure.panel_dpi=400` or `--set soma_window.cubes_xy_steps=1.5,1.25,1`. Unknown keys, out-of-range values and invalid combinations fail before changing global settings. Run `vispa settings` to print each setting's default, current value, valid range and effect as JSON. Python callers can use `review_settings_schema()` and pass a mapping or a list of `PATH=VALUE` strings to `apply_setting_overrides()`. The single-panel review figure includes the image and target marker legend and labels the displayed plane as native X/Y. The cyan target box and cross mark the supplied coordinate; they do not validate anatomy, orientation, or laterality. The labeled single-panel CLI review reserves font-measured clearance between its axes and shared legend; multi-panel and unlabeled figures retain the legacy layout.

`vispa gui` starts the optional Tk interface. `vispa --help`, `vispa --version`, and `python -m vispa --help` do not load image libraries, open windows, or acquire data. Package import does not change `sys.path` or import `IONData`.

The compatibility command `vispa example` fetches one public SWC for a morphology-only preview. It does not exercise the lab image, atlas, FNT, or brain-view paths. The cached source is checksum-pinned; its coordinate frame and units are unspecified. Preview its source URL and proposed output locations without network or file access first:

```powershell
.\VisPa.cmd example --dry-run
```

The one-record operation accepts `--cache-dir`, `--output-dir`, and `--dpi` (100–240; default 160). It reuses an existing figure only when its receipt, source checksum, VisPa version, renderer-code checksum, DPI, full-extent declaration, and PNG hash match; changed renderer code, version, or DPI uses a named variant, and conflicting files are preserved. No sample configuration is required.

## One-volume DS00 montage

`vispa montage` renders one explicitly named 3D NIfTI into the preserved five DS00 views. It does not discover cohorts, read workbooks, choose files, or apply a transform. The affine must yield LPS voxel axis codes, as in the source montage. NIfTI affines map voxel indices into RAS+ world coordinates; each panel labels increasing projected anatomical directions in RAS+ millimetres. The header must declare millimetres, or the operator must explicitly declare `--units mm` when the header units are unknown; known non-mm units are rejected. The output includes a compact intensity-image legend. The `[3d]` extra provides the montage dependencies.

```powershell
.\VisPa.cmd montage --input 'D:\data\sample.nii.gz' --output 'D:\review\sample-5view.png' --units mm --max-voxels 64000000 --set display_gamma=0.88 --dry-run
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
`environment.yml` installs the optional 3D dependencies in the Conda runtime. It requires a local OBJ mesh, an explicit sample ID and processed
SWC filename, and explicit coordinate-frame and coordinate-unit declarations in
`sources.brain_view`; it does not resolve cohort identities, use raw SWCs, fetch remote
data, or apply registration/mirroring. Preview the resolved paths and display settings
before launching a window:

```powershell
.\VisPa.cmd brain-view --sample 251637 --neuron 001.swc --config 'C:\data\visual_toolkit_config.yaml' --dry-run
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
are available through the compatibility `Visual_toolkit` module alias. Values can be mappings or
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

The packaged default is a same-intranet profile: it configures live IONData catalog access, separate BAP image-cube and raw-SWC hosts, known microscopy share roots, and per-user VisPa caches/outputs. Its sample-to-AnimalID and dataset links are candidate resource references and may be unavailable off the lab network. No credentials, FNT executable, local worker path, or other application's working-output path is set. The packaged YAML contains no literal Windows profile path. A new installation creates `%APPDATA%\VisPa\vispa_config.yaml` from package defaults; caches and outputs use `%LOCALAPPDATA%\VisPa`. To select a separate local config, pass `-Config PATH` to `install.cmd` or `--config PATH` to VisPa. On this checkout, the explicitly selected local example is `D:\VisPa\config\vispa_config.yaml`; no other lab PC needs that drive. JSON works with the standard library; YAML is included in the core install. Relative paths resolve from the config file's folder, or from the optional top-level `base_dir`.

Create the per-user YAML without overwriting anything already present:

```powershell
vispa config-init --dry-run
vispa config-init
vispa config-init --output 'D:\review\visual_toolkit_config.yaml'
vispa config-init --from-config 'D:\old\visual_toolkit_config.json' --output 'D:\review\visual_toolkit_config.yaml'
```

`--output` must end in `.yaml` or `.yml`; an explicit destination is never
overwritten. Without `--output`, the VisPa per-user YAML is the target and uses
packaged defaults. Import an older config only with `--from-config`; its source
bytes remain unchanged.
Passing `--output` selects the packaged same-intranet template; it never overwrites an existing destination. A fresh install or normal GUI launch creates the per-user VisPa config when absent. Legacy VisualToolkit YAML/JSON and environment variables remain untouched and require explicit `--config` or `config-init --from-config` selection. Existing CSV-only catalogs remain CSV by default; the Neuron list source selector can explicitly query Live IONData when a catalog is configured. Choosing a source never triggers automatic fallback. The created file contains validated values for review, brain-view and montage scopes as well as the lab source profile. A relative per-sample `swc_cache` resolves from the config folder unless `swc_cache_root` or `swc_root` is declared. The GUI parses its arguments first (abbreviations are rejected) and initializes only a valid implicit launch; `--config`, `--dry-run` and a configured VisPa environment path never create a file.

All lab server addresses and source roots live in the editable profile. In the packaged profile, each sample's `ds00_relative` is resolved under `defaults.ds00_root`, and `sources.dataset_manifest_relative` follows the same root. The `resample_5um` entries follow `defaults.resample_5um_root`. Changing these roots redirects the declared paths without editing ten per-sample UNC strings; existing profiles that use `ds00_processed` keep their original path meaning. Relative child paths must stay within their declared root. The sample filenames and SHA-256 declarations remain candidate provenance; changing a root does not verify that files or geometry match. The public morphology example's source URL, metadata URL, record ID, filename and expected SHA-256 are in `sources.public_example`.

For SSH sections, set `ssh_sample_id` alongside `ssh_remote_base`; that remote root is only eligible for the matching sample. `low_res_ssh_base=` is an explicit per-instance override. The GUI identity and auto-load behavior is selected from `visual_toolkit.default_sample`, `visual_toolkit.default_neuron`, and `visual_toolkit.auto_load`. The packaged profile starts on sample `250432` (AnimalID `747`) and `001.swc` with auto-load disabled; explicit CLI/constructor identities take precedence, and `--no-autoload` always disables startup loading. In the GUI, **Neuron list** uses the selected source and shows every API row for the exact sample ID, preserving zero-padded filenames and suffixes; selecting a row fills only the Neuron ID field. The source selector offers Live IONData explicitly alongside a configured dated CSV; on older CSV-only profiles, CSV remains selected unless you choose Live IONData. The compact note lists the eight INS-cohort AnimalIDs from the megatable and separately identifies sample 250432 / AnimalID 747; it does not classify individual neuron rows. **Render** (F5) produces the complete panel set (Soma, Context, Sagittal and TrioPlot); there is no per-panel selection. **Save outputs** beside Render chooses whether the run writes files (unticked = preview only), and **Save Soma NIfTI (.nii.gz)** in Saving controls the soma volume. The **3D brain view** action carries the current sample, neuron ID, and any loaded portal region to the isolated original OpenGL worker, using the configured processed SWC only. **fnt-tracer** uses an explicitly configured matching project first, then an exact VisPa native FNT cache project; its executable is needed only to launch the external tracer. There is no bulk action.

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

The processed-DS sagittal implementation requires a resolved dataset manifest, `defaults.ds00_root`, a configured per-sample image path and checksum, and local SWC input or cache. It records source identity and geometry. Its A/B mapping choices remain unresolved; successful loading or rendering is not anatomical acceptance.

## API and projectome integration

The primary Python import is `vispa`. `vispa.VisPa`, `REVIEW_SETTINGS`, and the plotting helpers are exposed lazily from `vispa.toolkit`. Core rendering accepts in-memory arrays, so a consumer can integrate the package without adopting the standalone acquisition providers or source layout.

Projectome owns its cohort runners, montage adapter, source manifest, and lab-specific configuration. It can depend on this distribution and keep a thin compatibility facade that maps its existing `Visual_toolkit` imports, injects the `IONData` provider, and supplies explicit data roots. The independent package contains only the generic single-volume DS00 renderer, not the cohort montage adapter or its workbook/path/selection logic. It carries candidate sample mappings and paths in its editable default profile, with no cohort runner, workbook, image data, or source SWCs; `extraction_manifest.json` preserves historical source path and hash provenance.

## Package checks

The package tests cover clean import without projectome or `IONData`, config-relative resolution, SWC validation and provider fallback, local coordinate geometry, a tiny-array render with its marker and receipt, DS00 frame parity, montage dry-run no-write behavior, and PNG/receipt output. No license is assigned by this staged extraction.

See [CHANGELOG.md](CHANGELOG.md) for the preserved toolkit history and extraction changes.


### Single-neuron resource and FNT preflight

Run `vispa config-check --config settings.yaml --sample 251637 --neuron 003.swc --dry-run` for a read-only JSON inventory (file hashes, source dates unknown as null, coordinate declarations, cache references and cube route/geometry). Add `--fnt` to require both a configured executable and an exact matching manual or native cached FNT project; this mode returns failure when either is unavailable and never starts the binary. The JSON also reports `project_ready` and `executable_ready` separately. Directory references are not recursively hashed; the inventory alone does not establish complete offline panel coverage or scientific acceptance.

The active VisPa profile can fetch one exact native FNT with `vispa fnt-fetch --config PATH --sample 250432 --neuron 001.swc --dry-run`; remove `--dry-run` to download and verify it into the VisPa cache. `visual_toolkit.fnt_tracer` exposes `auto_download` (boolean, default true), `cache_root` (optional path), `server_base_url` and `catalog_base_url` (plain HTTP(S) base URLs), `timeout_seconds` (positive integer, default 30), and `max_response_bytes` (positive integer, default 67108864). An explicit `project_root` keeps a matching annotated local project as first choice; otherwise the exact verified VisPa cache project is used. `config-check --fnt` stays read-only and reports project and executable readiness separately. The executable is required only to launch **fnt-tracer**. In the GUI, **Settings** opens the active config with six sections in **Organized editor**, complete editable **Raw YAML** (or **Raw JSON** for an explicit JSON config), and a read-only **Default YAML** reference. Choose Data folders, Sources, Brain view, FNT, Public example or Startup; use **Browse…** for paths. Raw mode includes sample-specific paths, geometry, provenance and display settings. Switching between the editing tabs transfers valid unsaved edits. No-op saves preserve exact bytes; changed form saves keep unknown keys but may reformat YAML comments and whitespace. Invalid active YAML opens in Raw for correction. On first open, VisPa copies its installed default profile to `vispa_config.default.yaml` beside the active config; an existing copy is never replaced. If that copy is unavailable or invalid, Default YAML shows the installed profile with a warning. **Reset to default** stages the frozen local profile; **Restore backup…** stages a selected historical YAML/JSON. Neither writes the active file until **Save settings**. Save validates the complete file, backs up its previous bytes under `config_backups/` with a unique timestamp, and refuses an externally changed file or failed backup. Default YAML cannot be edited or saved directly. **Reload** discards unsaved edits. Restart VisPa after changing source folders. The cache and FNT paths do not change scientific rendering parameters.

Combined review figures derive text wrapping, legend/footer height and labeled-axis separation from the selected font metrics and available axes width; panels retain full image extents and original aspect ratios, anchored at the top. These are automatic layout constraints rather than separate scientific parameters. Tune `figure.review_figsize` and `figure.review_dpi` through the existing settings interface.

Soma inline-label presentation: `--set marker.label_mode=none` (default, role legend only), `short` (S), or `numbered` (1 with a thin leader). Cyan box/cross coordinates are identical in all modes. Existing label font size and offset remain tunable; `vispa settings --scope review` lists the enum and effects.

GUI Render now uses the same combined legend layout as the bounded runner. Soma/Context use explicit crop-pixel index axes, all standalone PNG tabs carry role legends outside the image, and GUI cache keys include gui.py/toolkit.py hashes so local code changes invalidate earlier figure strips even when the package version stays unchanged.

## Legacy compatibility

`import Visual_toolkit`, `Visual_toolkit.Visual_toolkit`, `python -m Visual_toolkit`, `python -m Visual_toolkit.gui`, `visual-toolkit` and `visual-toolkit-gui` remain aliases. Qualified legacy leaf modules share primary module objects; the legacy GL parent is a state-free namespace.

Existing `visual-toolkit.*.v1` receipt schemas and the `visual_toolkit` settings key remain compatible. Legacy `visual_toolkit_config.yaml/json` files, per-user VisualToolkit folders, and `VISUAL_TOOLKIT_*` / `PROJECTOME_DATASETS` variables are preserved. Normal VisPa startup selects only its own config or an explicit `--config` path; old files can be imported explicitly. Existing installations, data, and historical manifests are not moved or rewritten. The GitHub repository is `bylaikaby/VisPa`; each lab user can extract it into their own local source folder.

The offline wheel command above uses an explicit placeholder path; substitute the exact built wheel recorded in the [current run receipt](work/fnt_onboarding_20261022/run_receipt.json). That receipt is the current installation and verification entry point.
