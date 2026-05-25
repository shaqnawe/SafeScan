# Session K — production-readiness sweep: cache upsert, CORS, vision benchmarking

**Date:** 2026-05-25 (afternoon, same calendar day as Session J)
**Scope:** Three production-readiness items from the queued list — make `safety_reports` cache a real upsert (bounded growth, no more orphan rows), fix the CORS issue that the Session I dogfooding note flagged for any dev-against-prod workflow, and build a vision-OCR provider benchmark so future Anthropic-vs-OpenAI decisions are data-driven rather than speculative. Closes out the long-standing "open issues" backlog from Sessions I and J with three small, well-scoped commits and one new dev tool.

---

## Goals

Coming in (from the Session J open queue):
1. `safety_reports` upsert + history table — the oldest production-readiness item, kept punted across two sessions.
2. CORS for dev-against-prod workflow — low priority in Session I but pinned here as a quick win.
3. Vision-model benchmarking — now that we have a real Anthropic baseline from Session J (100% on cosmetic INCI), measure whether OpenAI is a viable cheaper alternative.

Picked up along the way:
4. Append-only history table was deferred mid-task (user opted for simpler `updated_at`-only after weighing the tradeoff).
5. CORS root cause turned out to be different from what the Session I dogfooding note hypothesized — worth documenting in case the gotcha bites again.
6. gpt-4o (full) was the surprise loser in benchmarking. Two benchmarks confirmed the pattern.

---

## safety_reports upsert + updated_at (commit `57417a6`)

### Problem

`cache_report()` was a plain `INSERT` despite the misleading `_UPSERT_CACHED_REPORT` variable name. Every re-scan of a barcode within the 7-day TTL window created a new row. The cache lookup ordered by `created_at DESC` so the latest row won, but the table grew unbounded. Pre-migration state on Railway: 12 rows, 2 barcodes with duplicates (3 + 2 = 5 redundant rows).

### Detour: history table vs `updated_at`

Initially planned to build an append-only `safety_reports_history` table for audit trail. User asked the right question ("is there an advantage to append-only?") and after honest weighing of the tradeoff:

| Approach | Pros | Cons |
|---|---|---|
| Overwrite in place + `updated_at` | Simple, bounded, ~15 LOC | Lose prior versions |
| Append-only history table | Audit trail, A/B rubric testing, compliance-ready | Unbounded growth, ~50 LOC |

At dogfooding/pre-MVP scale, no compliance requirement, no rubric A/B planned, no "what did the app say last week" use case. Picked the simpler path. The upsert shape stays compatible — history can be added later via a CTE that snapshots the old row before overwriting. Documented as deferred-with-trigger in TODO.md (revisit if compliance / rubric A/B / "prove what you said" use case appears).

### Migration

Single Railway transaction:

```sql
-- 1. Add updated_at column (backfilled from created_at)
ALTER TABLE safety_reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE safety_reports SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE safety_reports ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE safety_reports ALTER COLUMN updated_at SET NOT NULL;

-- 2. Dedupe: keep newest per barcode
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY barcode ORDER BY created_at DESC) AS rn
    FROM safety_reports
)
DELETE FROM safety_reports WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- 3. Add UNIQUE constraint (required for ON CONFLICT to plan)
ALTER TABLE safety_reports
    ADD CONSTRAINT safety_reports_barcode_unique UNIQUE (barcode);

-- 4. Drop redundant single-column index
DROP INDEX IF EXISTS idx_safety_reports_barcode;
```

Result: 12 → 9 rows on Railway. `safety_reports_pkey`, `safety_reports_barcode_unique`, `idx_safety_reports_expires` are the three indices now.

### Code change

```sql
-- backend/db/queries.py
_UPSERT_CACHED_REPORT = """
INSERT INTO safety_reports (barcode, report, claude_used, expires_at)
VALUES ($1, $2::jsonb, $3, NOW() + INTERVAL '7 days')
ON CONFLICT (barcode) DO UPDATE
SET report      = EXCLUDED.report,
    claude_used = EXCLUDED.claude_used,
    expires_at  = EXCLUDED.expires_at,
    updated_at  = NOW()
"""
```

`created_at` stays put across re-cache (first-cached time preserved). `updated_at` bumps on every overwrite. `expires_at` refreshes for a new 7-day TTL.

### Smoke test

Two `cache_report()` calls on the same test barcode (with 1.2s gap) on Railway:

```
[BEFORE] id=16  claude_used=True   created=21:23:45.93   updated=21:23:45.93
[AFTER ] id=16  claude_used=False  created=21:23:45.93   updated=21:23:47.66
  same id?              True
  created_at unchanged? True
  updated_at bumped?    True
  report overwritten?   True
get_cached_report returns latest payload (grade=B as expected)
```

