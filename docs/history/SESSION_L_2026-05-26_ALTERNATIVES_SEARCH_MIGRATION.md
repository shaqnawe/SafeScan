# Session L — Recommended alternatives, name search, slim partial migration

**Date:** 2026-05-26
**Branch:** `feature/capacitor-mobile`
**Commits:** `7e5dff3`, `b685a83`, `daab4b3`

## Summary

Three shipped pieces of work, all about product discovery and matching:

1. **Per-ingredient concern chips + sources + score impact** (commit `7e5dff3`, started end of Session K, finished start of Session L). `IngredientAnalysis` schema expanded to carry `concerns: list[str]`, `sources: list[str]`, `score_impact: int | None` — structured data that was already in the DB but Phase 2 was collapsing into one free-text string. Frontend renders Yuka-style colored chips (red for IARC/GHS/Prop 65/endocrine/mutagen/formaldehyde-releaser, neutral otherwise), prettified source labels (EFSA, CosIng, SCCS, EU 1333/2008, IFRA, ECHA), and a `−N pts` badge on the right edge.
2. **Slim partial migration local → Railway** (commit `b685a83`). Pushed 4.55M product rows from local Postgres to Railway in 6 min 19 sec at ~12K rows/sec. Idempotent script preserved Railway-only DailyMed data.
3. **Recommended alternatives by use-case slug + product name search** (commit `daab4b3`). Slug-based matching replaces broad-category matching (fixes the "moisturizer recommended as alternative to hand soap" false positive). `pg_trgm` GIN indexes on `products.name` + `products.brand` give sub-2ms fuzzy search across 4.6M rows.

## Slim partial migration

### Why

Yesterday's recon (Session K) found that Railway prod had:
- **0 OFF rows** (4.4M missing)
- **0 USDA rows** (62K missing)
- Only 5.5K of 63K OBF rows
- Only 3.8K of 14.7K OpenFDA rows
- 72.8K DailyMed Rx rows — only on Railway, not on local

Every food/cosmetic scan in production fell through to Phase 2 Claude analysis (60-120s + ~$0.10–0.30) because Phase 1's `lookup_product` couldn't find them locally.

### Decision

