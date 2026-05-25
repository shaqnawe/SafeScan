# Session I — frontend design pass, image agent overhaul, silent persistence bug fix

**Date:** 2026-05-24 (spanning 2026-05-23 → 2026-05-24)
**Scope:** disciplined three-pass frontend redesign (typography, motion, theme toggle + anchor + iconography), image-agent rewrite for parallelism + structured output + bounded timeout + format validation + per-call status + retry, fix for a silent persistence bug that had been breaking every photo submission with a barcode, and threading the new agent status fields into the UI.

---

## Goals

Coming in:
1. Audit the existing frontend against the `frontend-design` skill's conventions and close the most glaring gaps.
2. Address the TODO image-extraction items (parallelize, structured output, timeout, validation, status, retry).
3. Verify the `ON CONFLICT (barcode) WHERE barcode IS NOT NULL` upsert in `image_agent._save_submission()` (suspected silent failure per the prior session's notes).

Picked up along the way:
4. The italic `'n'` in the Fraunces wordmark was being chopped by `background-clip: text`. Needed a small padding fix.
5. Skills installed via `npx skills add anthropics/skills` left untracked directories (`.agents/`, `.claude/`) and a `skills-lock.json` polluting the working tree.
6. Three-state theme toggle (system / light / dark) — Home only at first, then lifted to every page via a `ThemeProvider` context.
7. End-to-end smoke test of the submission pipeline to confirm the persistence bug fix landed and the status fields populate correctly.

---

## Frontend pass — A / B / C

The pass was scoped before any code, then committed in three semantically clean commits. Avoided drift by sticking to the three-batch plan: each batch type-checks clean on its own.

### Pass A — typography (`cfd8161`)

Pair a distinctive display face with the existing Manrope body — the `frontend-design` skill explicitly calls out that "pair a distinctive display font with a refined body font" is a key gap when only one face is in use.

- Loaded **Fraunces** alongside Manrope from Google Fonts. Variable axes loaded: `opsz 9..144`, `wght 200..800`, `SOFT 0..100`.
- New `FONT_DISPLAY` constant in `theme.ts` — reserved by convention for hero typography only (wordmark + grade letter, nothing else).
- Applied Fraunces italic to the "SafeScan" wordmark on Home at `opsz 144`, `SOFT 50`, `weight 500`, `size 56pt`.
- Applied Fraunces upright to the giant grade letter on `SafetyReport` at `opsz 144`, `SOFT 30`, `weight 300`, `size 120pt`.

**Italic-`n`-chopped fix:** the wordmark's trailing italic `'n'` was being clipped by `background-clip: text`. The italic glyph's exit stroke extends past the geometric bounding box, but the gradient mask clips to the box edges. Fix: symmetric `padding: '0 0.18em'` on the H1 — em-based so it scales with `font-size`; symmetric so the text stays visually centered. Verified via Playwright in both light + dark mode.

### Pass B — motion (`8f2e1e3`)

The skill's framing: *"one well-orchestrated page load with staggered reveals creates more delight than scattered micro-interactions."* The codebase had zero transitions, zero entrance animations.

- New `src/motion.css` (80 lines, no library dependency):
  - `@keyframes fade-up`, `@keyframes fade-in`
  - `.fade-up`, `.fade-in` entrance utilities — easing `cubic-bezier(0.22, 1, 0.36, 1)`
  - `.stagger-1..7` — 70ms cascade delays
  - `.lift` — `translateY(-2px)` hover affordance for cards
  - `.press` — `scale(0.97)` on `:active` + `brightness(1.05)` on `:hover` for CTAs
  - Wrapped in `@media (prefers-reduced-motion: reduce)` to disable on user request
- Imported once in `main.tsx` so utilities are globally available.
- Applied across pages:
  - **HomePage**: logo → wordmark → tagline → CTA → footer-hint cascade, feature cards staggered with `.lift`, CTA gets `.press`
  - **SafetyReport**: hero card → summary → stats → findings → ingredients cascade via the existing `Glass` wrapper (which now accepts an optional `className`); CTA gets `.press`
  - **AllergenProfilePage**: description + grid cascade, `.press` on each toggle
  - **HistoryPage**: list fade-up, each entry gets `.lift .press`
  - **SubmissionsPage**: list fade-up, `.lift .press` on clickable items
  - **ComparisonPage**: slot pair fade-up, `.press` on Go buttons
  - **AddProductPage**: intro + photo pickers cascade

Discipline note: avoided fade-up on every individual list item — gets visually busy when a list has 20+ entries. Fade up the **container** once instead.

### Pass C — theme toggle + anchor gesture + lucide icons (`5ad3349`)

Three pieces of polish bundled because they all touch chrome / icons.

**Theme toggle (tri-state):**
- `useDarkMode.ts` → `.tsx`, rewritten to return `{isDark, mode, setMode, cycleMode}` where `mode: 'system' | 'light' | 'dark'`.
- Persisted to `localStorage` under `safescan:theme-mode`.
- `'system'` follows OS preference live via `matchMedia` listener; `'light' | 'dark'` pin explicitly.
- New `ThemeProvider` context + `useTheme()` hook in the same file. `main.tsx` wraps `<App />` once; pages drop `<ThemeToggle />` anywhere without prop drilling.
- New `components/ThemeToggle.tsx` with two variants: `pill` (icon + label, used on Home where the pill bar lives) and `icon` (round 36×36, used in cramped page headers).
- Mounted on every page that has a header: `AllergenProfilePage`, `HistoryPage`, `AddProductPage` (both header blocks), `SubmissionsPage`, `ComparisonPage`, `SafetyReport`, plus the `App` error view. Skipped only on `BarcodeScanner` (camera overlay) and `LoadingSpinner` (transient).

**Anchor gesture (Home only):**
The skill repeatedly asks: *"what is the one thing someone will remember?"* Hero had no anchor.

- Giant ghosted "SafeScan" rendered behind the hero — Fraunces 240pt italic, `opsz 144`, `SOFT 70`, rotated `-3°`, opacity `0.05` light / `0.035` dark.
- Positioned `absolute` below the logo tile, extends past the page gutters (breaks the centered grid).
- `pointer-events: none` so it never intercepts taps.

**Lucide icons (replace emoji in chrome, keep for status/branding):**

Installed `lucide-react@^1.16.0` with `--legacy-peer-deps` (pre-existing `@vitejs/plugin-basic-ssl@2.3.0` ↔ `vite@5.4.21` peer-dep mismatch is unrelated; existing install was already past it).

| Replaced | New |
|---|---|
| 🔍 Home logo tile | `HeartPulse` (signals "health", not just "scanner") |
| 📷 "Start Scanning" CTA + text | `ScanLine` + new copy "Scan a Product" |
| 🧬 🍎 ✨ feature cards | `Dna`, `Apple`, `Sparkles` (22px, amber accent) |
| 🌾 allergens pill | `Wheat` |
| 🕐 history pill | `Clock` |
| 🌓 ☀️ 🌙 theme toggle | `Monitor`, `Sun`, `Moon` |
| ← back buttons (every page) | `ArrowLeft` |
| ↻ submissions refresh | `RefreshCw` |
| 🔍 history empty state | `Search` (56px, thinner stroke) |
| ⚠️ App error view | `AlertTriangle` |

**Kept as emoji** (semantic / per-item identity):
- Status pills on submissions: ⏳🔄✅❌ (color encodes meaning at a glance)
- Empty-state decorations: 📦 📋
- Allergen labels: 🥜🥛🦐🌾… (each allergen has its own identity emoji)

### Atomic-split mechanics

After all three passes were applied locally in one big working tree, splitting back into clean A / B / C commits required:

1. `git stash --include-untracked` to save the full final state.
2. Hand-rebuild Pass A edits from memory, commit.
3. Hand-rebuild Pass B edits, commit.
4. `git checkout 'stash@{0}' -- frontend/` to overwrite the working tree with the final state from the stash (the diff vs. HEAD now contains only the C-specific changes).
5. `git checkout 'stash@{0}^3' -- frontend/src/components/ThemeToggle.tsx` for the untracked new file (untracked files are the 3rd parent of a `--include-untracked` stash).
6. `rm frontend/src/hooks/useDarkMode.ts` + `git add -u` to record the rename-to-`.tsx`.

Recorded here because the trick is non-obvious and likely to come up again.

---

## Image agent overhaul

Three commits, each a clean unit. Wall-clock for a typical "both photos uploaded" submission drops roughly 2×, every Claude vision call now has a bounded timeout, JSON parsing is type-safe, uploads are format-checked + auto-resized at the edge, and transient errors get one retry.

### Parallel vision calls + `messages.parse()` + bounded timeout (`e7e22c8`)

`process_product_photos()` previously awaited `_extract_product_info()` then `_parse_ingredients()` sequentially — total wall-clock = sum of both. Made independent and concurrent:

```python
extract_task = asyncio.create_task(_extract_product_info(...)) if product_image else None
parse_task   = asyncio.create_task(_parse_ingredients(...))   if ingredients_image and not manual_text else None
# both running now
extracted = await extract_task if extract_task else default
ingredients_response = await parse_task if parse_task else None
```

Trade-off accepted: the parser used to be fed `extracted.product_type` (more accurate after the front-photo extraction completed). Now it's fed the caller-provided `product_type_hint` instead, so it can launch in parallel. The frontend always passes `product_type_hint` (form has a select), and the parser handles both food + cosmetic regardless — small accuracy edge case for 2× speedup is the right call.

**Structured output via `messages.parse()`:**
- New `IngredientParseResponse` Pydantic model alongside `ExtractedProduct`.
- Both vision helpers now use `client.messages.parse(..., output_format=PydanticClass)` and read `.parsed_output` — matches the existing pattern in `scanner.py`.
- Dropped ~40 lines of fragile manual JSON parsing (markdown-fence stripping + `json.loads` + `data.get()` field plucking).

**Bounded timeout:**
- Per-call `timeout=60.0`. SDK default is ~10min — a hung connection on an interactive photo submission used to stall the request indefinitely. 60s comfortably accommodates adaptive thinking.

**Misc:**
- `max_tokens` on `_extract_product_info` bumped `1024 → 2048` to match the parser and leave headroom for adaptive thinking.

### Format validation + auto-resize at the endpoint boundary (`1241142`)

New `validate_and_normalize_image()` helper, called from `main.py` per upload **before** the bytes reach the agent.

- **Magic-byte sniff**: detects JPEG / PNG / GIF / WEBP from the file header. The client-supplied `content_type` is ignored — the file header is authoritative. Anything else raises `ValueError`, returned as HTTP 400.
- **Auto-resize**: anything over 3.5MB raw (the safe ceiling under Anthropic's 5MB base64 limit, since base64 inflates by ~33%) gets downsized via Pillow — `thumbnail` to 2048px longest side (preserves OCR-readable text), re-encoded as JPEG with progressively lower quality (`85 → 75 → 65 → 55`) until under budget.
- `pillow>=11.0.0` pinned in `requirements.txt` (was already a transitive dep).

Verified end-to-end: 18.7MB high-entropy JPEG resized to ~2MB, dimensions clamped to 2048×2048. `curl -F "product_image=@plaintext.txt"` returns clean 400 with the `ValueError` message.

### Per-call status + retry on transient errors (`aacdad5`)

Previously the helpers returned a default `ExtractedProduct()` or empty tuple on failure — the caller couldn't tell apart "no photo uploaded" vs "Claude errored". Refactored:

- Helpers now return `Optional[ExtractedProduct]` / `Optional[IngredientParseResponse]` (None = failure).
- `SubmissionResult` gained `product_status` and `ingredients_status` of type `CallStatus = Literal['ok', 'failed', 'not_attempted']`.
- The orchestrator translates None into `'failed'`, sets `'ok'` on success, `'not_attempted'` when the call wasn't launched. Manual-text parsing always reports `'ok'` since it can't fail in a way worth flagging.

**Retry helper:** new `_call_anthropic_with_retry(call_factory, label)` — takes a **zero-arg async factory** (not a coroutine directly, because coroutines can only be awaited once and a retry needs to rebuild the request). Retries once on `anthropic.RateLimitError | anthropic.APITimeoutError` with 1s backoff; permanent `anthropic.APIError` fails fast.

Verified test matrix with simulated exceptions:
- transient → retry → success: 2 attempts, returns success
- transient × 2 → exhaust: 2 attempts, returns None
- permanent APIError: 1 attempt, no retry, returns None

---

## The silent persistence bug (`c92f9f6`)

The high-severity item from the TODO. Worth its own section because the bug was both invisible to the API caller and load-bearing for a whole feature path.

**Symptoms:** every `POST /api/submit-product` with a barcode appeared to succeed (HTTP 200, response body looked correct), but `submission_id` was always `null` and the row never landed in `user_submissions`. The SubmissionsPage list would show nothing even after dozens of uploads.

**Root cause:** `image_agent._save_submission()` does an `INSERT ... ON CONFLICT (barcode) WHERE barcode IS NOT NULL DO UPDATE ...` upsert. PostgreSQL requires a matching partial unique index for that clause to be valid — without one, the query fails at **planning time** (not execution time) with:

```
InvalidColumnReferenceError: there is no unique or exclusion constraint
matching the ON CONFLICT specification
```

The exception was getting swallowed by `_save_submission`'s blanket `try/except Exception`, which logged a one-liner and returned `None`. The function shape was unchanged from the caller's perspective; the API still returned 200; the submission silently never persisted. NULL-barcode inserts ALSO failed because the error is raised at plan time regardless of the actual values being inserted.

**Fix:** add the index, schema-side:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS user_submissions_barcode_unique
    ON user_submissions (barcode)
    WHERE barcode IS NOT NULL;
```

Partial so anonymous (no-barcode) photo-only submissions can repeat without a constraint violation.

Applied to the live database. Schema change pushed via `db/schema.sql`. Verified with a smoke test against the live DB:
- Same-barcode upserts collapse to one row (`id1 == id2`) ✅
- NULL-barcode inserts create separate rows (`id1 != id2`) ✅

**Lesson on the swallow:** the blanket `except Exception` in `_save_submission` is what made this silent for so long. Considered tightening to `except asyncpg.PostgresError` so this kind of planning-time error would surface to the caller, but kept the existing behavior for now because of the swallow's other (legitimate) use: not failing a whole image-extraction response just because the DB happened to be momentarily unreachable.

---

## Frontend extraction-status surface (`d2db589`)

The backend started returning `product_status` / `ingredients_status` in `aacdad5` but the frontend ignored them. Wired through:

- **Backend `GET /api/submissions`** — now pulls the two status fields out of `extracted_data` and includes them in each per-row response (defaults to `'not_attempted'` for older rows that pre-date the fields).
- **Frontend types** — new `CallStatus` type; added the two fields to both `SubmissionResult` and `UserSubmission` interfaces.
- **AddProductPage**: red warning card with `AlertTriangle` above the extracted-product card when either status is `'failed'`. Copy: *"Couldn't read the {product label / ingredient list}"* + actionable guidance (better lighting, hold closer, manual entry).
- **AddProductPage redirect**: the auto-redirect-to-Submissions on successful submission was suppressed when extraction had failures — otherwise the warning would never have been seen, the user would silently end up on a list page with no context for why the extracted data looked sparse.
- **SubmissionsPage**: compact "extraction issue" pill (`AlertTriangle` + red soft-bg) on each list row when either status is `'failed'`. Title attribute spells out which side failed on hover. Orthogonal to the existing pending/analyzing/complete/failed workflow status — a "complete" submission can still have had a partial extraction failure.

Verified via Playwright with a mocked failed-extraction response: warning card renders, auto-redirect correctly suppressed.

---

## End-to-end smoke test

Drove the production submission flow via Playwright (the dev frontend pulls `VITE_API_URL=https://proactive-harmony-production-2735.up.railway.app` from `.env.local`, so the test actually hit Railway, not the local backend).

Results:
- Submit → HTTP 200 ✅
- `submission_id=6` (proves the partial-index fix is deployed) ✅
- `product_status='not_attempted'`, `ingredients_status='ok'` (proves `aacdad5` deployed) ✅
- 5 manual ingredients parsed ✅
- `ready_for_analysis=true` ✅

**Surfaced separately:** CORS on `/api/submissions` — Railway's allowed origins don't include `localhost:5173`, so the SubmissionsPage list-fetch fails when accessed via the dev frontend. Not blocking; production-only frontend is unaffected. Worth fixing in the FastAPI CORS middleware if dev-against-prod workflow matters.

---

## .gitignore for Claude Code skills (`fa12dce`)

`npx skills add anthropics/skills` (run mid-session for skill access) created three things in the working tree that don't belong in version control:

| Path | Why excluded |
|---|---|
| `.agents/` | Vendored skill content — bulky, re-installable via `npx skills add anthropics/skills` |
| `.claude/` | Personal `settings.local.json` + symlinks to `.agents/skills/` that only work on this machine |
| `skills-lock.json` | Lock file for skill versions — useless without `.agents/` |

Added to `.gitignore` under a new "Claude Code / agent skills" section with a comment explaining the re-install command.

Worth noting: the symmetric `marketplace` flow (`/plugin marketplace add anthropics/skills`) was also tried briefly during the same exploration — turned out to be redundant with the npx install. Removed both the marketplace entry from `~/.claude/settings.json` and the cloned marketplace directory in `~/.claude/plugins/marketplaces/` to clean up.

---

## Files touched

**Backend:**
- `agents/image_agent.py` — rewritten across three commits (parallel, parse, timeout, validation, status, retry)
- `db/schema.sql` — new partial unique index on `user_submissions(barcode) WHERE barcode IS NOT NULL`
- `main.py` — validation wired at endpoint boundary; status fields surfaced in `/api/submissions`
- `requirements.txt` — `pillow>=11.0.0`

**Frontend:**
- `src/components/HomePage.tsx` — Fraunces wordmark, anchor gesture, lucide icons, motion classes, ThemeToggle
- `src/components/SafetyReport.tsx` — Fraunces grade letter, cascading reveals via Glass wrapper, ThemeToggle, ArrowLeft, CTA press
- `src/components/AllergenProfilePage.tsx` — content cascade, press on toggles, ArrowLeft, ThemeToggle
- `src/components/HistoryPage.tsx` — list fade-up, lift+press on entries, Search empty state, ArrowLeft, ThemeToggle
- `src/components/AddProductPage.tsx` — intro/picker cascade, ArrowLeft (both header blocks), ThemeToggle, extraction-failure warning card, suppress-redirect-on-failure
- `src/components/SubmissionsPage.tsx` — list cascade, lift+press on items, ArrowLeft, RefreshCw, ThemeToggle, extraction-issue badge
- `src/components/ComparisonPage.tsx` — slot cascade, press on Go, ArrowLeft, ThemeToggle
- `src/components/ThemeToggle.tsx` (new) — pill + icon variants
- `src/hooks/useDarkMode.tsx` (renamed from `.ts`) — tri-state hook + ThemeProvider + useTheme context
- `src/main.tsx` — ThemeProvider wrap + motion.css import
- `src/motion.css` (new) — fade-up + stagger + lift + press utilities with reduced-motion respect
- `src/theme.ts` — `FONT_DISPLAY` export
- `src/types.ts` — `CallStatus`, status fields on `SubmissionResult` + `UserSubmission`
- `index.html` — Fraunces added to Google Fonts URL
- `package.json` + `package-lock.json` — `lucide-react@^1.16.0`

**Root / config:**
- `.gitignore` — `.agents/`, `.claude/`, `skills-lock.json`

---

## Commits (chronological)

| Commit | Summary |
|---|---|
| `cfd8161` | Pass A: Add Fraunces display font, paired with Manrope body |
| `8f2e1e3` | Pass B: Add motion primitives + cascade reveals across pages |
| `5ad3349` | Pass C: Add theme toggle, anchor gesture, and lucide icons |
| `fa12dce` | Ignore Claude Code agent skills and local settings |
| `e7e22c8` | Image agent: parallel vision calls, structured output, bounded timeout |
| `c92f9f6` | Fix missing partial unique index on user_submissions(barcode) |
| `1241142` | Image agent: validate format and downsize at the endpoint boundary |
| `aacdad5` | Image agent: explicit per-call status + retry on transient errors |
| `d2db589` | Surface image-agent extraction status in the frontend |

---

## Decisions worth keeping

- **Display font scope:** Fraunces is reserved for the wordmark and grade letter only. Don't dilute by applying it to page titles — they keep Manrope. The display face's impact comes from *restraint*.
- **Lucide vs emoji split:** chrome / branding / nav → lucide; status / per-item identity → emoji. Status emojis (⏳🔄✅❌) and allergen identity emojis carry color and meaning at a glance that monoweight lucide alternatives would lose.
- **`asyncio.create_task` then await each:** as concurrent as `asyncio.gather()` for two tasks, and lets us bind named results without unpacking a tuple.
- **Image validation lives at the endpoint boundary** (`main.py`), not inside the agent. Bad uploads should return HTTP 400, not a deep-stack 500. Agent gets to trust its inputs.
- **Partial unique index pattern:** for any `ON CONFLICT (col) WHERE predicate` upsert, the matching partial unique index has to exist in the schema, otherwise PG fails at *planning* time regardless of the actual values being inserted. Easy to forget; easy to swallow if the caller has a blanket exception handler.
- **Suppress-redirect-on-failure** is what makes the new extraction-failure warning actually visible — without it, the auto-navigate-to-Submissions on successful upload would skip past the AddProductPage done view entirely.
