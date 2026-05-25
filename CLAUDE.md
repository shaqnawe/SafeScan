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

# DailyMed Rx prescription drug labels (uses same openFDA manifest; Rx-only, NDC-11 barcodes)
python -m db.importers.dailymed_importer

# IARC Monographs — enrich ingredients table with carcinogen group tags
# (reads db/seed/data/iarc_agents_*.csv — no download needed)
python -m db.importers.iarc_importer

# California Prop 65 — enrich ingredients table with Prop 65 concern tags
# (reads db/seed/data/prop65_list_*.csv — no download needed)
python -m db.importers.prop65_importer

# ECHA Annex VI CLP / GHS hazard classification — enrich ingredients with GHS concern tags
# (reads db/seed/data/ghs_*.xlsx — download from echa.europa.eu/information-on-chemicals/annex-vi-to-clp)
python -m db.importers.ghs_importer

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
- **Frontend**: React + TypeScript + Vite, `react-zxing` for camera barcode scanning, `lucide-react` for UI icons, Manrope (body) + Fraunces (display, hero typography only) from Google Fonts
- **AI**: Claude Opus 4.6 (heavy analysis) + Sonnet 4.6 (extraction/classification) with adaptive thinking
- **DB**: PostgreSQL with 6 tables: `products`, `product_ingredients`, `ingredients`, `ingredient_aliases`, `safety_reports`, `user_submissions`, `recalls`
- **Ingredient seed**: ~276 curated entries across 4 JSON files in `backend/db/seed/data/` — see `backend/db/seed/README.md`

### Analysis pipeline (three paths)

When `POST /api/scan` is called with a barcode:

1. **Cache hit** → `safety_reports` table (7-day TTL) — instant return
2. **Local fast path** → `agents/local_analyzer.py` — pure Python scoring from DB data, zero Claude calls. Used when the product is in the local DB *with a rich source* (not UPCitemdb-cached). Falls back to Claude if `resolved_ingredients` is empty.
3. **Claude path** (two phases):
   - **Phase 1** (tool use loop): `MODEL_LIGHT` (Sonnet 4.6) calls `lookup_product` tool. Uses `thinking={"type": "adaptive", "display": "omitted"}` — thinking runs but content is stripped from the response, preventing large blocks from bloating the Phase 2 round-trip.
   - **Phase 2** (synthesis): `MODEL_HEAVY` (Opus 4.6) via `client.messages.stream()` with `thinking={"type": "adaptive"}` + a JSON-only response instruction. Text chunks are joined, markdown fences stripped, then `json.loads()` + `SafetyReport(**data)` validation. Streaming is required: a non-streaming `create()` call with the full 33K-char system prompt + any non-trivial tool_result gets killed by an upstream ~60s load-balancer timeout. Streaming keeps the connection alive via continuous token flow. Root cause was bisected in Session I-extended; `messages.parse()` was tried earlier and abandoned for unrelated serialization issues.

### `lookup_product` priority order (`scanner.py`)

Phase 1's tool. Highest-fidelity first; later steps fire only on miss:

1. **Local DB, rich source** (off / obf / usda / openfda / dailymed) — curated ingredient data already resolved against `ingredients` table. UPCitemdb-cached rows do **not** count here — they have only name+brand.
2. **`user_submissions` with parsed ingredients** — a photo upload that produced a real ingredient list. Preferred over UPCitemdb's name-only data and worth checking before the live external APIs.
3. **Open Food Facts API** (food).
4. **Open Beauty Facts API** (cosmetic).
5. **UPCitemdb live fetch** (writes to local with `db_source='upcitemdb'`).
6. **`user_submissions` name+brand only** (extraction may have failed on the ingredient list but the product identity is still useful).
7. **UPCitemdb-cached local row** (held from step 1; last resort before `not_found`).

Refactor in Session I-extended (2026-05-24) — previously a `user_submission` with 42 parsed ingredients would lose to a UPCitemdb cached row from a prior scan, producing a useless "no ingredient list available" report.

### Phase 2 disconnect bug (resolved Session I-extended, 2026-05-24)

**Symptom:** `analyze_product()`'s Phase 2 call hung ~60s (or longer with client-side retries) and surfaced `APIConnectionError` / `httpx.RemoteProtocolError: Server disconnected without sending a response` for any scan where `lookup_product` returned a tool_result with non-trivial ingredient data. UPCitemdb-only scans still succeeded.

**Root cause** (bisected with `backend/scratch/repro_phase2.py`): an upstream ~60s load-balancer timeout, NOT model behavior. The non-streaming `messages.create()` call holds the connection idle while Opus generates 5K+ tokens of structured output; with the full 33K-char system prompt + a non-trivial message payload, total time-to-first-byte exceeds 60s and the LB closes the connection. Ruled out by the bisection: thinking on/off (same failure with `thinking=None`), Opus vs Sonnet (Sonnet failed identically), the synthetic preflight `tool_use` seed block (inlining failed identically), interleaved-thinking validation, `redacted_thinking` leak, wire-format alternation. The trigger was strictly combined-input-size — shrinking either the system prompt or the tool_result let baseline succeed.