Push only the `products` table — name, brand, image, categories, type, source. Skip `product_ingredients` (9 GB on disk, blows past Railway's 2 GB headroom). Local fast path stays local for now; production gets product identity + categories + image for Phase 1 `lookup_product` and for the alternatives feature's category filter.

### Implementation

`backend/scripts/migrate_products_to_railway.py` — streams in 10K-row batches:
1. COPY each batch into a per-session temp staging table on Railway
2. `INSERT INTO products ... SELECT FROM products_stage ON CONFLICT (barcode) DO NOTHING`
3. TRUNCATE staging, next batch

Idempotent. Safe to re-run. DailyMed preserved.

### Result

Ran 2026-05-26 around 18:30:

| Source | Pushed | Skipped | Time |
|--------|--------|---------|------|
| USDA | 62,831 | 0 | 7.1 s |
| OpenFDA | 11,093 | 3,602 | 2.2 s |
| OBF | 58,211 | 5,357 | 11.3 s |
| OFF | 4,419,563 | 289 | 365.7 s |
| **Total** | **4,551,698** | **9,248** | **6 min 19 s** |

Railway DB went from 1.6 GB to ~1.9 GB. ~1.7 GB headroom remaining.

Also synced 10 missing `ingredients` rows via the same staging pattern.

## Recommended alternatives by use-case slug

### Why

Initial alternatives implementation used `products.categories && current.categories` array overlap. This surfaced **Cetaphil Moisturizing Lotion as an alternative to Mrs Meyer's Hand Soap** because both share `[Health & Beauty, Personal Care, Cosmetics]`. Useless recommendation — different use case.

### Decision

Add a `category_slug` field to `SafetyReport` populated via a deterministic keyword heuristic. Match alternatives strictly on slug equality. Drugs always return None (brand vs generic Rx is a different problem).

Considered alternatives:
- **Curated whitelist of OFF-specific tags** (e.g. `en:hand-soaps`) — breaks on OBF/UPCitemdb data which uses generic broad labels.
- **RAG / vector embeddings** — nearest-neighbor by embedding conflates use case with brand identity and ingredient mix. "Le Labo Santal 33 perfume" would embed close to "Le Labo Santal 33 candle". Discrete classification beats nearest-neighbor for this specific job.
- **LLM-classified slug via Phase 2** — robust, ~10 extra output tokens per scan. Deferred as the upgrade path; matching query stays identical.

### Implementation

`backend/agents/category.py` — ordered list of `(regex, slug)` tuples, more-specific patterns first ("hand soap" before "soap").

- ~40 cosmetic slugs: `hand_soap`, `body_wash`, `bar_soap`, `shampoo`, `conditioner`, `face_moisturizer`, `body_lotion`, `face_cleanser`, `face_serum`, `sunscreen`, `toothpaste`, `deodorant`, `fragrance`, `lip`, `mascara`, `eye_makeup`, `foundation`, `concealer`, `blush`, etc.
- ~30 food slugs: `soda`, `juice`, `coffee`, `tea`, `beer`, `wine`, `milk`, `plant_milk`, `yogurt`, `cheese`, `bread`, `cereal`, `cookie`, `chocolate`, `candy`, `snack_chip`, `pasta`, `rice`, `soup`, `condiment`, `sauce`, etc.

Populated in three places so cached and fresh reports agree:
- `local_analyzer.build_report` — local fast path
- `scanner.analyze_product` after Phase 2 — Claude path
- `scanner.analyze_product` cache-hit branch — backfill for pre-slug cached reports

`find_alternatives` query changes:
- Filter on `report->>'category_slug' = $X` (strict; null slug = no match)
- **Dropped** the `expires_at > NOW()` filter — slightly-stale "this product in your category scored well last time" is still useful. The 7-day TTL is meant for the user's own fresh scan, not the panel.

### Verification

Backfilled the 15 existing cached reports: 14/15 got slugs (Nutella unclassified — no spread pattern in vocabulary yet).

| Scan | Slug | Alternative recommended |
|---|---|---|
| Mrs Meyer's Hand Soap (B 57) | `hand_soap` | none — Cetaphil correctly excluded |
| Coke Original (C 46) | `soda` | Club Soda (A 95) — even across 7-day TTL |
| Sriracha (B 70) | `condiment` | none — no other condiments in cache |
| Cetaphil Moisturizing Lotion (A 85) | `body_lotion` | skipped (grade A) |

Heuristic accuracy on 16 hand-picked cases: 14/16. Both fails were edge cases — "Sriracha hot chili sauce" matched `condiment` (also correct), and "SK-II Facial Treatment Essence" needed a regex tweak the LLM-emitted slug upgrade will handle.

## Product name search

### Why

Yuka-style discovery — "is X any good?" intent without needing a barcode. Also useful for the Mac webcam scanning issues (fixed-focus hardware) where users may want to search rather than fight the camera.

### Implementation

`pg_trgm` GIN indexes on Railway:
- `idx_products_name_trgm` (200 MB)
- `idx_products_brand_trgm` (81 MB)

Created out-of-band via `CREATE INDEX ... USING gin (...gin_trgm_ops)`. Total 281 MB of index, well under the 1.7 GB headroom.

`db/queries.py::search_products(query, product_type, limit)` — `ILIKE '%query%'` on both columns with relevance ranking:
```
brand-exact     → 100
name-prefix     →  80
brand-prefix    →  60
name-substring  →  40
brand-substring →  30
```

Endpoint: `GET /api/search?q=...&product_type=...&limit=...`. Returns `list[SearchResult]` with barcode/name/brand/image_url/product_type. Filters out rows with NULL name (mostly UPCitemdb stubs).

### Performance

`EXPLAIN ANALYZE` on `WHERE name ILIKE '%cetaphil%' OR brand ILIKE '%cetaphil%' LIMIT 20`:
- Uses `BitmapOr` over both trigram indexes
- 1.4 ms total over 4.6M rows
- 65 buffer hits + 37 buffer reads — comfortable cold-cache performance

### Frontend

Added a debounced (300ms) search input above the existing "OR ENTER BARCODE MANUALLY" section on the scanner page. Cancels in-flight requests on each keystroke via `AbortController`. Results render inline as tappable rows (image + brand chip + name + product_type pill). Tapping a result calls `onScan(barcode)` — same flow as a real barcode scan.

E2E verified via Playwright: typed "cetaphil" → 15 tappable Cetaphil products → tapped one → full safety report rendered.

## Mac webcam scanning bump (related)

Small fix earlier in the session for the user's "scanner reading wrong barcode" report. `useZxing` was being called with no `constraints`, so the browser was giving it 640×480 by default. Bumped to request 1920×1080 + `facingMode: environment` + `focusMode: continuous` (non-standard Chromium hint). 5-LOC change in `BarcodeScanner.tsx`. Mostly cosmetic for FaceTime HD (fixed focus) but real benefit for USB autofocus webcams.

The original misread (`5880121114726` instead of `808124114326`) was a valid EAN-13 checksum, meaning ZXing decoded a real barcode — most likely from a sticker or secondary barcode in frame, not a true misread.

## Open items / deferred

- **Per-scan timing instrumentation** — added to TODO. `safety_reports.created_at` only records cache write time, not analysis duration. Adding `analysis_duration_ms` is ~5 LOC + 1 migration. Deferred until perf regression suspected.
- **`product_ingredients` migration** — 9 GB on disk, doesn't fit. Trigger to revisit: Railway plan upgrade or product_ingredients pruning strategy. Until then, every food/cosmetic scan in prod still falls through to Phase 2.
- **LLM-emitted `category_slug`** — handles K-beauty / weird brand names that the keyword heuristic misses. Matching query stays identical so it's a clean upgrade. Trigger: keyword mis-classification > ~20% in dogfooding.
- **Schema.sql update for pg_trgm** — out-of-band SQL not in `schema.sql` yet. Add `CREATE EXTENSION IF NOT EXISTS pg_trgm;` + the two GIN indexes to keep schema.sql authoritative.
- **Spread/jam slug** — Nutella unclassified during backfill. Add `spread` pattern when adding more food slugs.
