# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt
# Requires DATABASE_URL and ANTHROPIC_API_KEY in backend/.env (see .env.example)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # dev server at http://localhost:5173
npm run build      # production build
```

For mobile device access, set `VITE_API_URL=http://<local-ip>:8000` in `frontend/.env.local`.

### Database importers (run from `backend/`)

```bash
# Open Food Facts (~2M food products, ~6GB download)
python -m db.importers.off_importer --url

# Open Beauty Facts (~63K cosmetics)
python -m db.importers.obf_importer --url

# USDA FoodData Central (~500K US branded foods, 477MB)
python -m db.importers.usda_importer --url

# OpenFDA OTC drug labels (~17K OTC drugs)
python -m db.importers.openfda_importer

# IARC Monographs — enrich ingredients table with carcinogen group tags
# (reads db/seed/data/iarc_agents_*.csv — no download needed)
python -m db.importers.iarc_importer

# California Prop 65 — enrich ingredients table with Prop 65 concern tags
# (reads db/seed/data/prop65_list_*.csv — no download needed)
python -m db.importers.prop65_importer

# All of the above + FDA recall sync + IARC + Prop 65 (runs via launchd weekly)
bash scripts/weekly_sync.sh
```

### Seed ingredients safety DB

```bash
cd backend
python -m db.seed.seed_ingredients
```

### Clear a cached report (force re-analysis)

```sql
DELETE FROM safety_reports WHERE barcode = '<barcode>';
```

---

## Architecture

### Stack

- **Backend**: FastAPI + asyncpg (PostgreSQL) + `anthropic` SDK (`AsyncAnthropic`)
- **Frontend**: React + TypeScript + Vite, `react-zxing` for camera barcode scanning
- **AI**: Claude Opus 4.6 (heavy analysis) + Sonnet 4.6 (extraction/classification) with adaptive thinking
- **DB**: PostgreSQL with 6 tables: `products`, `product_ingredients`, `ingredients`, `ingredient_aliases`, `safety_reports`, `user_submissions`, `recalls`
- **Ingredient seed**: ~276 curated entries across 4 JSON files in `backend/db/seed/data/` — see `backend/db/seed/README.md`

### Analysis pipeline (three paths)

When `POST /api/scan` is called with a barcode:

1. **Cache hit** → `safety_reports` table (7-day TTL) — instant return
2. **Local fast path** → `agents/local_analyzer.py` — pure Python scoring from DB data, zero Claude calls. Used when the product is in the local DB. Falls back to Claude if `resolved_ingredients` is empty.
3. **Claude path** (two phases):
   - **Phase 1** (tool use loop): `MODEL_LIGHT` (Sonnet 4.6) calls `lookup_product` tool → fetches from local DB, then Open Food Facts API, then Open Beauty Facts API, then **UPCitemdb** (trial, 100/day, no key required), then `user_submissions` fallback. Uses `thinking={"type": "adaptive", "display": "omitted"}` — thinking runs but content is stripped from the response, preventing large blocks from bloating the Phase 2 round-trip.
   - **Phase 2** (structured output): `MODEL_HEAVY` (Opus 4.6) via `client.messages.parse()` with `thinking={"type": "adaptive"}` → returns `SafetyReport` Pydantic model. Wrapped in `try/except anthropic.APIError` with a fallback report.

### Ingredient resolution cascade (`db/ingredient_resolver.py`)

Called during local DB lookup to map raw label text to safety data:
1. Exact name match + alias match + E-number match (single batch DB query)
2. FTS via GIN index (`plainto_tsquery`) for fuzzy matches
3. Claude classification for unknowns (opt-in only via `use_claude=True`, capped at 10/call) — writes results back to `ingredients` + `ingredient_aliases` for future lookups

### Key design decisions

**Barcode format**: US phones scan 12-digit UPC-A; the DB stores 13-digit EAN-13. Scanner always tries both: `ean13 = barcode.zfill(13) if len(barcode) == 12 else None`. All importers normalize to EAN-13.

**Async client**: Use `anthropic.AsyncAnthropic()` throughout. Never use the sync `anthropic.Anthropic()` client in async FastAPI handlers — it causes `httpx.RemoteProtocolError`. The one exception is `ingredient_resolver.py:_classify_with_claude` which uses the sync client intentionally (called from a background context).

**Phase 1 thinking**: Uses `thinking={"type": "adaptive", "display": "omitted"}` — this lets Claude reason during lookup without including thinking content in the response. Never remove `display: "omitted"` or change it to the default; full thinking content in Phase 1 bloats the conversation and causes Phase 2 to drop the connection.

**Model routing**: `MODEL_HEAVY = "claude-opus-4-6"` for Phase 2 safety analysis only. `MODEL_LIGHT = "claude-sonnet-4-6"` for Phase 1 tool loop, image extraction, ingredient parsing, and ingredient classification. Constants are defined at the top of each agent file.

**Prompt caching**: All system prompts are passed as `[{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}]` rather than plain strings. This caches the prompt for 5 minutes, saving input tokens on repeated scans. The system prompts are large (loaded from `instructions/`) so this is high-value.

**Grade scale**: A/B/C/D only — there is no "E" grade. The fallback `SafetyReport` in `scanner.py` uses `grade="D"`. The Phase 2 prompt says "A/B/C/D" not "A/B/C/D/E".

