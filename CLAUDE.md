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
- **AI**: Claude Opus 4.6 with adaptive thinking (`thinking: {"type": "adaptive"}`)
- **DB**: PostgreSQL with 6 tables: `products`, `product_ingredients`, `ingredients`, `ingredient_aliases`, `safety_reports`, `user_submissions`, `recalls`

### Analysis pipeline (three paths)

When `POST /api/scan` is called with a barcode:

1. **Cache hit** → `safety_reports` table (7-day TTL) — instant return
2. **Local fast path** → `agents/local_analyzer.py` — pure Python scoring from DB data, zero Claude calls. Used when the product is in the local DB. Falls back to Claude if `resolved_ingredients` is empty.
3. **Claude path** (two phases):
   - **Phase 1** (tool use loop): Claude calls `lookup_product` tool → fetches from local DB, then Open Food Facts API, then Open Beauty Facts API, then `user_submissions` fallback. **No thinking in Phase 1** — adding `thinking` here generates large blocks that break Phase 2 round-trip.
   - **Phase 2** (structured output): `client.messages.parse()` with `thinking={"type": "adaptive"}` → returns `SafetyReport` Pydantic model.

### Ingredient resolution cascade (`db/ingredient_resolver.py`)

Called during local DB lookup to map raw label text to safety data:
1. Exact name match + alias match + E-number match (single batch DB query)
2. FTS via GIN index (`plainto_tsquery`) for fuzzy matches
3. Claude classification for unknowns (opt-in only via `use_claude=True`, capped at 10/call) — writes results back to `ingredients` + `ingredient_aliases` for future lookups

### Key design decisions

**Barcode format**: US phones scan 12-digit UPC-A; the DB stores 13-digit EAN-13. Scanner always tries both: `ean13 = barcode.zfill(13) if len(barcode) == 12 else None`. All importers normalize to EAN-13.

**Async client**: Use `anthropic.AsyncAnthropic()` throughout. Never use the sync `anthropic.Anthropic()` client in async FastAPI handlers — it causes `httpx.RemoteProtocolError`. The one exception is `ingredient_resolver.py:_classify_with_claude` which uses the sync client intentionally (called from a background context).

**Phase 1 thinking**: Do NOT add `thinking=` to the Phase 1 `messages.create()` call in `agents/scanner.py`. Adaptive thinking blocks from Phase 1 become large content blocks that, when round-tripped into Phase 2, cause the server to drop the connection.

**Product type constraints**: `products.product_type` CHECK constraint allows: `'food'`, `'cosmetic'`, `'unknown'`, `'drug'`. `products.source` CHECK allows: `'off'`, `'obf'`, `'user'`, `'image_scan'`, `'usda'`, `'openfda'`.

**Duplicate ingredient prevention**: `product_ingredients` has a unique index on `(product_id, position)`. All importers use `ON CONFLICT (product_id, position) DO NOTHING`.

### Agent system prompts

System prompts are loaded from `instructions/` at module import time (not per-request):
- `instructions/agents/analysis_agent.md` — safety analysis persona + rules
- `instructions/data/scoring_rubric.md` — A/B/C/D/E grade thresholds and scoring logic
- `instructions/data/eu_regulations.md` — EU cosmetics/food regulatory context
- `instructions/agents/image_agent.md` — product photo extraction instructions
- `instructions/agents/ingredient_parser.md` — ingredient list parsing instructions

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
