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

# All of the above + FDA recall sync (runs via launchd weekly)
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

### Analysis pipeline (three paths)

When `POST /api/scan` is called with a barcode:

1. **Cache hit** → `safety_reports` table (7-day TTL) — instant return
2. **Local fast path** → `agents/local_analyzer.py` — pure Python scoring from DB data, zero Claude calls. Used when the product is in the local DB. Falls back to Claude if `resolved_ingredients` is empty.
3. **Claude path** (two phases):
   - **Phase 1** (tool use loop): `MODEL_LIGHT` (Sonnet 4.6) calls `lookup_product` tool → fetches from local DB, then Open Food Facts API, then Open Beauty Facts API, then `user_submissions` fallback. Uses `thinking={"type": "adaptive", "display": "omitted"}` — thinking runs but content is stripped from the response, preventing large blocks from bloating the Phase 2 round-trip.
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

**Product type constraints**: `products.product_type` CHECK constraint allows: `'food'`, `'cosmetic'`, `'unknown'`, `'drug'`. `products.source` CHECK allows: `'off'`, `'obf'`, `'user'`, `'image_scan'`, `'usda'`, `'openfda'`.

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