**CAS number column**: `ingredients.cas_number TEXT` (nullable) added in Session A. Indexed via `idx_ingredients_cas` (partial). Used by IARC and Prop 65 importers for preferred-path matching.

**Concern tag vocabulary**: Canonical tags are defined in `instructions/agents/analysis_agent.md` under "Concern Tag Vocabulary". IARC-specific tags: `iarc_group_1` (−25 pts), `iarc_group_2a` (−25 pts), `iarc_group_2b` (−12 pts). Prop 65 tags: `prop65_carcinogen`, `prop65_developmental_toxin`, `prop65_reproductive_toxin`. The legacy `carcinogen` tag is equivalent to `iarc_group_2b` and retained for backwards compatibility. `local_analyzer.py` checks all of these.

**Ingredient enrichment importers**: `iarc_importer.py` and `prop65_importer.py` update-only — they never insert new rows. They append to `concerns` and `sources` arrays using a dedup merge (`ARRAY(SELECT DISTINCT unnest(...))`). They never touch `safety_level`, `eu_status`, or `score_penalty`. Shared logic in `db/importers/_match_helpers.py`. After adding new seed entries (especially with CAS numbers), re-run both importers.

**Ingredient seed files**: `db/seed/data/e_numbers.json` (187 EU additives), `cosing_flagged.json` (59 cosmetic), `food_flagged.json` (15 food contaminants), `fragrance_allergens_flagged.json` (15 EU fragrance allergens). Total ~276 entries. `ingredient_type` CHECK allows: `'food_additive'`, `'cosmetic'`, `'food'`, `'both'`.

**UPCitemdb fallback**: `backend/agents/fetchers/upcitemdb.py` — called at runtime from `lookup_product()` as Step 4, after OFF and OBF miss. Uses the trial endpoint (`https://api.upcitemdb.com/prod/trial/lookup`) — no API key required, rate-limited to 100 lookups/day per IP by UPCitemdb. Returns name + brand + category only; **no ingredient data**. On hit, the product is upserted into the `products` table (`source='upcitemdb'`) so subsequent scans hit the local DB cache. Products upserted from UPCitemdb always go through Claude for analysis (never the local fast path) because `db_source='upcitemdb'` signals zero ingredient data — the local scorer would produce a misleadingly high score.

**Phase 1 message serialization**: Before calling `messages.parse()` in Phase 2, all SDK `ContentBlock` objects in the Phase 1 message history are converted to plain dicts via `_to_dict()`. Passing SDK objects directly causes `RemoteProtocolError: Server disconnected without sending a response` on certain payloads (Anthropic serializes them inconsistently in `messages.parse()` vs `messages.create()`). Also: empty assistant messages (content `[]`) are never appended — they occur when `max_tokens` is hit during adaptive thinking before any visible block is produced, and the API rejects them at the protocol level.

**Product type constraints**: `products.product_type` CHECK constraint allows: `'food'`, `'cosmetic'`, `'unknown'`, `'drug'`. `products.source` CHECK allows: `'off'`, `'obf'`, `'user'`, `'image_scan'`, `'usda'`, `'openfda'`, `'upcitemdb'`.

**Duplicate ingredient prevention**: `product_ingredients` has a unique index on `(product_id, position)`. All importers use `ON CONFLICT (product_id, position) DO NOTHING`.

### Agent system prompts

System prompts are loaded from `instructions/` at module import time (not per-request). Restart the backend after editing any instruction file.

Files used at runtime:
- `instructions/agents/analysis_agent.md` — safety analysis persona, confidence calibration, output format compliance rules
- `instructions/data/scoring_rubric.md` — A/B/C/D grade thresholds (no "E"), penalty/bonus tables, score algorithm
- `instructions/data/eu_regulations.md` — EU cosmetics/food regulatory context
- `instructions/agents/image_agent.md` — product photo extraction, OCR challenge guidance
- `instructions/agents/ingredient_parser.md` — ingredient list parsing, INCI normalization rules

Not used at runtime (reference only):
- `instructions/agents/barcode_agent.md` — documents the lookup priority and timeout policy
- `instructions/agents/safety_lookup_agent.md` — documents the resolution cascade
- `instructions/agents/sync_worker.md` — documents the weekly sync worker

### Frontend state

- **Scan history**: `useScanHistory` hook, stored in localStorage (max 20 items)
- **Allergen profile**: `useAllergenProfile` hook, stored in localStorage
- **API base URL**: `VITE_API_URL` env var, defaults to `http://localhost:8000`

### Photo submission flow

`POST /api/submit-product` (multipart) → `image_agent.process_product_photos()` → saves to `user_submissions` → triggers `analyze_submission_bg()` as a FastAPI `BackgroundTask`. The background task calls `analyze_product()` which follows the same 3-path pipeline above, using the `user_submissions` table as a final fallback in `lookup_product()`.

### Recall checking

Every `SafetyReport` gets recalls attached via `_attach_recalls()` after analysis. Sources checked:
1. Local `recalls` table (FTS query on title + description)
2. Local `recalls` table (barcode literal ILIKE search)
3. Real-time `openFDA` food enforcement API

The `recalls` table is populated from the FDA RSS feed — seeded on startup via `ensure_recalls_table()` and refreshed weekly by `scripts/weekly_sync.sh` or manually via `POST /api/recalls/refresh`.
