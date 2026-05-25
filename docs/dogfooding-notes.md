# Dogfooding Notes

Informal notes from real-world use. Not a formal document — don't over-format this.
Record what surprises you: wrong grades, missed recalls, broken UI, slow scans.
Anything that would make you not trust the app is worth a line here.

---

## Pre-ship verification

One-time checks to run the first time the app is used post-deploy. These
verify fixes that couldn't be tested live during implementation.

- [ ] Verify CAS write-back end-to-end once API credits are restored.
      Trigger an unknown-ingredient classification (scan a product with
      an obscure ingredient not in the DB), then query:
        SELECT name, cas_number, updated_at FROM ingredients
        WHERE cas_number IS NOT NULL
        ORDER BY updated_at DESC LIMIT 5;
      Confirm the newly-classified ingredient appears with its CAS populated.
      If CAS is null but Claude should have known it, something in the
      wire-through is silently dropping the field. Check
      backend/db/ingredient_resolver.py — _IngredientClassification model,
      _CLAUDE_SYSTEM prompt, _INSERT_INGREDIENT param order, _write_back.

- [ ] Verify a real photo submission end-to-end now that the silent
      persistence bug is fixed (Session I, commit c92f9f6). Upload a
      product front + ingredients photo via the iOS app or the web UI:
        1. Confirm /api/submit-product returns 200 with a non-null
           submission_id (was null before the partial-index fix)
        2. Confirm the row appears in user_submissions table:
             SELECT id, barcode, status, created_at
             FROM user_submissions ORDER BY id DESC LIMIT 5;
        3. Confirm the auto-triggered background analysis runs and the
           safety_reports row materializes
        4. Confirm product_status and ingredients_status are 'ok' in
           extracted_data (or 'failed' with a visible warning card on
           AddProductPage if Claude couldn't read the labels)
      Costs ~$0.01 in Claude credits per attempt.

- [ ] **CORS on /api/submissions when dev frontend hits Railway.**
      Surfaced by the Session I E2E smoke test (2026-05-24). Railway's
      CORSMiddleware doesn't include 'http://localhost:5173' in
      allow_origins, so when frontend/.env.local is pointed at the
      production URL the SubmissionsPage list-fetch fails with:
        Access to fetch at 'https://...railway.app/api/submissions'
        from origin 'http://localhost:5173' has been blocked by CORS
        policy: No 'Access-Control-Allow-Origin' header is present
      POST /api/submit-product is unaffected (likely because preflight
      isn't required for the same content-type pattern).
      Fix: add 'http://localhost:5173' and 'http://localhost:4173'
      (preview) to backend/main.py's CORSMiddleware allow_origins.
      Not blocking — production-only frontend has no issue. Only worth
      fixing if dev-against-prod workflow matters.

---

## How to validate image-agent OCR quality

After scanning a product with photos of both the front AND the ingredients
label, compare what the image agent extracted against the real label text.

```bash
cd backend

# 1. Find the submission id you just created:
psql "$DATABASE_URL" -c "SELECT id, barcode, status FROM user_submissions ORDER BY id DESC LIMIT 3"

# 2. Run the diff against ground truth (manufacturer site or transcribed label):
/Users/npc/miniconda3/envs/myenv/bin/python -m scratch.diff_extraction \
    --submission-id <N> --truth-stdin     # paste truth, Ctrl-D

# or from a file:
/Users/npc/miniconda3/envs/myenv/bin/python -m scratch.diff_extraction \
    --submission-id <N> --truth-file path/to/truth.txt
```

The helper reports recall (% of real ingredients captured) + precision
(% of extracted entries that are real) and lists each MISSED, EXTRA,
and FUZZY-matched ingredient. Log notable findings under "Missing
ingredients / false negatives" or "Incorrect flags / false positives"
below.

---

## Scan observations

| Date | Barcode | Product | Expected grade | Actual grade | Notes |
|------|---------|---------|---------------|--------------|-------|
| 2026-05-24 | 8809838658313 | Dr.G R.E.D Blemish Clear Soothing Body Wash (Korean) | B (rinse-off, mostly safe ingredients with one fragrance + one salicylic acid) | D (fallback) → A 85 after fix | First real submission. **Front-of-product photo + pasted ingredient text** (not a photo of the ingredients label) — so this validated the front-image path + the text-list path, NOT image-agent OCR on a dense INCI list. The 42 ingredients came from the pasted text. Persistence worked after the schema fix (id=7). Initial analysis returned fallback grade D because Phase 2 disconnected at ~60s. Root-caused with `backend/scratch/repro_phase2.py` bisecting harness: upstream LB timeout on combined system+message size, NOT a model or content-filter issue. Fix: switched Phase 2 to `messages.stream()` — keeps the connection alive past 60s. Re-analysis now produces a real Opus report. See CLAUDE.md "Phase 2 disconnect bug (resolved)". **Still need:** end-to-end test of image-agent ingredient OCR on an actual back-of-package photo. |
| 2026-05-25 | 8809695369650 | Dr.G Dermoisture Barrier.D Daily Lotion (Korean) | A (gentle moisturizer, ceramides + hyaluronic acid, no concerning ingredients) | A 91 | **First successful end-to-end image-OCR submission**. Image-only (front + back) — no manual text. Required three backend fixes over the course of debugging: (1) drop adaptive thinking on `_parse_ingredients` / `_extract_product_info` — thinking was eating the max_tokens budget and truncating the structured JSON output mid-property (`pydantic ValidationError: EOF while parsing... column 4073`); (2) bump max_tokens 2048 → 4096; (3) broaden retry helper's `except` to catch pydantic.ValidationError + bare Exception so silent failures land in DB/logs instead of bubbling 500s. After deploy: 50 ingredients extracted, parsing_confidence 0.93, parsing_notes documented the OCR normalizations (Aqua reordering, rejoined hyphenated `Magnesi-um`). **Diff helper result vs Dr.G website truth: 49/50 exact + 1 semantically equivalent (Water/Aqua reorder) = effectively 100% recall + precision, 0 hallucinations, 0 fusion artifacts.** Image-agent OCR for cosmetic INCI labels is validated. See `docs/history/SESSION_J_2026-05-25_PHASE_2_STREAMING_FIX.md` for the debugging journey. |

---

## UI / rendering issues

<!--
Examples: ingredient list truncated, allergen banner wrong color,
report card overflows on small screen, compare mode layout broken on iOS.
-->

---

## Missing ingredients / false negatives

<!--
Ingredient was on the label but not flagged / not found in DB.
Include: raw label text, what it should have resolved to, what the report said.
-->

---

## Incorrect flags / false positives

<!--
Ingredient was flagged but shouldn't have been, or grade is harsher than warranted.
Include: canonical name, concern tag applied, why it's wrong.
-->

---

## Performance notes

<!--
Slow scans (>10s), spinner stuck, camera lag, backend timeouts.
Note whether it was Phase 1, Phase 2, or DB lookup that was slow.
-->

---

## Recall attachment quality

<!--
Recalls shown that don't match the product (false positive match via FTS).
Recalls missing that you know should be there.
Risk level (serious/high) correctly set?
-->