**Fix:** switched Phase 2 to `client.messages.stream()`. Continuous token flow keeps the connection alive past the 60s LB cutoff. Verified on the failing body wash payload: passes in ~97s, returns a complete grade A report. Diagnostic harness at `backend/scratch/repro_phase2.py` is kept for regression debugging.

### Ingredient resolution cascade (`db/ingredient_resolver.py`)

Called during local DB lookup to map raw label text to safety data:
1. Exact name match + alias match + E-number match (single batch DB query)
2. FTS via GIN index (`plainto_tsquery`) for fuzzy matches
3. Claude classification for unknowns (opt-in only via `use_claude=True`, capped at 10/call) — writes results back to `ingredients` + `ingredient_aliases` for future lookups

### Key design decisions

**Barcode format**: US phones scan 12-digit UPC-A; the DB stores 13-digit EAN-13. Scanner always tries both: `ean13 = barcode.zfill(13) if len(barcode) == 12 else None`. All food/cosmetic importers normalize to EAN-13. Prescription drug boxes use Code 128 barcodes encoding NDC-11 (11 digits); `dailymed_importer.py` stores these as 11-digit strings. The scanner's existing `get_product_from_db(barcode)` exact-match handles NDC-11 natively — no extra lookup step needed.

**Async client**: Use `anthropic.AsyncAnthropic()` throughout. Never use the sync `anthropic.Anthropic()` client in async FastAPI handlers — it causes `httpx.RemoteProtocolError`. The one exception is `ingredient_resolver.py:_classify_with_claude` which uses the sync client intentionally (called from a background context).

**Phase 1 thinking**: Uses `thinking={"type": "adaptive", "display": "omitted"}` — this lets Claude reason during lookup without including thinking content in the response. Never remove `display: "omitted"` or change it to the default; full thinking content in Phase 1 bloats the conversation and causes Phase 2 to drop the connection.

**Model routing**: `MODEL_HEAVY = "claude-opus-4-6"` for Phase 2 safety analysis only. `MODEL_LIGHT = "claude-sonnet-4-6"` for Phase 1 tool loop, image extraction, ingredient parsing, and ingredient classification. Constants are defined at the top of each agent file.

**Prompt caching**: All system prompts are passed as `[{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}]` rather than plain strings. This caches the prompt for 5 minutes, saving input tokens on repeated scans. The system prompts are large (loaded from `backend/instructions/`) so this is high-value.

**Grade scale**: A/B/C/D only — there is no "E" grade. The fallback `SafetyReport` in `scanner.py` uses `grade="D"`. The Phase 2 prompt says "A/B/C/D" not "A/B/C/D/E".

**CAS number column**: `ingredients.cas_number TEXT` (nullable) added in Session A. Indexed via `idx_ingredients_cas` (partial). Used by IARC and Prop 65 importers for preferred-path matching.

**Concern tag vocabulary**: Canonical tags are defined in `backend/instructions/agents/analysis_agent.md` under "Concern Tag Vocabulary". IARC-specific tags: `iarc_group_1` (−25 pts), `iarc_group_2a` (−25 pts), `iarc_group_2b` (−12 pts). Prop 65 tags: `prop65_carcinogen`, `prop65_developmental_toxin`, `prop65_reproductive_toxin`. ECHA Annex VI CLP / GHS tags: `ghs_carcinogen_cat1` (−25 pts, H350), `ghs_carcinogen_cat2` (−12 pts, H351), `ghs_reproductive_toxin` (−15 pts, H360/H361), `ghs_mutagen` (−12 pts, H340/H341). (Originally scoped against EPA CompTox; pivoted to ECHA Annex VI in Session H — see that session log for why.) The legacy `carcinogen` tag is equivalent to `iarc_group_2b` and retained for backwards compatibility. `local_analyzer.py` checks all of these.

**Ingredient enrichment importers**: `iarc_importer.py`, `prop65_importer.py`, and `ghs_importer.py` are update-only — they never insert new rows. They append to `concerns` and `sources` arrays using a dedup merge (`ARRAY(SELECT DISTINCT unnest(...))`). They never touch `safety_level`, `eu_status`, or `score_penalty`. Shared logic in `db/importers/_match_helpers.py`. After adding new seed entries (especially with CAS numbers), re-run all three enrichment importers.

