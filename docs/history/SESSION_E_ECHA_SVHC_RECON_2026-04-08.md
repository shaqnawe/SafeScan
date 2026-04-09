# Session E — ECHA REACH/SVHC Recon Report (2026-04-08)

## Decision: DEFERRED

Recon showed only 4 CAS matches against our 44 CAS-populated ingredient rows.
All matches are already well-covered by IARC + Prop 65 tags. No importer was created.

**Revisit trigger**: When `SELECT COUNT(*) FROM ingredients WHERE cas_number IS NOT NULL` exceeds 150 rows.
Currently 44 rows (as of 2026-04-08). Expected growth: organic Claude classification write-back over 3-6 months.

---

## Data Source

- **Source**: chemsafetypro.com XLSX mirror of ECHA official candidate list
- **URL**: `https://www.chemsafetypro.com/Topics/EU/REACH_SVHC_List_Excel_Table.xlsx`
- **Size**: 233 substances, 261 CAS numbers (some entries multi-CAS), updated 2023-01-17
- **Fields**: Index, Chemical Name, EC Number, CAS Number, Inclusion Date
- **Access**: 200 OK; direct ECHA programmatic access blocked (403 on echa.europa.eu; 502 on chem.echa.europa.eu)

## Scope Check Results

**CAS overlaps with our ingredients table (44 CAS-populated rows)**: 4

| Ingredient | CAS | Existing concerns | Net gain from echa_svhc tag |
|---|---|---|---|
| benzo[a]pyrene | 50-32-8 | iarc_group_1, prop65_carcinogen, process_contaminant | label only |
| acrylamide | 79-06-1 | iarc_group_2a, prop65_carcinogen/reproductive/developmental, neurotoxin, process_contaminant | label only |
| lead | 7439-92-1 | iarc_group_2b, prop65_carcinogen/reproductive/developmental, developmental_toxin | label only |
| furan | 110-00-9 | prop65_carcinogen, process_contaminant, iarc_group_2b | label only |

**Name-only match (no CAS in DB at time of recon)**: boric acid (SVHC CAS 10043-35-3)
→ CAS backfilled as part of Session E cleanup

**Cosing overlap (already partially tagged)**:
- Cyclopentasiloxane (D5) → SVHC CAS 541-02-6, sources already include 'echa'
- Cyclotetrasiloxane (D4) → SVHC CAS 556-67-2, sources already include 'echa'
→ CAS numbers added to cosing_flagged.json for future seed runs

## Cleanup Actions Taken (no importer)

1. `boric acid` CAS backfilled in DB: `UPDATE ingredients SET cas_number = '10043-35-3' WHERE lower(name) = 'boric acid'`
2. `Cyclopentasiloxane` CAS `541-02-6` added to `cosing_flagged.json`
3. `Cyclotetrasiloxane` CAS `556-67-2` added to `cosing_flagged.json`
4. `docs/history/SAFESCAN_UPDATE_INSTRUCTIONS_v1.1.md` source 3 marked DEFERRED
5. `TODO.md` ECHA entry updated with revisit trigger

## What Was NOT Done

- No `echa_svhc_importer.py`
- No `echa_svhc` concern tag added to vocabulary or local_analyzer.py
- No weekly_sync.sh changes
- No scoring changes

## Note on local_analyzer.py

Suggestion arose during recon to add `echa_svhc` as a scored concern tag in `local_analyzer.py`.
Deferred separately: scoring rubric decisions require dedicated analysis of which ingredients
would actually see grade changes. Not in scope for a data import session.