### Note on FK to products

`safety_reports.barcode TEXT NOT NULL UNIQUE` links to `products.barcode` **by value, not by FK**. Confirmed intentional during this work — cached reports can exist for barcodes that aren't in the `products` table (UPCitemdb-only paths, user_submissions paths). Adding a FK would force every cached barcode into `products` and break the submission flow.

---

## CORS fix (commit `b76730c`)

### What the Session I note said

> CORS on /api/submissions when dev frontend hits Railway. Railway's CORSMiddleware doesn't include 'http://localhost:5173' in allow_origins...

### What was actually wrong

The config was `allow_origins=["*"]` paired with `allow_credentials=True`. The CORS spec **forbids** that combination — browsers silently reject the response with no `Access-Control-Allow-Origin` header. So even though `"*"` *looks* like it should allow everything, the credentials flag invalidates it.

The Session I note hypothesized a missing localhost origin, but the real fix was to drop the wildcard entirely and supply explicit origins. Worth keeping documented because this gotcha is genuinely non-obvious — most CORS docs don't lead with the credentials caveat.

### Fix

```python
# backend/main.py
_DEFAULT_ORIGINS = [
    "http://localhost:5173",        # Vite dev
    "http://localhost:4173",        # Vite preview
    "capacitor://localhost",        # Capacitor iOS WebView
    "https://localhost",            # Capacitor Android WebView
    "https://proactive-harmony-production-2735.up.railway.app",  # Railway prod
]
_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = (
    [o.strip() for o in _origins_env.split(",") if o.strip()]
    if _origins_env
    else _DEFAULT_ORIGINS
)
```

Env-driven so Railway can override for hardening (e.g. drop the localhost dev URLs in prod). Capacitor's WebView origins (`capacitor://localhost`, `https://localhost`) included by default since the iOS app is the primary client.

---

## Vision-OCR provider benchmark (commits `92ce8fa`, `0edeadb`, `5b57328`)

### Tool: `backend/scratch/benchmark_vision.py`

Runs the production ingredient-parser system prompt + `IngredientParseResponse` Pydantic schema through three vision models in parallel:

- Claude Sonnet 4.6 (current production)
- GPT-4o-mini (cheap candidate)
- GPT-4o (premium candidate)

Reports per-provider: ingredient count, parsing_confidence, wall time, in/out tokens, USD cost. If `--truth-file` or `--truth-text` is provided, also runs `diff_extraction.diff()` per provider and reports recall + precision.

Anthropic uses `messages.parse(output_format=…)`; OpenAI uses `beta.chat.completions.parse(response_format=…)`. Both fed the same base64 image and the same user prompt. The shared production system prompt ensures apples-to-apples comparison.

### Two benchmark runs

**Run 1: Dr.G Daily Lotion** (50-ingredient Korean cosmetic INCI label)

| Provider | Recall | Precision | Cost | Confidence |
|---|---|---|---|---|
| Sonnet 4.6 | 98.0% (effective 100%) | 98.0% | $0.04469 | 0.93 |
| gpt-4o-mini | 96.0% | 94.1% | $0.00568 | **1.00** |
| gpt-4o | **80.0%** | 85.1% | $0.02306 | 0.90 |

**Run 2: Cetaphil Moisturizing Lotion** (16-ingredient Western cosmetic INCI label)

| Provider | Recall | Precision | Cost | Confidence |
|---|---|---|---|---|
| Sonnet 4.6 | 100.0% | 100.0% | $0.02558 | 0.93 |
| gpt-4o-mini | 93.8% | 93.8% | $0.00467 | **1.00** |
| gpt-4o | 93.8% | 93.8% | $0.01339 | **1.00** |

### Findings

**1. gpt-4o's hallucination risk scales with list length.** On the 50-ingredient label it invented `Isododecane`, `Helianthus Annuus Seed Oil Unsaponifiables`, `Polyhydroxystearic Acid` — none on the actual label. On the 16-ingredient label, zero hallucinations. Hypothesis: the model fills the structured-output schema with plausible substances when token pressure rises. Either way: **gpt-4o is unreliable for the safety analyzer's primary path regardless of pricing**.

**2. mini's overconfidence is a calibration bug, not a one-off.** Reported confidence **1.00 on both scans** despite real errors in both:
- Daily Lotion: substituted `Propanediol → Propylene Glycol` (different molecules), invented `Polyglucuronic Acid`, typos `Timella`/`Phyto`
- Cetaphil: dropped `(Water)` from `Aqua (Water)`, typo `Tocopheryl → Tocopherol Acetate`