**Ingredient seed files**: `db/seed/data/e_numbers.json` (187 EU additives), `cosing_flagged.json` (59 cosmetic), `food_flagged.json` (15 food contaminants), `fragrance_allergens_flagged.json` (15 EU fragrance allergens). Total ~276 entries. `ingredient_type` CHECK allows: `'food_additive'`, `'cosmetic'`, `'food'`, `'both'`.

**UPCitemdb fallback**: `backend/agents/fetchers/upcitemdb.py` — called at runtime from `lookup_product()` as Step 4, after OFF and OBF miss. Uses the trial endpoint (`https://api.upcitemdb.com/prod/trial/lookup`) — no API key required, rate-limited to 100 lookups/day per IP by UPCitemdb. Returns name + brand + category only; **no ingredient data**. On hit, the product is upserted into the `products` table (`source='upcitemdb'`) so subsequent scans hit the local DB cache. Products upserted from UPCitemdb always go through Claude for analysis (never the local fast path) because `db_source='upcitemdb'` signals zero ingredient data — the local scorer would produce a misleadingly high score.

**Phase 1 message serialization**: Before calling `messages.parse()` in Phase 2, all SDK `ContentBlock` objects in the Phase 1 message history are converted to plain dicts via `_to_dict()`. Passing SDK objects directly causes `RemoteProtocolError: Server disconnected without sending a response` on certain payloads (Anthropic serializes them inconsistently in `messages.parse()` vs `messages.create()`). Also: empty assistant messages (content `[]`) are never appended — they occur when `max_tokens` is hit during adaptive thinking before any visible block is produced, and the API rejects them at the protocol level.

**Product type constraints**: `products.product_type` CHECK constraint allows: `'food'`, `'cosmetic'`, `'unknown'`, `'drug'`. `products.source` CHECK allows: `'off'`, `'obf'`, `'user'`, `'image_scan'`, `'usda'`, `'openfda'`, `'upcitemdb'`, `'dailymed'`.

**Duplicate ingredient prevention**: `product_ingredients` has a unique index on `(product_id, position)`. All importers use `ON CONFLICT (product_id, position) DO NOTHING`.

**Partial unique index requirement for `ON CONFLICT ... WHERE`**: PostgreSQL requires a matching partial unique index for any `ON CONFLICT (col) WHERE predicate` upsert clause — and it checks this at **planning time**, regardless of the actual values being inserted. Without the matching index, the query fails with `InvalidColumnReferenceError: there is no unique or exclusion constraint matching the ON CONFLICT specification`. This was a silent bug for `user_submissions` until Session I — `_save_submission`'s blanket `try/except` swallowed the error, and every barcode photo submission appeared to succeed but never persisted. Fix: `CREATE UNIQUE INDEX user_submissions_barcode_unique ON user_submissions(barcode) WHERE barcode IS NOT NULL` (partial so NULL-barcode anonymous submissions can repeat). When adding any new upsert with a `WHERE` clause, verify a matching partial unique index exists in `schema.sql` AND in the live DB.

### Agent system prompts

System prompts are loaded from `backend/instructions/` at module import time (not per-request). Restart the backend after editing any instruction file.

Files used at runtime:
- `backend/instructions/agents/analysis_agent.md` — safety analysis persona, confidence calibration, output format compliance rules
- `backend/instructions/data/scoring_rubric.md` — A/B/C/D grade thresholds (no "E"), penalty/bonus tables, score algorithm
- `backend/instructions/data/eu_regulations.md` — EU cosmetics/food regulatory context
- `backend/instructions/agents/image_agent.md` — product photo extraction, OCR challenge guidance
- `backend/instructions/agents/ingredient_parser.md` — ingredient list parsing, INCI normalization rules

Not used at runtime (reference only):
- `backend/instructions/agents/barcode_agent.md` — documents the lookup priority and timeout policy
- `backend/instructions/agents/safety_lookup_agent.md` — documents the resolution cascade
- `backend/instructions/agents/sync_worker.md` — documents the weekly sync worker

### Frontend state

- **Scan history**: `useScanHistory` hook, stored in localStorage (max 20 items)
- **Allergen profile**: `useAllergenProfile` hook, stored in localStorage
- **Theme mode** (system / light / dark): `useDarkMode.tsx` exports `ThemeProvider` (mounted once in `main.tsx`) and `useTheme()` context hook. Persisted to localStorage under `safescan:theme-mode`. `'system'` follows OS `prefers-color-scheme` live. `<ThemeToggle />` component (pill + icon variants) drops into any page header without prop-drilling.
- **Motion**: `src/motion.css` provides `.fade-up`, `.stagger-1..7`, `.lift`, `.press` utility classes. Globally imported in `main.tsx`. Respects `prefers-reduced-motion`.
- **Display typography**: `FONT_DISPLAY` (Fraunces variable) exported from `theme.ts` — reserved for the wordmark and grade letter ONLY. Page titles stay Manrope. Don't dilute by applying Fraunces elsewhere.
- **API base URL**: `VITE_API_URL` env var, defaults to `http://localhost:8000`. The committed `.env.local` points to the Railway production URL.

