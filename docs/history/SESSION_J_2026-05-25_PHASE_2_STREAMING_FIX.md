# Session J — Phase 2 streaming fix + image-agent diff helper

**Date:** 2026-05-25
**Scope:** Root-cause and fix the Phase 2 disconnect bug carried over from Session I-extended. Build a controlled bisecting harness, run it, switch Phase 2 to streaming, verify end-to-end. Then build an image-agent extraction quality diff helper for the upcoming photo+photo OCR test, and correct the prior session's dogfooding note that overstated what the body wash submission validated.

---

## Goals

Coming in:
1. Implement Path 2 from Session I-extended Open issues — build `backend/scratch/repro_phase2.py` to bisect the Phase 2 disconnect trigger with ~4–6 controlled API calls.
2. Apply the fix once root cause is known.
3. Build an after-test diff helper to evaluate image-agent ingredient extraction quality on the next real photo+photo submission.

Picked up along the way:
4. Correct the body wash dogfooding row — it implied photo OCR worked, but ingredients came from pasted text.
5. Align `user_submissions.id=7` on Railway with the fresh grade A report so the iOS SubmissionsPage shows the correct analysis.

---

## Phase 2 disconnect bisection (commit `d5874db`)

### Hypothesis going in

From Session I-extended TODO.md "Open issues", three remaining hypotheses:
- Synthetic preflight `tool_use` block with no preceding thinking violates Opus's interleaved-thinking validation
- Combined system + payload exceeds some server-side budget
- Content-specific (Korean product name, specific INCI tokens) trips a moderation filter

### The harness

`backend/scratch/repro_phase2.py` — 6 variants, each changing exactly ONE variable from the failing baseline:

| Variant | model | thinking | preflight | tool_result | system |
|---|---|---|---|---|---|
| `baseline` | Opus | adaptive | synthetic | full (~1.5K) | full (33K) |
| `no_thinking` | Opus | **OFF** | synthetic | full | full |
| `sonnet` | **Sonnet** | adaptive | synthetic | full | full |
| `no_synthetic_preflight` | Opus | adaptive | **INLINED** | n/a | full |
| `tiny_tool_result` | Opus | adaptive | synthetic | **~100c** | full |
| `no_system_prompt` | Opus | adaptive | synthetic | full | **1-sentence** |

Each variant logs model/thinking/system-size/msg-count before firing, then timing + token counts after. `max_retries=0` so we see raw failures. 120s per-call timeout to fail fast instead of waiting the full ~280s the production hang took.

### Run cost

~$0.50 total across both passes:
- Cheap pass (3 variants): `baseline` + `no_thinking` + `no_synthetic_preflight` — all FAIL at ~60s, ~$0 in completion tokens (server killed connection before any output)
- Remaining 3 variants: `sonnet` FAIL 60s, `tiny_tool_result` PASS 7.7s, `no_system_prompt` PASS 33.7s

### Result matrix

| Variant | Result | Notable |
|---|---|---|
| `baseline` | **FAIL 60.3s** | confirms repro |
| `no_thinking` | **FAIL 60.2s** | thinking is not the trigger |
| `sonnet` | **FAIL 60.2s** | not Opus-specific |
| `no_synthetic_preflight` | **FAIL 60.2s** | message structure is not the trigger |
| `tiny_tool_result` | **PASS 7.7s** | shrinking payload fixes it |
| `no_system_prompt` | **PASS 33.7s** | shrinking system prompt fixes it |

### Interpretation

All 6 hypotheses from Session I-extended were wrong. The trigger is combined input size (full 33K-char system + non-trivial message content). The clinching observation: the constant ~60s failure time across both Opus AND Sonnet — far too clean to be model performance, that's an upstream load balancer killing the request.

Likely mechanism: non-streaming `messages.create()` holds the connection idle while Opus generates 5K+ tokens. Server-side time-to-first-byte exceeds the LB's 60s cutoff. The LB closes the connection regardless of what the model is actually producing.

### Fix

One-line conceptual change in `backend/agents/scanner.py:432–467`:

```python
# Before
response = await client.messages.create(model=MODEL_HEAVY, ...)
text = "\n".join(b.text for b in response.content if ...)

# After
async with client.messages.stream(model=MODEL_HEAVY, ...) as stream:
    async for chunk in stream.text_stream:
        text_chunks.append(chunk)
text = "".join(text_chunks).strip()
```

Streaming sends tokens as they're produced — the LB sees continuous data flow and never closes the connection. Everything downstream (markdown-fence stripping, JSON parse, Pydantic validation, exception handlers) stays identical because `messages.stream()` raises the same `anthropic.APIError` family on failure.

### Verification

One streaming verification call on the failing baseline payload (~$0.20):
```
--- baseline payload, STREAMING ---
  PASS 97.1s  text=5023c  in=314  out=5892  stop=end_turn
```

Then full production-path end-to-end via `analyze_product("8809838658313")` (~$0.30):
```
[SUBMISSION] Using user submission for 'R.E.D BLEMISH Clear Soothing Body Wash' with 42 ingredients
[RESULT] 144.4s  grade=A  score=85  product='R.E.D BLEMISH Clear Soothing Body Wash'  brand='Dr.G'
[INGREDIENTS] 41 analyzed
[SUMMARY] 'This body wash has an excellent safety profile. It uses gentle, sulfate-free surfactants and is enriched with beneficial actives including Centella Asiatica and ten forms of hyaluronic acid...'
```

144s wall-clock — well past the 60s LB cutoff that previously killed every attempt. Persisted to `safety_reports.id=11`.

### What I expected vs. what shipped

Expected the fix to require restructuring the synthetic preflight message block or trimming the system prompt. Shipped a 9-line refactor of one async call. The bisection turned a 3-day debugging path into a 30-minute one.

---

## Image-agent extraction diff helper (commit `7e4bff9`)

### Why now

User flagged that the body wash submission validated front-image extraction + text-list parsing, NOT image-agent OCR on a dense INCI label. The next test will be a real back-of-pack photo, and "did OCR work?" is too fuzzy to answer by eyeballing the output.

### `backend/scratch/diff_extraction.py`

Compares extracted ingredients (from a DB submission OR pasted text) against a ground-truth list. Reports:

- **recall**: % of real ingredients the agent captured — primary OCR completeness signal
- **precision**: % of extracted entries that match real ingredients — catches hallucinations and fusion artifacts
- **matched** / **missed** / **extra** / **fuzzy** buckets, each listed individually so you can read the diff

CLI:
```bash
python -m scratch.diff_extraction --submission-id 8 --truth-file truth.txt
python -m scratch.diff_extraction --submission-barcode <bc> --truth-stdin
python -m scratch.diff_extraction --extracted-text "..." --truth-text "..."
```

### INCI-aware normalization

Three issues that would otherwise produce false mismatches:

1. **Case + whitespace**: `Water (Aqua)` vs `water(aqua)` — normalize lowercase + collapse spaces + standardize paren spacing.
2. **Internal comma in chemical names**: `1,2-Hexanediol` is one ingredient. INCI convention separates ingredients with `, ` (comma+space), so splitting on `, ` preserves it. Implemented via `_INCI_SPLIT = re.compile(r",\s+")`.
3. **Stray space inside chemical name**: some sources write `1, 2-Hexanediol`. Glued back together with `re.sub(r"(\d),\s+(\d)", r"\1,\2", text)` BEFORE splitting.

### Fuzzy matching

For each missed-truth ingredient, search for a >=0.80 similarity match in the extras bucket using `difflib.get_close_matches`. Surfaces three OCR-typical patterns:

- **Typo**: `'Salicylic Acid'` ≈ `'Salicilic Acid'`
- **Fusion**: `'Sodium Chloride'` ≈ `'SodiumChloride'` (space dropped between two ingredients)
- **Split**: `'1,2-Hexanediol'` ≈ `'2-Hexanediol'` (chemical name fragment)

Fuzzy matches count toward recall/precision (they ARE captured, just imperfectly transcribed) but are listed separately so you can spot the OCR weakness pattern.

