# Ingredient Seed Database

Documentation for the ingredient safety seed data and how to extend it.

---

## Schema

Each entry in the seed JSON files maps to one row in the `ingredients` table plus optional rows in `ingredient_aliases`.

```
ingredients
  id             SERIAL PRIMARY KEY
  name           TEXT UNIQUE NOT NULL          -- lowercase canonical name
  inci_name      TEXT                          -- INCI (cosmetic) name in CAPS
  e_number       TEXT                          -- EU food additive E-number (e.g. "E102")
  cas_number     TEXT                          -- CAS Registry Number (preferred path for IARC/Prop65 matching)
  ingredient_type TEXT                         -- 'food_additive' | 'cosmetic' | 'food' | 'both'
  safety_level   TEXT                          -- 'safe' | 'caution' | 'avoid'
  score_penalty  INT                           -- 0–30 subtracted from 100-base score
  concerns       TEXT[]                        -- canonical tags (see Concern Tag Vocabulary below)
  eu_status      TEXT                          -- 'approved' | 'restricted' | 'banned' | 'unknown'
  sources        TEXT[]                        -- e.g. ['cosing', 'efsa', 'iarc', 'prop65']
  notes          TEXT
  updated_at     TIMESTAMPTZ
```

### CAS Numbers

The `cas_number` column is the primary matching path used by the IARC and Prop 65 importers. Always include a CAS number for new entries where one is known — it dramatically improves importer match rates.

---

## Data Files

| File | Entries | Description |
|---|---|---|
| `data/e_numbers.json` | ~187 | EU food additives (E100–E967). Sources: EFSA, EU Reg 1333/2008. |
| `data/cosing_flagged.json` | ~59 | Flagged cosmetic ingredients. Sources: CosIng, EU Reg 1223/2009. |
| `data/food_flagged.json` | ~15 | Food processing contaminants and high-concern food compounds. Sources: IARC, Prop 65, EFSA. |
| `data/fragrance_allergens_flagged.json` | ~15 | EU Annex III declarable fragrance allergens. Sources: EU Reg 1223/2009, SCCS/1659/21. |

---

## Concern Tag Vocabulary

All `concerns` array entries must come from this canonical list (defined authoritatively in `instructions/agents/analysis_agent.md`). Do not add new tags without updating both files.

### IARC Carcinogenicity
- `iarc_group_1` — confirmed human carcinogen (−25 pts)
- `iarc_group_2a` — probably carcinogenic (−25 pts)
- `iarc_group_2b` — possibly carcinogenic (−12 pts)
- `carcinogen` — legacy tag, equivalent to `iarc_group_2b`; retained for backwards compatibility

### California Prop 65
- `prop65_carcinogen`
- `prop65_reproductive_toxin`
- `prop65_developmental_toxin`

### ECHA REACH
- `echa_svhc` — Substance of Very High Concern (Candidate List)

### RASFF
- `rasff_alert` — active EU Rapid Alert for Food and Feed notification

### General safety
- `endocrine_disruptor` | `allergen` | `fragrance_allergen` | `paraben`
- `sls` | `sles` | `formaldehyde_releaser` | `irritant`
- `phototoxic` | `neurotoxin` | `aquatic_toxin` | `petrochemical`
- `reproductive_toxin` | `developmental_toxin` | `banned_eu`
- `artificial_color` | `artificial_sweetener`
- `process_contaminant` — forms as a processing byproduct (acrylamide, furan, glycidol, etc.) — NOT an intentional additive

---

## Quality Bar for New Entries

Before adding an entry:
1. **Canonical name** — lowercase, unambiguous, matches how it appears on product labels
2. **CAS number** — include whenever known; required for IARC/Prop 65 importer matching
3. **At least one credible source** — CosIng, EFSA, IARC, EU Regulation number, or peer-reviewed literature
4. **Concerns from vocabulary only** — do not invent tags; use `notes` for anything that doesn't fit
5. **Score penalty calibrated**:
   - Banned substances: 25–30
   - IARC Group 1 / Prop 65 known carcinogen: 20–25
   - Endocrine disruptors: 15–20
   - Strong allergens / sensitisers: 12–15
   - Mild irritants / restricted substances: 5–10
   - Process contaminants at low background levels: 5–8
6. **`should_add_to_db` threshold**: only seed entries you'd rate ≥0.8 confidence

---

## Running the Seed

From `backend/`:

```bash
python -m db.seed.seed_ingredients
```

The script upserts all four JSON files. On conflict (duplicate `name`), it updates `safety_level`, `score_penalty`, `concerns`, `eu_status`, `notes`, and `cas_number` (via COALESCE — preserves manually backfilled values if seed has NULL).

---

## Re-running Enrichment Importers

After adding new entries (especially with CAS numbers), re-run the enrichment importers to pick up any new IARC / Prop 65 matches:

```bash
python -m db.importers.iarc_importer
python -m db.importers.prop65_importer
```

These are update-only — they append to `concerns` and `sources` using a dedup merge and never overwrite `safety_level`, `eu_status`, or `score_penalty`.

---

## Gap Audit Process

To find new high-value entries to add:

1. **Check IARC unmatched log** — the importer prints unmatched IARC agents after each run. Prioritize Group 1 / 2A that appear in food or cosmetic products.
2. **Check Prop 65 unmatched log** — same approach; prioritize substances in common product categories.
3. **Run a label scan** — scan 5–10 real products and note which ingredients resolve as `resolution_method: "unresolved"`. High-frequency unresolved ingredients are the highest-value additions.
4. **Avoid IARC Group 3** — the importer filters Group 3 at load time; adding these CAS numbers to the seed will not produce any IARC match.

### When to expand seed vs. rely on Claude write-back

- **Use seed** for: well-known substances with stable regulatory status, EU-regulated additives, commonly-encountered ingredients
- **Use Claude write-back** (`use_claude=True` in `ingredient_resolver.py`) for: novel compounds, brand-name blends, obscure INCI names — Claude classifies and writes back to DB for future lookups

---

## TODO

- [ ] Refresh IARC CSV to pick up Monographs 134+ (aspartame Group 2B classified 2023; current CSV predates Monograph 134)
- [ ] Add Prop 65 Part 3 sources (NSF, NTP) — currently only Part 1 (state-qualified)
- [ ] Add ECHA SVHC entries for `echa_svhc` tag coverage
- [ ] Consider adding microplastic concern tag once EFSA finalizes assessment
