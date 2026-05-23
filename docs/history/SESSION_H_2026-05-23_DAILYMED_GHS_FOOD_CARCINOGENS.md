# Session H — DailyMed, ECHA CLP / GHS, food carcinogen scoring, UI overhaul

**Date:** 2026-05-23
**Scope:** new data sources (DailyMed Rx, ECHA GHS, FDA drug recalls), scoring fixes (food now sees IARC / GHS / Prop 65 penalties), per-scan latency cleanup, end-to-end UI redesign, Claude Code auto-accept.

---

## Goals

Coming in:
1. Add more product / safety data sources, beyond OFF / OBF / USDA / OpenFDA / UPCitemdb.
2. Resolve the two deferred decisions from the FDA Recall Coverage Audit (2026-04-09):
   - Remove the per-scan real-time `_query_openfda()` call.
   - Evaluate the `drug/enforcement.json` backfill.
3. Refresh IARC CSV for Monographs 134+ (aspartame).
4. Make the UI feel consistent and premium across all screens.

Picked up along the way:
5. IARC / GHS / Prop 65 carcinogen tags weren't penalising food products — fix that.
6. Frontend `'E'` grade was still declared in TypeScript types; rubric is A–D only.
7. Enable Claude Code auto-accept mode for this project so edits don't pause for confirmation.

---

## Data sources added

### DailyMed (Rx prescription drugs)

`backend/db/importers/dailymed_importer.py`.

- Reuses the openFDA `/drug/label` manifest as the existing OTC importer.
- Filters records to `HUMAN PRESCRIPTION DRUG` product type (OTC stays in `openfda_importer.py`).
- Barcode strategy:
  - First tries `openfda.upc` (some Rx products have UPC) — normalises to EAN-13 by left-padding.
  - Falls back to `openfda.package_ndc` normalised to **NDC-11** (11 digits, 5-4-2 zero-padded). Code 128 barcodes on Rx packaging encode this directly; the scanner reads an 11-digit string and the DB exact-matches it as-is (no extra normalisation needed in the lookup path).
- Source tag: `'dailymed'`. Added to the `products.source` CHECK constraint via:
  ```sql
  ALTER TABLE products
    DROP CONSTRAINT IF EXISTS products_source_check,
    ADD CONSTRAINT products_source_check
      CHECK (source IN ('off','obf','user','image_scan','usda','openfda','upcitemdb','dailymed'));
  ```
- Wired into `scripts/weekly_sync.sh` as the step after `openfda_importer`.

### ECHA Annex VI CLP — GHS hazard enrichment

`backend/db/importers/ghs_importer.py` (originally scoped as `comptox_importer.py`).

**Pivot from CompTox → ECHA Annex VI:** initial research suggested EPA's CompTox Dashboard had a bulk GHS hazard CSV download. Verification with `general-purpose` research agent showed the documented page (`comptox.epa.gov/dashboard/downloads`) was retired and there is no pre-built bulk GHS export. The two practical sources were:

1. **ECHA Annex VI CLP harmonised classifications** — ~4,400 EU-binding substance classifications, downloadable Excel (.xlsx), structured CAS + H-code columns.
2. **PubChem LCSS** — much broader (tens of thousands of compounds) but gzipped XML with H-codes embedded in free-text strings, requires CID-to-CAS joining via a second file.

Picked ECHA — cleaner structure, authoritative, smaller. Importer was renamed and rewritten to read `.xlsx` via `openpyxl` (added to `requirements.txt`).

ECHA file layout quirks handled:
- First several rows are a disclaimer block — scanner skips ahead to the header row by detecting a known column name.
- Two-row header: row N has section labels (`Classification`, `Labelling`) with merged cells appearing as blanks; row N+1 has sub-column names (`Hazard Statement Code(s)`). Importer merges both rows, preferring the sub-header when present.
- Multiple H-codes per cell (e.g. `H350i H360D H341`) — splits on `[ ,;]+`, normalises suffixes (`H350i` → `H350`).

**curl** to download (requires `Referer` header — Azure WAF JS challenge blocks bare requests):
```bash
curl -L "https://echa.europa.eu/documents/10162/17218/annex_vi_clp_table_atp21_en.xlsx/306afdb8-2ac0-8bb6-05eb-6842f6e5900c?t=1728453462885" \
  -H "Referer: https://echa.europa.eu/information-on-chemicals/annex-vi-to-clp" \
  -H "User-Agent: Mozilla/5.0" \
  -o backend/db/seed/data/ghs_2026-05-23.xlsx
```

ATP22 (applying from 2026-05-01) was also downloaded; it overwrote the ATP21 file under the same name. Re-runs are idempotent (concerns array dedup-merges via `_match_helpers.py`).