### Photo submission flow

`POST /api/submit-product` (multipart) → `validate_and_normalize_image()` per upload at the endpoint boundary → `image_agent.process_product_photos()` → saves to `user_submissions` → triggers `analyze_submission_bg()` as a FastAPI `BackgroundTask`. The background task calls `analyze_product()` which follows the same 3-path pipeline above, using the `user_submissions` table as a final fallback in `lookup_product()`.

**Image validation at the boundary** (`image_agent.validate_and_normalize_image`): sniffs magic bytes (the client's `content_type` is ignored — file header is authoritative) and rejects anything that isn't JPEG/PNG/GIF/WEBP with a clean HTTP 400. Anything over 3.5MB raw (safe ceiling under Anthropic's 5MB base64 limit) is downsized via Pillow — thumbnail to 2048px longest side (preserves OCR-readable text), JPEG re-encode at quality 85→75→65→55 until under budget.

**Image agent vision calls**: `_extract_product_info()` and `_parse_ingredients()` run **concurrently** via `asyncio.create_task` (`process_product_photos` awaits each task; both are already running). Each uses `client.messages.parse(..., output_format=PydanticClass)` with `timeout=60.0` and `max_tokens=4096`. **Do not enable `thinking`** on these calls — they're pure structured extraction (OCR + JSON emission, no reasoning needed) and adaptive thinking competes with the output for the token budget. On a 50-ingredient INCI label with thinking on, Claude generates partial JSON that pydantic rejects with `ValidationError: EOF while parsing a string at line 1 column 4073`. See Session J log for the debugging cycle. The retry helper `_call_anthropic_with_retry()` catches `RateLimitError`, `APITimeoutError` (with one 1s-backoff retry), `APIError`, and a broad `Exception` clause for `pydantic.ValidationError` — without that last clause, any truncated structured output bubbles to FastAPI as HTTP 500 instead of landing as `ingredients_status='failed'`. The parser is fed `product_type_hint` from the API caller rather than the extractor's `product_type` — this is what enables parallelism. Trade-off accepted: small accuracy edge case (when `product_type_hint='unknown'` AND the extractor would have inferred a better value) for ~2× wall-clock speedup.

**Submission result status**: `SubmissionResult` carries `product_status` and `ingredients_status` of type `CallStatus = 'ok' | 'failed' | 'not_attempted'`. The orchestrator translates a `None` return from either helper into `'failed'`; `'not_attempted'` means no photo was uploaded for that side. Both surface in `GET /api/submissions` for the SubmissionsPage to render an "extraction issue" badge, and on `AddProductPage`'s done view as a red warning card (with the auto-redirect-to-Submissions suppressed so the user actually sees the warning).

### Recall checking

Every `SafetyReport` gets recalls attached via `_attach_recalls()` after analysis. Sources checked:
1. Local `recalls` table (FTS query on title + description)
2. Local `recalls` table (barcode literal ILIKE search)

(The real-time per-scan openFDA call was removed in Session H — the weekly 45-day delta sync covers the openFDA ~7-day indexing lag, making the per-scan HTTP call redundant. Eliminated ~200–800ms per uncached scan.)

The `recalls` table is populated from two sources and has a `source` column to distinguish them:
- **FDA** (`source='fda'`): openFDA food enforcement API — ~28.7K records from 2012 to present, full `classification` → `risk_level` mapping (Class I=serious, Class II=high). Managed by `db/recall_store.py`. Weekly delta sync covers the last 45 days. One-time full backfill: `python -m db.recall_store --backfill`. **The FDA RSS feed was retired** — it only exposed a rolling ~20-item window with no risk classification and wrong category labels for non-food entries (medical devices labeled "food").
- **RASFF** (`source='rasff'`): EU Rapid Alert System for Food and Feed — EC DG SANTE Datalake API (`api.datalake.sante.service.ec.europa.eu`), no API key required. ~37.8K entries covering 2020–present. Managed by `db/rasff_store.py`. Full re-pagination each weekly sync (~531 pages, ~30s) because the API date filter is broken server-side.

**FDA recall coverage note**: The 28.7K openFDA food records are brand+lot specific (e.g. "Trader Joe's Vegetable Fried Rice, net wt. 1lb per bag, UPC 00617571…"). FTS match rate on a typical scan is ~5–15% (most matches are for brands with known recall histories). Class I (serious/life-threatening) and Class II (high/likely harm) are the only classifications in the dataset — no Class III records appear in food/enforcement.

**weekly_sync.sh order**: OFF → OBF → USDA → OpenFDA → DailyMed → FDA food recalls → FDA drug recalls → RASFF recalls → IARC → Prop 65 → ECHA GHS.
