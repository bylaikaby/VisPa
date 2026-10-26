# VisPa development rules

Develop reusable code in this standalone repository. All new run receipts, builds and candidate outputs belong under this repository's `work/`; the projectome validation receipt remains historical source evidence, not a destination for future standalone work records. Only the living project journal stays at `D:/projectome_analysis/docs/project_note.md`; the project guide may cross-link this repository README. Scientific caches and immutable sources may remain external through explicit configuration: no data migration is implied. Preserve dirty work and scientific sources.

Planning stays with the user-selected model. Delegate execution to gpt-6-sol with low reasoning effort unless the user explicitly overrides it.

Scientific views require compact role legends, plane-specific axes and full reference extent; no FOV clipping/zero substitutes. New operators require validated settings, dry run, bounded single-case mode and provenance before batch. Human review marks and suggested transforms never silently mutate source SWCs or establish scientific acceptance.

Keep the explicit brain-view batch operator and its shared run receipts under this repository's `batch/` and `work/` for now. A later transfer to `D:/Multimodal_INS/analysis_scripts` is planned only; do not move code or outputs until that boundary and its source references are reviewed. Each batch image is one declared local OBJ mesh plus one processed SWC in the same declared frame and units, using VisPa's existing worker; do not infer transforms or call it a combined-neuron scene.

Every changed module carries version/date/changelog headers; update the consolidated CHANGELOG.md. Compatibility aliases must share module state and retain existing protocol/config contracts.
