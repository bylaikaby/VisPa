# VisPa and ReMAP project note

This is the living record for VisPa and its sibling ReMAP package. The [Projectome journal](https://github.com/InteroAnat/projectome_analysis/blob/codex/insula-pipeline-evolution-20261008/docs/project_note.md) retains the full historical record and wider Projectome research. Record new VisPa and ReMAP milestones here with the actual agent, Shanghai timestamp, evidence, decisions and next steps.

## Status snapshot

| Area | Current evidence and next step |
| --- | --- |
| Standalone HTML | Secondary candidate 0.7.0; development paused by user. Full desktop design/function parity remains incomplete. |
| VisPa | Source candidate 1.21.8.dev2 includes [Cohort Progress](../README.md#cohort-progress) and [Function Overview](../README.md#vispa-function-overview). See the [changelog](../CHANGELOG.md). |
| ReMAP | Sibling source candidate 0.2.2.dev3 supplies atlas measurement, FNT, clustering and table operators. The [ReMAP guide](../packages/remap/README.md) and [changelog](../packages/remap/CHANGELOG.md) describe the public source interfaces. |
| 251637 FNT | The cohort audit covered 574 unique identities and all corresponding processed SWCs. The current exploratory workbook covers 260 scored and 314 unscored neurons. Source producer runs matched all 10 and 78 within-run entries on separate four- and twelve-neuron subsets of the 260-source matrix. Cross-batch pairs and full-cohort score parity remain open. See the local consolidated review and receipts in `work/remap_clustering_251637_20261117/`. |
| Scientific review | The 212- and 260-source matrices disagree on all 22,366 shared off-diagonal scores. Cached inputs differ and full historical lineage remains unresolved. Cluster method, normalization, K and anatomical interpretation remain open. |

The cited study outputs are held in the research workspace.

## Insula study workflow

1. Generate [Function Overview](../README.md#vispa-function-overview) to trace the single-monkey and multi-monkey routes. Supply exact sample and neuron identities and declared coordinates.
2. Check the [saved-score review](../packages/remap/README.md#saved-score-analysis-and-review) with a bounded case and matching regional tables. Saved FNT files and source tables feed the projection hierarchy and its candidate assignments. Keep candidate tables and source workbooks separate.
3. Check cohort scope before comparing figures. The [atlas display](../packages/remap/README.md#atlas-insula-hierarchy-display) restricts the saved parent tree to the declared soma roster. [Cohort Progress](../README.md#cohort-progress) validates saved composition evidence through a separate report.
4. Use the pinned research drivers and receipts for paper-method figures, flat maps, morphology and functional evidence. Candidate clustering and software checks support technical review. Scientific interpretation requires the study-specific evidence.

### 2026-11-19 | Codex | Integrated source candidate

- Work agent Codex. Recorded at 2026-11-19T08:49:30+08:00 (Asia/Shanghai). Event date 2026-11-19. Reconciled the integrated source with the current remote VisPa tree, retaining its desktop badge and paused HTML changes. Verified the source Function Overview export, a bounded Cohort Progress export, 324 VisPa tests and 43 ReMAP tests. The local study guide and figures retain the panel-level review and reproducibility evidence.

## Legacy milestones and source records

- **October 2026.** Projectome's VisualToolkit became VisPa. Legacy region analysis and FNT workflows became the basis for ReMAP. See the region code audit, metric terminology, 251637 clustering review and ARM projection clustering review. Some evidence paths in the 251637 review are historical and unavailable.
- **Early November 2026.** VisPa and ReMAP shared acquisition and DS00 selection work, and VisPa added whole-animal bulk review. The Projectome journal retains the dated development, checkout and coordinate decisions.
- **November 17, 2026.** ReMAP entered the VisPa source tree. PC2 verified cohort input coverage and a bounded dry run. Later local runs added native score comparisons, clustering sensitivity checks and a workbook with hash-bound assignment inputs. See the consolidated review for candidate output and limits. The earlier workstation entry is preserved below, including its original next step.

## Journal

### 2026-11-17 | Agent Codex | Consolidated project note

- Recorded at 2026-11-17T21:13:54+08:00 (Asia/Shanghai). Consolidated the VisPa and ReMAP milestones from Projectome and incorporated the existing VisPa workstation entry. The README and repository guidance now point here for future software work.
- Legacy Projectome journal SHA-256 at migration: `5bb03042e237750c0077165937db0bb3ac1524c73ff14c8f50e0303c6990e90f`. Imported VisPa entry source is the local audit checkout of `3b8f17d981dd0d95d62eca73b2da8d25d1203c2b`, `docs/project_note.md`, SHA-256 `6e0f24e70c46cd0fbdf7b696719c258a75a23fa4c58dc967df33679417db78b1`.

### 2026-11-17 | Agent Codex | VisPa / ReMAP | ReMAP FNT verification on L02Win003

- Tested VisPa origin commit `68c573fe9de9baac00e13bd9e5d65f7003795a23` (CLI 1.21.7) with ReMAP 0.2.1 at `619fdd0e3e1bdfa04dcd5a3464ba30d93dcf70a7`. The bridge resolved after correcting its import in the isolated checkout.
- Audited the server workbook `remap_outputs/251637/neuron_table/251637_results.xlsx`, sheet `Summary`. All 574 unique cohort IDs mapped to readable processed SWCs that parsed and were hashed. No duplicates, missing inputs, or extra cached SWCs. Receipt on L02Win003 is `%TEMP%/vispa-pc2-68c573fe/work/251637_full_swc_audit.json`.
- The four-case producer dry run resolved and hashed the server SWCs and FNT tools. Historical legacy score parity covers that four-neuron pilot (10/10 entries). Full-cohort score and cluster parity remain unverified.
- Next, locate existing server FNT scores for the cohort and verify their marker identities and pair coverage before clustering.

## HTML candidate publication and pause

- Work agent: Codex. Recorded at: 2026-11-17T22:45:43+08:00 (Asia/Shanghai). Event date: 2026-11-17; exact activity times are not reconstructed. The user paused HTML development and made it secondary; desktop VisPa remains primary. Full design and function parity is still required if development resumes.
- Published source: [standalone HTML 0.7.0](../web/vispa.html), copied unchanged from the live checkout; SHA-256: `da1ead2ce79b2c0300e3c3b0b19b476b7e6bbd8832ab346bbc71afbcd6b6e618`. It embeds NiiVue 0.69.0 with its license and requires no Python service. The [changelog](../CHANGELOG.md) records incremental candidate capabilities. Desktop version remains 1.21.7; no package rebuild, installation or deployment was performed.
- Implemented candidate scope: local figure and review-note input/output, SWC/OBJ preview, local volume viewing, bounded IONData acquisition, NIfTI atlas lookup, and bounded Soma/Context/Sagittal computations. Desktop reference inputs include atlas_names, percentile_normalize, clip_segment and prepare_sagittal_panel; browser implementations remain provisional.
- Earlier bounded Chrome checks covered five synthetic atlas cases, Soma normalization, four Context composition cases, three clipping cases, and three Sagittal preparation cases. Numeric projection comparisons were within 1e-12. These are synthetic component checks, not complete application parity. Local evidence is retained under D:/VisPa_publish_20261023/work/html_vispa_check/ (not included in this publication). The Soma screenshot from the wrong browser target is invalid and is not acceptance evidence.
- Publication checks: both inline scripts parse; source and published HTML bytes match. Remaining work includes exact desktop design, FNT/browser replacement, production data and endpoint integration, configured DS geometry binding, robust expanded-memory limits, saved-download readback and responsive visual acceptance. No complete real-data or cross-device acceptance is claimed.
- Request reconciliation: prior project-note consolidation and Projectome merge notice were already published, preserving the original journal. This update publishes the secondary HTML candidate and documentation only; unrelated local ReMAP work is excluded. Development is paused; no automatic resumption is scheduled.
