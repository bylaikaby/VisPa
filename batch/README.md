# VisPa brain-view batch operator

Local candidate `1.12.0.dev0`. The entry point is `python -m batch.render_brain_views` from this checkout. Each declared job renders one declared root/reference OBJ and one processed SWC with VisPa's existing OpenGL worker. An optional exact `region` selector adds at most one manifest-bound region OBJ from `sources.brain_view.region_mesh_root`; no region is inferred. Existing jobs that intentionally use a region OBJ as `mesh_path` keep that behavior. No mesh generation, coordinate transform, cohort discovery or data fetch occurs here.

```mermaid
flowchart LR
  J[Explicit jobs JSON] --> P[Dry-run: sorted identities, root/region/SWC hashes, frame, camera, output paths]
  C[VisPa dataset config] --> P
  R[Optional exact region selector] --> P
  P -->|--limit 1| W[VisPa brain-view isolated worker]
  W --> O[One PNG + adjacent VisPa receipt per pair]
  O --> B[Shared batch receipt]
  B -. planned, no transfer yet .-> M[Multimodal_INS analysis_scripts]
```

## Bounded local example

Copy [the placeholder settings](local_pilot.example.json) into an untracked file under `work/jobs/`, then replace every placeholder with exact local paths, identities, frame and units. Keep outputs in a sibling directory such as `work/results/`; the operator refuses an output root inside the directory that contains the jobs file. Machine-specific filled jobs and rendered outputs must stay outside version control. The private prior pilot was a wiring and rendering test, not a scientific region-mesh validation.

```powershell
cd D:\VisPa_publish_20261023
python -m batch.render_brain_views --jobs work/jobs/filled-local-jobs.json --output-root work/results/brain-view-batch-new-run --limit 1 --dry-run
python -m batch.render_brain_views --jobs work/jobs/filled-local-jobs.json --output-root work/results/brain-view-batch-new-run --limit 1
```

For a new request, provide `schema=vispa.brain_view_batch.v1`, `vispa_config`, and `jobs` in one JSON file. Each job has explicit `sample_id`, `region_id`, `mesh_path`, `mesh_label`, `neuron_ids`, `coordinate_frame`, `coordinate_units`, optional exact `region`, optional `portal_region`, and optional `camera_overrides` using VisPa's documented [brain-view setting names and ranges](../README.md#shared-settings-interface). `region_id` remains the stable job/output grouping label; `region` is the new OBJ selector and accepts one exact filename, display name or acronym.

| Parameter | Default / allowed value | Effect |
|---|---|---|
| `--jobs` | Required JSON path | Declares the exact local mesh and neuron pairs. |
| `--output-root` | Required fresh directory | Contains one PNG/receipt per pair and one batch receipt; existing root refuses. |
| `--dry-run` | Off | Prints resolved hashes, frame/units, camera and paths without writing. |
| `--limit N` | Explicit positive integer | Selects the first N jobs sorted by sample, region and neuron; use `1` for first render. |
| `--all` plus `allow_all` | Both must be explicitly true | Enables all declared jobs; no cohort is inferred. |
| `mesh_label` | `<region_id>`; 1–18 printable ASCII characters | Names the actual OBJ role beside its color patch; set it explicitly when the region ID is longer than 18 characters. |
| `region` | Omitted; exact filename, display name or acronym | Adds one manifest-bound region overlay while preserving the declared root/reference mesh and its full camera extent. |
| `camera_overrides` | `{}`; valid VisPa brain-view settings | Changes the recorded view, such as `camera_distance_scale` for a small region. |

The executed pilot PNG, adjacent snapshot receipt and shared batch receipt remain privately stored under `work/` as review evidence. The command above uses a new output root because existing outputs are never overwritten.

The worker writes one PNG and adjacent JSON receipt with root/optional-region/SWC hashes, source frame, stored units, camera settings, renderer version and PNG hash. The operator writes one `batch_receipt.json` with sorted requests and status. A failed job preserves that receipt with `partial_or_failed`, and the command exits with status 2 after printing the result rather than raising an unhandled traceback. For the new overlay mode, camera distance remains based on the declared root/reference mesh, not the smaller region. A batch of jobs is a set of independent views, not a combined multi-neuron scene. The future `Multimodal_INS/analysis_scripts` location is a planned handoff only; this operator remains in VisPa now.

## ReMAP region and FNT review bridge

For the separate declared-case ReMAP and VisPa bulk workflow, see [the bridge module guide](MODULE.md). This checkout-only candidate uses saved FNT scores and local configured raw SWCs; it does not claim anatomical acceptance or select a final cluster count.
