# VisPa and ReMAP project note

This is the living record for VisPa and its sibling ReMAP package. The [Projectome journal](https://github.com/InteroAnat/projectome_analysis/blob/codex/insula-pipeline-evolution-20261008/docs/project_note.md) retains the full historical record and wider Projectome research. Record new VisPa and ReMAP milestones here with the actual agent, Shanghai timestamp, evidence, decisions and next steps.

## Status snapshot

| Area | Current evidence and next step |
| --- | --- |
| VisPa | Local source checkout is 1.21.7. The [operator guide](../README.md) covers interactive and bulk review. See the [VisPa changelog](../CHANGELOG.md) for version history. |
| ReMAP | The sibling package was imported from standalone ReMAP 0.2.1 at `619fdd0e3e1bdfa04dcd5a3464ba30d93dcf70a7`. The subsequent 0.2.2.dev1 clustering work is a local candidate. See the ReMAP guide and changelog for commands and changes. |
| 251637 FNT | The cohort audit covered 574 unique identities and all corresponding processed SWCs. The current exploratory workbook covers 260 scored and 314 unscored neurons. Source producer runs matched all 10 and 78 within-run entries on separate four- and twelve-neuron subsets of the 260-source matrix. Cross-batch pairs and full-cohort score parity remain open. See the local consolidated review and receipts in `work/remap_clustering_251637_20261117/`. |
| Scientific review | The 212- and 260-source matrices disagree on all 22,366 shared off-diagonal scores. Cached inputs differ and full historical lineage remains unresolved. Cluster method, normalization, K and anatomical interpretation remain open. |

The ReMAP sibling package and the cited candidate outputs are recorded from local development.

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
