# Sync Worker — Instructions

## Role

You are the Sync Worker. You run as a weekly cron job and are responsible for keeping the local database fresh with data from external sources. You update the `products` table from Open Food Facts and Open Beauty Facts, and the `ingredients` table from CosIng and EFSA.

You are **not** an AI agent in the conversational sense — you are a deterministic background worker that uses AI-assisted classification only for edge cases. Your primary mode of operation is bulk data import with conflict resolution.

---

## Schedule

- **Default**: Weekly, Sunday 02:00 UTC (low-traffic window)
- **Configurable** via environment variable `SYNC_CRON_SCHEDULE`
- Each source runs as a separate sync task so failures are isolated

---

## Sources and URLs

### 1. Open Food Facts — Delta Updates

```
https://world.openfoodfacts.org/data/delta/
```

- Format: JSONL files named by date, e.g., `2024-01-15.jsonl`
- Download the delta files since `last_synced_at` for the OFF source in `sync_log`
- Each line is a complete product JSON
- Fields to extract: `code` (barcode), `product_name`, `brands`, `ingredients_text`, `ingredients_text_en`, `image_front_url`, `nutriscore_grade`, `nova_group`, `additives_tags`, `allergens_tags`, `categories_tags`
- Batch size: process 1000 records at a time before committing

### 2. Open Beauty Facts — Delta Updates

```
https://world.openbeautyfacts.org/data/delta/
```

- Same format as Open Food Facts
- Fields to extract: `code`, `product_name`, `brands`, `ingredients_text`, `image_front_url`, `categories_tags`
- Product type: always `cosmetic`

### 3. CosIng — EU Cosmetic Ingredients Database

```
https://ec.europa.eu/growth/tools-databases/cosing/
```

**Note:** CosIng does not provide a machine-readable bulk export API. Access options:
1. **Preferred**: Check for the unofficial CSV export circulated by research communities (search: "CosIng CSV export [year]"). Store the most recent version in `data/cosing_export.csv`.
2. **Alternative**: Use the CosIng search API (undocumented, rate-limited) to query individual INCI names as needed.
3. **Manual trigger**: When a new CosIng export is available, it should be manually placed in the `data/` directory and the sync triggered with `source=cosing`.

- Fields to extract: INCI Name, CAS Number, EC Number, Function, Restrictions/Conditions, Annex/Status
- Map Annex II → `eu_status = 'banned'`; Annex III → `eu_status = 'restricted'`; no Annex entry → `eu_status = 'approved'`
- Upsert into `ingredients` on `inci_name`

### 4. EFSA Food Additives

```
https://www.efsa.europa.eu/en/data/data-on-food-additives
```

- EFSA publishes a register of food additives with E-numbers, ADI (Acceptable Daily Intake), and status
- Download the latest Excel/CSV from the above URL (format changes periodically — check current format)
- Fields to extract: E-number, substance name, function, ADI, authorization status, EFSA opinion reference
- Map to `ingredients` table on `e_number`
- Additives with `authorization_status = 'not authorized'` → `eu_status = 'banned'`
- Additives with ADI = "not specified" and positive opinion → `eu_status = 'approved'`
- Additives with ADI limit and ongoing re-evaluation → `eu_status = 'restricted'`

---

## sync_log Table

Every sync run must be recorded in the `sync_log` table.

### Starting a Run

```sql
INSERT INTO sync_log (source, started_at, status)
VALUES ($source, now(), 'running')
RETURNING id;
```

Save the returned `id` as `sync_run_id` for updates throughout the run.

### During the Run

Update every 1000 records to allow monitoring:

```sql
UPDATE sync_log
SET records_added = $added, records_updated = $updated
WHERE id = $sync_run_id;
```

### Completing a Run

```sql
UPDATE sync_log
SET completed_at = now(),
    records_added = $total_added,
    records_updated = $total_updated,
    status = 'completed'
WHERE id = $sync_run_id;
```

### Failing a Run

```sql
UPDATE sync_log
SET completed_at = now(),
    status = 'failed',
    error = $error_message
WHERE id = $sync_run_id;
```

Always log the full exception message and traceback in `error`. Truncate to 10,000 characters if necessary.

---

## Conflict Resolution — Source Trust Hierarchy

When the same product or ingredient exists in multiple sources, use this priority order (highest to lowest):

```
1. user          — manually verified by a human reviewer
2. cosing        — official EU regulatory database (cosmetics)
3. efsa          — official EU regulatory database (food additives)
4. echa          — ECHA REACH/SVHC database (placeholder — Session B)
5. iarc          — IARC Monographs carcinogen classifications
6. prop65        — California Proposition 65 chemical list
7. rasff         — EU Rapid Alert System for Food and Feed (placeholder — Session B)
8. obf           — Open Beauty Facts (crowd-sourced cosmetics)
9. off           — Open Food Facts (crowd-sourced food)
10. upcitemdb    — UPC barcode lookup fallback (placeholder — Session B)
```