### Bonus finding

Running the helper against the body wash submission (the supposed 100% case, since I had the ground-truth list) surfaced a real bug — the DB has an orphan `"1"` ingredient and `"2-Hexanediol"` as a separate entry. The image-agent's ingredient parser splits `"1, 2-Hexanediol"` on the comma. Same applies to any `\d,\s\d` chemical name pattern. Logged as a new low-priority Open issue in TODO.md.

---

## Aligning body wash submission on Railway

`analyze_product()` writes only to `safety_reports`, not to `user_submissions.report` — that's done by `analyze_submission_bg()` via `set_submission_complete`. So after the verification, `safety_reports.id=11` had the grade A report but `user_submissions.id=7` still had the original grade D fallback. Net effect: scanning the barcode fresh returns grade A from cache, but the SubmissionsPage view of id=7 still showed grade D.

Fixed with a one-off SQL via Python asyncpg (Railway's web SQL editor rejected the subquery-in-UPDATE form with a syntax error):

```python
src = await conn.fetchrow(
    "SELECT id, report::text AS report_json FROM safety_reports "
    "WHERE barcode='8809838658313' ORDER BY id DESC LIMIT 1"
)
await conn.execute(
    "UPDATE user_submissions SET report = $1::jsonb WHERE id = 7",
    src['report_json'],
)
```

Before: grade D / score 0 / 0 ingredients. After: grade A / score 85 / 41 ingredients. Status `complete` unchanged.

---

## Dogfooding notes correction

Prior body wash row said "Photo extraction worked (42 ingredients via image agent)". Rewritten to make clear:
- The submission was a front-of-product photo + pasted ingredient text
- The 42 ingredients came from the pasted text, not OCR
- Image-agent ingredient OCR on a dense INCI label is still untested

Added a "How to validate image-agent OCR quality" workflow section pointing at `diff_extraction.py` so future test scans have a documented path from photo to quality numbers.

---

## Files touched

```
backend/agents/scanner.py                       Phase 2 stream() instead of create() (lines 432-467)
backend/scratch/__init__.py                     new
backend/scratch/repro_phase2.py                 new — bisecting harness, kept for regression
backend/scratch/diff_extraction.py              new — extraction quality diff helper
CLAUDE.md                                       Phase 2 disconnect section: known issue → resolved RCA
docs/dogfooding-notes.md                        body wash row correction + diff-helper workflow section
TODO.md                                         Phase 2 → resolved, new comma-split Open issue, Session J entry
docs/history/SESSION_J_2026-05-25_PHASE_2_STREAMING_FIX.md   this file
```

---

## Commits (chronological)

- `d5874db` — `fix: Phase 2 streaming unblocks Opus on full system prompt`
- `7e4bff9` — `Add image-agent extraction diff helper`

Both pushed to `origin/feature/capacitor-mobile`.

---

## Decisions worth keeping

- **Bisection > guessing.** Three prior debugging sessions ruled out the wrong things via targeted-but-uncontrolled experiments. The harness ruled out the right things in 30 minutes because each variant changed exactly one variable. Pattern worth reaching for whenever a bug has >=3 plausible causes — write the variant table FIRST, then run.
- **Streaming for any long Opus call behind a load balancer.** The 60s cutoff is not specific to our payload — it'll bite any non-streaming Opus call that exceeds TTFB budget. Use `messages.stream()` by default for synthesis-class calls; reserve `messages.create()` for short responses (~<10s of generation).
- **Keep scratch/ harnesses around.** `repro_phase2.py` cost ~$0.50 to produce and now lives forever as a one-command regression check. `diff_extraction.py` turns a fuzzy "is OCR working?" question into a precise numeric answer. Both are dev-only tools that don't ship to production; their long-tail value is in fast re-validation.
- **Don't conflate `safety_reports.report` with `user_submissions.report`.** They're written by different code paths (`analyze_product` vs `analyze_submission_bg`). If you bypass the BG task by calling `analyze_product` directly, you have to manually sync the submission row.
