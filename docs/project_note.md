# VisPa project journal

### 2026-11-17 | Agent Codex | VisPa / ReMAP | ReMAP FNT verification on L02Win003

- Tested VisPa origin commit `68c573fe9de9baac00e13bd9e5d65f7003795a23` (CLI 1.21.7) with ReMAP 0.2.1 at `619fdd0e3e1bdfa04dcd5a3464ba30d93dcf70a7`. The bridge resolved after correcting its import in the isolated checkout.
- Audited the server workbook `remap_outputs/251637/neuron_table/251637_results.xlsx`, sheet `Summary`. All 574 unique cohort IDs mapped to readable processed SWCs that parsed and were hashed. No duplicates, missing inputs, or extra cached SWCs. Receipt on L02Win003 is `%TEMP%/vispa-pc2-68c573fe/work/251637_full_swc_audit.json`.
- The four-case producer dry run resolved and hashed the server SWCs and FNT tools. Historical legacy score parity covers that four-neuron pilot (10/10 entries). Full-cohort score and cluster parity remain unverified.
- Next, locate existing server FNT scores for the cohort and verify their marker identities and pair coverage before clustering.