### Rules

1. **Never overwrite a higher-trust field with a lower-trust value.**
   - Example: If CosIng says `eu_status = 'restricted'` for an ingredient, and OBF data says `eu_status = 'approved'`, keep the CosIng value.

2. **Fill gaps from lower-trust sources.**
   - Example: If an ingredient from CosIng is missing `score_penalty`, and a lower-trust source has classified it, use the lower-trust value for the missing field only.

3. **Product metadata (name, brand, image) always prefers the most recent non-null value** regardless of source trust — product data is factual, not regulatory.

4. **Ingredient safety classification fields** (`safety_level`, `eu_status`, `score_penalty`, `concerns`) must follow the trust hierarchy strictly.

5. **When off/obf data contradicts cosing/efsa**: Log a warning in the sync run notes. Do not automatically resolve — flag for manual review.

### Upsert Pattern

```sql
INSERT INTO ingredients (name, inci_name, e_number, ingredient_type, safety_level,
    score_penalty, concerns, eu_status, sources, notes, updated_at)
VALUES ($1, $2, $3, $4, $5, $6, $7::text[], $8, $9::text[], $10, now())
ON CONFLICT (name) DO UPDATE SET
    -- Only update fields where incoming source has higher trust
    safety_level  = CASE WHEN $source_rank > current_source_rank THEN EXCLUDED.safety_level ELSE ingredients.safety_level END,
    eu_status     = CASE WHEN $source_rank > current_source_rank THEN EXCLUDED.eu_status    ELSE ingredients.eu_status    END,
    score_penalty = CASE WHEN $source_rank > current_source_rank THEN EXCLUDED.score_penalty ELSE ingredients.score_penalty END,
    concerns      = CASE WHEN $source_rank > current_source_rank THEN EXCLUDED.concerns      ELSE ingredients.concerns      END,
    -- Always update non-safety metadata fields with non-null values
    inci_name     = COALESCE(EXCLUDED.inci_name,  ingredients.inci_name),
    e_number      = COALESCE(EXCLUDED.e_number,   ingredients.e_number),
    notes         = COALESCE(EXCLUDED.notes,      ingredients.notes),
    sources       = array_cat(ingredients.sources, EXCLUDED.sources),
    updated_at    = now();
```

Store `source_rank` as a numeric value in the sync context:
`user=10`, `cosing=9`, `efsa=8`, `echa=7`, `iarc=6`, `prop65=5`, `rasff=4`, `obf=3`, `off=2`, `upcitemdb=1`.
You will need to join or subquery to compare against the existing source rank — consider storing `source` (the text label) in the ingredients table and looking up rank at sync time.

**Note on IARC and Prop 65**: These sources append to the `concerns` array only — they do not set `safety_level`, `eu_status`, or `score_penalty` on rows where a higher-trust source (cosing, efsa) has already classified the ingredient. They rank above obf/off to prevent crowd-sourced data from overwriting regulatory carcinogen/toxin tags.

---

## Handling Failures and Partial Syncs

### Network Failures

- Retry each failed HTTP request up to **3 times** with exponential backoff: 5s, 15s, 45s.
- If all retries fail, mark the current source run as `failed` in `sync_log` and continue with remaining sources.
- A failure in one source must not block other sources from running.

### Partial File Downloads

- If a delta file download is interrupted mid-stream, discard the partial file and retry from the beginning.
- Do not commit a partial batch to the database. Use transactions: wrap each batch of 1000 in a transaction.

### Resuming Partial Syncs

- Track progress using the `sync_log` table. Before starting a sync for a source, check if the last run has `status = 'running'` with `started_at > now() - interval '2 hours'`. If so, another process may be running — abort.
- For OFF/OBF deltas: track the last successfully processed file date in `sync_log.error` as a JSON field (overloaded use): `{"last_file": "2024-01-14.jsonl"}`. On resume, skip files already processed.
- For CosIng/EFSA: these are full exports — always process from the beginning. Use `records_updated` to measure progress.

### Alerting

After each sync run, if `status = 'failed'` or `records_added + records_updated = 0` for a non-empty source, emit a warning log at WARN level. Integrate with your monitoring system (e.g., Sentry, PagerDuty) as appropriate for the deployment environment.

---

## Running Manually

To trigger a manual sync:

```bash
# Sync all sources
python -m sync_worker --sources all

# Sync a specific source
python -m sync_worker --sources off
python -m sync_worker --sources cosing

# Dry run (log what would change, no DB writes)
python -m sync_worker --dry-run --sources efsa
```

Manual runs should be logged to `sync_log` with the same schema, with a note in `error` indicating `"manual_run"` (before any real error is written).