A 94–96% recall model reporting confidence 1.00 will feed wrong ingredient names to the analyzer, which will then confidently flag/clear products based on the bad input. The downstream consequence is worse than the upstream cost saving.

**3. Sonnet's calibration is real.** Reported confidence 0.93 on both scans. On Cetaphil it self-flagged its own typo in parsing_notes — *"'Sodium Benzdate' may be..."*. The model knows when it's probably wrong AND says so. That metacognition is what makes the output safe to trust downstream.

**4. mini's "20× cheaper" headline doesn't survive.** mini consumed 28K input tokens vs Sonnet's 5K for the same image — OpenAI tiles images at higher resolution for mini. Net savings are ~5.5–8× (varies by output length), not 20×.

**5. Cost spread narrows on shorter lists.** 7.9× cheaper (mini vs Sonnet) on 50-ingredient label, 5.5× cheaper on 16-ingredient label. Output tokens dominate cost differential.

### Production routing decision

**Stay on Sonnet 4.6.** Two scans confirm: only Sonnet has calibrated confidence + zero hallucinations + INCI semantic awareness (Water/Aqua reorder per INCI convention, allergen flagging in parsing_notes). Cost savings at dogfooding scale ($3.50–4.50/day at 100 scans) don't justify the safety-critical risk of mini's confident chemical confusion.

**Trigger to revisit**: scale exceeds ~10K scans/day AND we're willing to wire a confidence-threshold fallback (`if mini.confidence < X OR result flagged risky → re-run on Sonnet`). The benchmark script + diff helper are both retained for that future evaluation.

---

## Files touched

```
backend/db/queries.py                              _UPSERT_CACHED_REPORT now a real upsert + docstring
backend/db/schema.sql                              safety_reports: UNIQUE on barcode, updated_at column, drop redundant index
backend/main.py                                    CORS — env-driven explicit origin list, no more wildcard+credentials
backend/requirements.txt                           +openai>=2.0.0 (dev-only for now, ready if routing layer added)
backend/scratch/benchmark_vision.py                new — three-provider vision benchmark
docs/dogfooding-notes.md                           Pre-ship CORS item resolved with real root cause + new "Vision-model benchmark observations" section with 2 rows
docs/history/SESSION_K_2026-05-25_PRODUCTION_READINESS.md   this file
```

---

## Commits (chronological)

- `57417a6` — `safety_reports: true upsert + updated_at column`
- `b76730c` — `fix: CORS — explicit origin list, drop spec-forbidden wildcard+credentials combo`
- `92ce8fa` — `Add vision-OCR benchmark: Claude vs gpt-4o-mini vs gpt-4o`
- `0edeadb` — `Docs: log Daily Lotion vision-benchmark result + production routing decision`
- `5b57328` — `Docs: log Cetaphil vision-benchmark + cross-scan analysis`

All pushed to `origin/feature/capacitor-mobile`.

---

## Decisions worth keeping

- **`allow_credentials=True` + `allow_origins=["*"]` is silently broken.** Browsers reject the response per the CORS spec. Always use explicit origins when credentials are enabled. Worth flagging in any future FastAPI/Starlette setup.
- **Migrations in a transaction with idempotent SQL.** The safety_reports migration was four ALTER/DELETE/CREATE statements wrapped in `async with conn.transaction():`. All-or-nothing. Each statement was either `IF NOT EXISTS` or guarded by row-count checks. Safe to re-run. This pattern should be the default for any schema change against a live database.
- **Defer-with-trigger > build-just-in-case.** Two examples today: history table deferred (trigger: compliance / A/B / "prove what you said"), image persistence still deferred (trigger from Session J: 2+ re-shoot-impossible OCR failures). The cost of building speculative infrastructure is real — both code maintenance burden and the opportunity cost of not building something that matters now. Naming the trigger explicitly lets you say "not yet" without forgetting it exists.
- **Calibration matters as much as accuracy.** The benchmark didn't just compare recall numbers — the most actionable finding was the calibration delta (Sonnet's 0.93 vs OpenAI's 1.00). A model that's wrong AND knows it can be guarded with downstream logic; a model that's wrong AND confident is unsafe to trust automatically. For safety-critical applications, prefer the less-confident model when accuracy is close.
- **Premium tier ≠ better tier on every task.** gpt-4o (the premium OpenAI model) was the worst of three on the long-list benchmark. Don't assume the more expensive model is the right default — benchmark on representative input before defaulting to either end of the price ladder.
- **Match the dogfooding question to the test data.** When the user provided the SDS as "truth" for Cetaphil, the right move was to flag that SDS lists only hazardous components (~6) not the full INCI label (~16) — and either request the consumer list OR pivot to a different validation question (hazard-subset detection). Don't run a low-signal diff just because there's data on hand.
