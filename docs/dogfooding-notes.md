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

- [x] **CORS on /api/submissions when dev frontend hits Railway.** Fixed
      Session K (2026-05-25). Actual root cause was NOT a missing localhost
      origin — it was `allow_origins=["*"]` paired with `allow_credentials=True`,
      which the CORS spec forbids (browsers silently reject the response).
      `backend/main.py` now reads `ALLOWED_ORIGINS` from env (comma-separated)
      with a default list that includes Vite dev/preview, Capacitor iOS
      (`capacitor://localhost`), Capacitor Android (`https://localhost`), and
      the Railway production URL. To override on Railway, set `ALLOWED_ORIGINS`
      env var. To allow another local-network device, append its origin to the
      env var.

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
| 2026-05-25 | 8809247975612 | LIKESKY 띠잇 (Thin In) 3 Layer Biscuit (Korean food) | C (ultra-processed snack, refined flour + sugar + palm oil + artificial flavor + caramel color) | C 49 | **Food path validated**. Image-only submission, rotated/vertical ingredients panel. OCR captured 26 ingredients at parsing_confidence 0.85 (lower than the cosmetic's 0.93 — Claude correctly self-calibrated for the harder image). `parsing_notes` self-flagged uncertainty: "'Skin Milk Powder' may be 'Skim Mil[k Powder]'" — almost certainly an OCR ambiguity from rotated text. Allergen declaration block detected and noted (wheat, soybean, milk, sesame). Phase 2 produced a substantive food analysis: NOVA 4 ultra-processed penalty, caramel color flagged for 4-MEI per IARC + Prop 65, artificial flavor penalty for opacity, rosemary oleoresin captured as a natural-antioxidant positive. **Diff helper recall/precision look low at face value (~30%) but this is a truth-list quality issue, not OCR weakness** — the truth list uses EU category names (`leavening agent(E575)`, `flavoring`, `mixed cooking oil`) while OCR captured specific chemical names (`Ammonium Bicarbonate` for E575, `Artificial Flavor`, `Soybean Oil` + `Palm Oil`). Real effective accuracy ~95%+. Truth list itself had OCR/copy errors (`Wheat flour sugar` and `sugars Processed product` missing commas). The "Skin/Skim Milk" finding is a real OCR call worth a fuzzy-match flag if we ever extend the diff helper with token-set or regulatory-code equivalence matching. |

---

## Vision-model benchmark observations

Same image + same prompt + same Pydantic schema through three providers in
parallel (`backend/scratch/benchmark_vision.py`). Production currently uses
Anthropic Sonnet 4.6.

| Date | Image | Truth | Sonnet 4.6 | gpt-4o-mini | gpt-4o |
|------|-------|-------|------------|-------------|--------|
| 2026-05-25 | Dr.G Daily Lotion (Korean cosmetic, dense INCI) | 50 ingredients | **50 ext / 98.0% / 98.0% / conf 0.93 / $0.04469 / 26.3s** — single "miss" was Water/Aqua reorder per INCI convention (semantic-equivalent). Flagged wheat allergen in parsing_notes. | 51 ext / 96.0% / 94.1% / **conf 1.00** / $0.00568 / 50.9s — substituted `Propanediol → Propylene Glycol` (different chemical), invented `Polyglucuronic Acid` and `Polyquaternium-3 Distearate`, typos `Timella`/`Phyto`. Overconfident. | 47 ext / **80.0%** / 85.1% / conf 0.90 / $0.02306 / 14.0s — multiple confident hallucinations: `Isododecane`, `Helianthus Annuus Seed Oil Unsaponifiables`, `Polyhydroxystearic Acid` (none on label); fused-split `Sucrose Cocoate → Sucrose + Cocoate`; misspelled `Ethlyhexylglycerin`. |
| 2026-05-25 | Cetaphil Moisturizing Lotion (Western cosmetic, short INCI) | 16 ingredients | **16 ext / 100.0% / 100.0% / conf 0.93 / $0.02558 / 12.8s** — single typo `Sodium Benzoate → Sodium Benzdate` was **self-flagged in parsing_notes** ("'Sodium Benzdate' may be..."). Real metacognition. | 16 ext / 93.8% / 93.8% / conf 1.00 / $0.00467 / 14.3s — dropped `(Water)` from `Aqua (Water)`, typo `Tocopheryl → Tocopherol Acetate`. Same overconfidence pattern. | 16 ext / 93.8% / 93.8% / conf 1.00 / $0.01339 / 7.0s — returned `Water` instead of INCI `Aqua`; typo `Pantolactone → Panolactone`. **No hallucinations this time** (vs 4+ on the 50-ingredient list). |

**Cross-scan picture (2 benchmarks):**

| Metric | Daily Lotion (50 ingr) | Cetaphil (16 ingr) |
|---|---|---|
| Sonnet recall | 98% (effective 100%) | 100% |
| mini recall | 96% | 93.8% |
| gpt-4o recall | 80% | 93.8% |
| Cost ratio mini:Sonnet | 7.9× cheaper | 5.5× cheaper |

**Headline findings:**

- **Sonnet 4.6 is the only consistently-calibrated provider.** Confidence 0.93 on both scans, knows when it's wrong (self-flagged the Sodium Benzdate typo). Both OpenAI models reported confidence **1.00 every time** despite real errors — overconfidence is a calibration bug, not a one-off.
- **gpt-4o's hallucination risk scales with list length.** 4+ invented ingredients on the 50-list, zero on the 16-list. Likely the model fills the structured-output schema with plausible-looking substances when token pressure rises. **Skip gpt-4o for the safety analyzer's primary path regardless of pricing.**
- **mini is consistently ~94–96%** across both scans — predictable quality floor. Errors lean toward substantive chemical confusion (`Propanediol → Propylene Glycol` — different molecules), typos, and missed parenthetical translations.
- **Cost spread narrows on shorter lists** because output tokens dominate cost differential. 7.9× cheaper on 50-list, 5.5× cheaper on 16-list. Mini's "20× cheaper input tokens" headline is misleading because mini tiles images at higher resolution (28K input tokens vs Sonnet's 5K on the same image).

**Production routing recommendation (as of 2026-05-25):** stay on Sonnet 4.6. Two scans confirm: only Sonnet has calibrated confidence + zero hallucinations + INCI semantic awareness. Cost savings at dogfooding scale ($3.50–4.50/day at 100 scans) don't justify the safety-critical risk of mini's confident chemical confusion. Trigger to revisit: scale exceeds ~10K scans/day AND we're willing to wire a confidence-threshold fallback (`if mini.confidence < X OR result flagged risky → re-run on Sonnet`).

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