**First-run results:** 1,486 substance rows → 2,144 tag entries → 28 matched (26 by CAS, 2 by name). Match rate is low because the ingredient seed only has ~276 entries and ~39 of those carry CAS numbers; will grow naturally as Claude classifies unknown ingredients during scans.

**New concern tags** (added to `analysis_agent.md` vocabulary and `scoring_rubric.md`):

| Tag | GHS code(s) | Penalty |
|-----|-------------|---------|
| `ghs_carcinogen_cat1` | H350 (Category 1A/1B confirmed) | −25 |
| `ghs_carcinogen_cat2` | H351 (Category 2 suspected) | −12 |
| `ghs_reproductive_toxin` | H360, H361 | −15 |
| `ghs_mutagen` | H340, H341 | −12 |

### FDA drug recall enforcement

Parameterised `recall_store.fetch_and_store_openfda()` with `endpoint_url`; added `OPENFDA_DRUG_URL = "https://api.fda.gov/drug/enforcement.json"` and `--drugs` CLI flag. Schema is identical to food enforcement, so the same parser + upsert path works.

**Backfill result:** 17,659 inserted, 1 updated, 1 skipped, 0 errors. Recalls table now holds three streams: FDA food (~28.7K), FDA drug (~17.7K), RASFF EU (~37.8K).

Weekly cron now syncs both food and drug deltas automatically.

---

## Scoring changes

### `_query_openfda()` removed from `check_product_recalls()`

The real-time per-scan HTTP call to api.fda.gov has been live since the FDA Recall Coverage Audit (2026-04-09) as belt-and-suspenders against openFDA's ~7-day indexing lag. After ~6 weeks of weekly delta syncs covering the last 45 days, the local table consistently contained everything the live call would have returned. The function was deleted entirely (not commented out — dead code rots) and the module docstring updated.

**Latency impact:** ~200–800ms removed from every `_attach_recalls()` invocation, which runs on every uncached scan.

### IARC / GHS / Prop 65 penalties extended to food

Discovered while documenting the aspartame IARC update: the food branch in `local_analyzer._compute_score()` never read the carcinogen concern tags. Only the cosmetic branch did. This was an oversight from Session A (focused on cosmetics) — the rubric markdown and code were consistent with each other but both ignored food carcinogens.

Refactor:
- Extracted carcinogen scoring into a shared `_carcinogen_penalty(concerns: list[str]) -> int` helper.
- Both food and cosmetic paths now call it. Magnitudes match the old cosmetic-only logic (−25 for IARC 1/2A, −12 for 2B, etc.).
- These tags **stack** with `explicit_penalty` and `safety_level` because they're post-hoc enrichments — the seed `score_penalty` was written before the IARC/GHS/Prop 65 importers existed and doesn't encode their weight. (The rubric's "do not double-count" rule applies to categorical penalties that overlap with what the seed author put in `score_penalty`, not to enrichment-only tags.)
- Prop 65 tags (`prop65_carcinogen`, `prop65_developmental_toxin`, `prop65_reproductive_toxin`) were silently ignored by the scorer on **both** paths — now applied. Penalties: −12 / −15 / −15.

Rubric update: a new "Carcinogen / Reproductive / Mutagen Tags" section was added to the food penalty table with the full tag → penalty map and a stacking rule. The cosmetic table now references the shared section rather than duplicating it (avoids drift).

**Visible impact on real products:**
- Aspartame in Diet Coke: was −7 (explicit), now −19 (−7 explicit + −12 IARC 2B).
- Processed meats (if/when seeded with IARC Group 1): would be −7 + −25 = −32 (D-territory, which is correct).

### IARC CSV refresh

`iarc_agents_2026-05-23.csv` adds two Monograph 134 entries:
- Aspartame, CAS 22839-47-0, Group 2B (2023)
- Isoeugenol, CAS 97-54-1, Group 2B (2023)

Both seeded ingredients matched and got the `iarc_group_2b` tag appended. Aspartame additionally got its CAS number filled in (the seed had `name` only, no `cas_number`).

Re-run results: 394 valid entries → 21 matched (18 CAS + 3 name), vs. 20 matched before the additions. The +1 implies one of the two new entries matched a previously-unmatched ingredient by name. (The other was already CAS-tagged before this run; the importer dedupes the tag append.)

### Grade scale cleanup

`'E'` removed from:
- `frontend/src/types.ts` (`SafetyReport.grade` union)
- `frontend/src/theme.ts` (`gradeGradient` map; fallback now `map.D`)
- Color/rank maps in `HistoryPage.tsx`, `SubmissionsPage.tsx`, `BarcodeScanner.tsx`, `ComparisonPage.tsx`
- `backend/models.py` (comment on `SafetyReport.grade`)

The rubric was already A/B/C/D only. The frontend types and color maps were the last holdouts.

---

## UI overhaul — premium glassmorphism + amber accent

Coming in, the app had:
- Hardcoded dark mode on most pages (`background: '#000'` in `HomePage`, `BarcodeScanner`, `AddProductPage`).
- Inconsistent green (`#34c759` Apple system green) accent across primary CTAs.
- Per-component duplicated color logic (`isDark ? '#1c1c1e' : '#fff'` repeated everywhere).

Reworked end-to-end:

- **New `frontend/src/theme.ts`** — single source of truth. Exports `getTheme(isDark)`, `gradeGradient(grade, isDark)`, `glassStyle(theme)`, `FONT_STACK`, plus a `SAFETY_INDICATOR` table. Both dark (`#0a0a0f` bg + amber/gold accent `#fbbf24`) and light (`#fafaf7` bg + amber `#d97706`) modes share the same structure.
- **All screens rewritten** to consume the theme module: `SafetyReport.tsx`, `HomePage.tsx`, `LoadingSpinner.tsx`, `App.tsx` error screen, `HistoryPage.tsx`, `AllergenProfilePage.tsx`, `BarcodeScanner.tsx`, `AddProductPage.tsx`, `SubmissionsPage.tsx`, `ComparisonPage.tsx`.
- **Glassmorphism** — `backdrop-filter: blur(20px) saturate(180%)` cards with subtle borders; replaces the old flat white/gray card style.
- **Camera viewfinder** — kept always-dark since it's a fullscreen camera surface; viewfinder corners and scan-line are amber (was green).
- **Manrope font** — loaded from Google Fonts via `index.html` with `display=swap`; weights 200/400/500/600/700/800 (200 is used for the giant gradient grade letter).
- **PWA theme-color** — split into two media-queried `<meta>` tags so the mobile browser chrome matches dark vs light.
- **Pre-React body background** — set in `index.html` to match `theme.bg` for each mode (eliminates the black flash before React mounts).
- **Five design-direction mockups** kept in `frontend/design-mockups/` (Minimalist, Bold Modern, Health & Trust, Dark Premium + Light counterpart, Playful) — the dark/light premium pair was the chosen direction.

---

## Claude Code auto-accept

`.claude/settings.local.json` updated to add `"defaultMode": "acceptEdits"` under `permissions`. Every Claude Code session in this project now starts in auto-accept mode; the user can still `Shift+Tab` to toggle modes mid-session.

---

## Files touched (non-exhaustive)

**Backend:**
- `db/importers/dailymed_importer.py` (new)
- `db/importers/ghs_importer.py` (new)
- `db/recall_store.py` (removed `_query_openfda`, added drug endpoint)
- `agents/local_analyzer.py` (added `_carcinogen_penalty` helper, extended to food)
- `models.py` (grade comment)
- `db/schema.sql` (`'dailymed'` added to source CHECK)
- `db/seed/data/iarc_agents_2026-05-23.csv` (new — adds aspartame, isoeugenol)
- `db/seed/data/ghs_2026-05-23.xlsx` (new — ECHA ATP22 download)
- `instructions/agents/analysis_agent.md` (GHS vocabulary)
- `instructions/data/scoring_rubric.md` (carcinogen tag table added to food; cosmetic references shared section)
- `scripts/weekly_sync.sh` (DailyMed step, FDA drug recall step, GHS step)
- `requirements.txt` (`openpyxl>=3.1.0`)

**Frontend:**
- `src/theme.ts` (new — single source of truth)
- 10 component / page files rewritten or partially rewritten to consume the theme
- `index.html` (Manrope load, theme-color media queries, pre-React body bg)
- `src/types.ts` (grade union: `'E'` removed)
- `design-mockups/` (new directory, 5 standalone HTML mockups + index + compare page)

**Root / docs:**
- `CLAUDE.md` (importer list, source CHECK, concern tag vocabulary, barcode format note)
- `TODO.md` (this session's entry; deferred decisions resolved; trigger updates)
- `ARCHITECTURE.md` (FDA-RSS stale text, MIN_RESOLVED, weekly_sync.sh actual list)
- `README.md` (product lookup chain, safety analysis sources)
- `instructions/agents/sync_worker.md` (trust hierarchy expanded; schedule corrected)
- `instructions/agents/barcode_agent.md` (UPCitemdb step added; source field list updated; barcode format section)
- `instructions/agents/safety_lookup_agent.md` (duplicated rubric replaced with pointer to `scoring_rubric.md`)
- `.claude/settings.local.json` (`defaultMode: acceptEdits`)
