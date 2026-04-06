# SafeScan — Best Practices Update Instructions

This document covers two areas: (1) code and agent instruction updates to align with the latest Claude API best practices, and (2) new data sources to expand product coverage.

---

## Completion Status

| Part | Status | Session |
|------|--------|---------|
| Part 1 — Claude API & Code Updates | ✅ Complete | Sessions 1–2 |
| Part 2 — Agent Instruction Improvements | ✅ Complete | Session 2 |
| Part 3 — Additional Data Sources | 🔄 In Progress (1+2 done Session A, 5 done Session B, 3+4+6–10 pending) | Dedicated session per source |
| Part 4 — Quick Wins Checklist | ✅ Complete (except IARC/Prop65 deferred to Part 3) | Sessions 1–2 |

**Session 1** (previous): 1.2, 1.3, 1.5, 1.6, Part 4 code quick wins
**Session 2** (this session): 1.1 verified, 1.4 verified (no prefilling), 1.7 verified, Part 2 all five instruction files

---

---

## Part 1: Claude API & Code Updates

### 1.1 Migrate `output_format` → `output_config.format`

**What changed:** Anthropic moved structured outputs from beta to GA. The `output_format` parameter is deprecated in favor of `output_config.format`. The beta header `structured-outputs-2025-11-13` is no longer required. The Python SDK's `messages.parse()` still accepts `output_format` as a convenience, but the raw `.create()` calls should use `output_config`.

**Files to update:**

`backend/agents/scanner.py` — Phase 2 call:
```python
# BEFORE (deprecated)
structured_response = await client.messages.parse(
    model="claude-opus-4-6",
    max_tokens=4096,
    thinking={"type": "adaptive"},
    system=SYSTEM_PROMPT,
    messages=messages,
    output_format=SafetyReport,  # deprecated param name
)

# AFTER (current)
structured_response = await client.messages.parse(
    model="claude-opus-4-6",
    max_tokens=4096,
    thinking={"type": "adaptive"},
    system=SYSTEM_PROMPT,
    messages=messages,
    output_format=SafetyReport,  # SDK .parse() still accepts this
)
```

The SDK's `.parse()` method handles the translation internally, so this is low-urgency. However, if you ever switch to raw `.create()` with a JSON schema, use:
```python
output_config={
    "format": {
        "type": "json_schema",
        "schema": SafetyReport.model_json_schema()
    }
}
```

**Also update `backend/db/ingredient_resolver.py`** — the `_classify_with_claude` function uses the sync client with `.parse()`. Same migration applies. Verify it uses `output_format=_ClassificationBatch` (the SDK handles the rest).


### 1.2 Add `thinking.display: "omitted"` to Phase 1

**What changed:** Anthropic added a `display` field for extended thinking that lets you omit thinking content from responses while preserving the signature for multi-turn continuity. This directly solves the Phase 1 → Phase 2 round-trip problem documented in CLAUDE.md.

**Current workaround:** Phase 1 has no `thinking=` parameter at all, which means you lose any benefit of reasoning during product lookup.

**Proposed change in `scanner.py`:**
```python
# Phase 1: tool use loop — now safe to enable thinking
response = await client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    tools=[LOOKUP_TOOL],
    messages=messages,
    thinking={
        "type": "adaptive",
        "display": "omitted"   # thinking blocks come back empty, 
    },                         # signature preserved, no bloat in Phase 2
)
```

**Update CLAUDE.md** to replace the "Phase 1 thinking" warning:
```
**Phase 1 thinking**: Uses `thinking={"type": "adaptive", "display": "omitted"}` 
to avoid large thinking blocks bloating the Phase 2 round-trip. Never remove the 
`display: "omitted"` setting — full thinking content in Phase 1 breaks Phase 2.
```


### 1.3 Cost optimization: Use Sonnet 4.6 for cheaper agent tasks

**Rationale:** Opus 4.6 costs $15/$75 per MTok. Sonnet 4.6 costs $3/$15. Several SafeScan agent tasks don't need Opus-level reasoning.

**Candidates for Sonnet 4.6:**

| Task | Current model | Recommended | Reasoning |
|------|--------------|-------------|-----------|
| `_extract_product_info` (image agent) | Opus 4.6 | **Sonnet 4.6** | OCR + structured extraction — Sonnet handles this well |
| `_parse_ingredients` (image agent) | Opus 4.6 | **Sonnet 4.6** | Parsing ingredient text from photos is mechanical |
| `_classify_with_claude` (resolver) | Opus 4.6 | **Sonnet 4.6** | Single-ingredient classification, batched ≤10 |
| Phase 1 tool loop (scanner) | Opus 4.6 | **Sonnet 4.6** | Just calling lookup_product — no deep reasoning |
| Phase 2 structured output (scanner) | Opus 4.6 | **Keep Opus 4.6** | Full safety analysis requires deep reasoning |

**Implementation:** Add a config constant at the top of each agent file:
```python
# models.py or config.py
MODEL_HEAVY = "claude-opus-4-6"       # complex safety analysis
MODEL_LIGHT = "claude-sonnet-4-6"     # extraction, parsing, classification
```

This alone could cut API costs by 50-70% since Phase 2 (the expensive call) is the only one that truly needs Opus.


### 1.4 Remove prefilling if present anywhere

**What changed:** Claude Opus 4.6 and Sonnet 4.5+ no longer support assistant message prefilling. Any trailing `role: "assistant"` message causes a 400 error.

**Action:** Search the codebase for any messages array ending with `{"role": "assistant", "content": ...}`. The current scanner.py doesn't appear to use prefilling, but verify in all agent files.


### 1.5 Prompt caching for system prompts

**What changed:** Prompt caching is now automatic — no beta header needed. Since SafeScan loads system prompts at module import time (not per-request), the same system prompt text is sent on every call.

**Action:** Add `cache_control` to system prompt blocks to explicitly opt into caching:
```python
response = await client.messages.create(
    model=MODEL_LIGHT,
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=messages,
)
```

This caches the system prompt for 5 minutes, saving input tokens on repeated scans. Particularly valuable for the Phase 1 loop which makes multiple API calls per scan.


### 1.6 Add error handling for structured output failures

The current `scanner.py` handles `parsed_output is None` but doesn't handle the case where the structured output call itself fails (e.g., schema compilation error, timeout).

```python
try:
    structured_response = await client.messages.parse(...)
    report = structured_response.parsed_output
except anthropic.APIError as e:
    print(f"  [CLAUDE] Structured output failed: {e}")
    # Fall back to unstructured analysis or return error report
    report = None

if report is None:
    return SafetyReport(
        product_name="Unknown Product",
        barcode=barcode,
        ...
    )
```


### 1.7 Update `products.source` CHECK constraint

The schema currently allows: `'off', 'obf', 'user', 'image_scan'`. But the USDA and OpenFDA importers write `'usda'` and `'openfda'` respectively. CLAUDE.md documents this but the schema.sql may be out of sync.

**Verify and update:**
```sql
ALTER TABLE products DROP CONSTRAINT IF EXISTS products_source_check;
ALTER TABLE products ADD CONSTRAINT products_source_check 
    CHECK (source IN ('off', 'obf', 'user', 'image_scan', 'usda', 'openfda'));
```

---

## Part 2: Agent Instruction Improvements

### 2.1 `instructions/agents/analysis_agent.md`

**Add a "Confidence Calibration" section** after the classification rules:
```markdown
## Confidence Calibration

When classifying ingredients, explicitly state your confidence level:
- **High confidence**: Ingredient is well-known, appears in major regulatory databases, 
  you have clear training knowledge of its safety profile.
- **Medium confidence**: Ingredient is recognizable but you're uncertain about specific 
  regulatory status or concentration-dependent effects.
- **Low confidence**: Novel compound, proprietary blend name, or ambiguous abbreviation.

For medium/low confidence classifications, set `score_penalty` conservatively 
(higher than you might otherwise) and include your uncertainty in `notes`.
```

**Add structured output guidance:**
```markdown
## Output Format Compliance

Your output MUST conform exactly to the SafetyReport Pydantic schema. Key rules:
- `grade` must be one of: "A", "B", "C", "D" — there is no "E" grade
- `score` must be 0–100 (integer)
- `safety_level` must be one of: "safe", "caution", "avoid", "unknown"
- `concerns` array entries should come from the canonical concern tags list
- Never invent new fields; use `notes` for anything that doesn't fit the schema
```

### 2.2 `instructions/agents/barcode_agent.md`

**Add timeout and retry guidance:**
```markdown
## Timeout and Retry Policy

| Step | Timeout | Retries | Backoff |
|------|---------|---------|---------|
| Local DB | 2s | 0 | — |
| Open Food Facts API | 8s | 1 | 3s |
| Open Beauty Facts API | 8s | 1 | 3s |
| User submissions lookup | 2s | 0 | — |

On any network error, log the error with the step name and proceed to the next step. 
Never let a single API failure block the entire pipeline.
```

### 2.3 `instructions/data/scoring_rubric.md`

**Clarify the "no E grade" rule more prominently:**
```markdown
## IMPORTANT: Grade Scale

The grade scale is A/B/C/D only. There is NO "E" grade.
- If the model outputs grade "E", it is an error — clamp to "D"
- The scanner.py Phase 2 prompt mentions "A/B/C/D/E" — this should be 
  corrected to "A/B/C/D"
```

**This is a real bug:** In `scanner.py`, the Phase 2 prompt says:
```
"A=75-100 (excellent), B=50-74 (good), C=25-49 (average), D=0-24 (poor)."
```
But the fallback report in `scanner.py` sets `grade="E"` which contradicts the rubric. Fix the fallback to use `grade="D"`.

### 2.4 `instructions/agents/image_agent.md`

**Add guidance on common OCR failure patterns:**
```markdown
## Common OCR Challenges

- **Curved surfaces**: Bottles and tubes distort text. Focus on the flattest 
  visible area.
- **Metallic/holographic packaging**: Glare causes character misrecognition. 
  Note this in `low_confidence_reasons`.
- **Micro text**: Ingredient lists are often in very small font. If individual 
  characters are ambiguous, prefer the more common ingredient spelling.
- **Color-on-color**: Light text on light backgrounds or dark on dark. Adjust 
  contrast mentally and flag low confidence.
```

### 2.5 `instructions/agents/ingredient_parser.md`

**Add INCI normalization rules:**
```markdown
## INCI Name Normalization

Before returning ingredient names, apply these normalizations:
1. Strip leading/trailing whitespace
2. Collapse multiple spaces to single space
3. Remove trailing periods or semicolons
4. Normalize common variations: "Aqua/Water" → "Aqua (Water)"
5. Preserve parenthetical qualifiers: "Tocopherol (Vitamin E)" stays as-is
6. Remove quantity annotations: "Sugar (15%)" → "Sugar" with note "15%"
7. Handle "and" conjunctions: "Sodium Lauryl and Laureth Sulfate" → 
   two separate entries
```

---

## Part 3: Additional Data Sources

### 3.1 Food Products — New Sources

#### A. FoodData Central — Full Database (not just branded)
**What:** You currently import only `branded_food.csv` from USDA. The full FoodData Central also includes SR Legacy (~8K common foods), Foundation Foods (~2K with detailed nutrient data), and Survey Foods (NHANES). These provide reference-grade nutrient composition data.

**URL:** `https://fdc.nal.usda.gov/download-datasets`

**Value:** Better nutrient-level analysis for generic/unbranded products.

#### B. EU Food Additives Database (OpenData)
**What:** Machine-readable EU food additive authorizations with maximum permitted levels per food category.

**URL:** `https://ec.europa.eu/food/food-feed-portal/screen/food-additives/search`

**Value:** More granular than the EFSA register — includes per-category maximum levels, which allows concentration-aware scoring (e.g., "E211 is safe in beverages at 150mg/L but excessive in baked goods").

#### C. California Proposition 65 List
**What:** California's list of chemicals known to cause cancer, birth defects, or reproductive harm. ~900 chemicals updated regularly.

**URL:** `https://oehha.ca.gov/proposition-65/proposition-65-list` (downloadable as Excel)

**Value:** Cross-reference with ingredients for a US-market safety signal. Prop 65 listings are a strong consumer-facing safety flag.

**Implementation:** New importer `prop65_importer.py`. Map chemicals to existing `ingredients` rows via CAS number or name match. Add a `prop65_listed` boolean or add `"prop65"` to the `concerns` array.

#### D. RASFF (EU Rapid Alert System for Food and Feed)
**What:** Real-time notifications about food safety issues detected in the EU market. Includes contamination events, unauthorized additives, and allergen mislabeling.

**URL:** `https://webgate.ec.europa.eu/rasff-window/screen/search` (API available)

**Value:** Supplements the FDA recall data you already have. Gives you EU-side recall/alert coverage.

**Implementation:** New importer or real-time checker similar to `recall_store.py`. Query by product category or ingredient name.

#### E. GS1 / UPC Databases
**What:** Commercial barcode databases with product metadata. Options include UPCitemdb (free tier: 100 lookups/day), Barcode Lookup API (free tier available), and the Open Product Data project.

**URLs:**
- `https://www.upcitemdb.com/wp/docs/` (free API, 100/day)
- `https://www.barcodelookup.com/api` (paid, comprehensive)
- `https://product-open-data.com/` (open source)

**Value:** Fallback for barcodes not found in OFF/OBF/USDA. Gets you product name + brand + category even when ingredient data isn't available.

#### F. Nutritionix API
**What:** Comprehensive US food database with 900K+ items, including restaurant and fast food items that OFF doesn't cover well.

**URL:** `https://www.nutritionix.com/business/api`

**Value:** Fills the restaurant/fast-food gap. Excellent for branded food items common in the US market.


### 3.2 Cosmetic Products — New Sources

#### A. EWG Skin Deep Database
**What:** The Environmental Working Group maintains a database of ~90K personal care products with hazard scores for ~2,500 ingredients.

**URL:** `https://www.ewg.org/skindeep/`

**Value:** Pre-computed hazard scores from a well-known consumer safety organization. Their ingredient hazard ratings could be cross-referenced with your `ingredients` table.

**Caveat:** EWG doesn't provide a public bulk API. Data would need to be obtained via partnership or periodic scraping (check their ToS). They do publish ingredient-level data pages that are publicly accessible.

#### B. ECHA REACH Database
**What:** The European Chemicals Agency's Registration, Evaluation, Authorisation and Restriction of Chemicals database. Contains detailed toxicological and ecotoxicological data for chemicals manufactured or imported in the EU in quantities > 1 ton/year.

**URL:** `https://echa.europa.eu/information-on-chemicals` (search API available)

**Value:** Authoritative for carcinogenicity, mutagenicity, reproductive toxicity (CMR) classifications. The SVHC (Substance of Very High Concern) candidate list is particularly useful — map it to `concerns: ["svhc"]`.

**Implementation:** ECHA provides a IUCLID-format bulk download and an API. Query by CAS number for ingredient-level lookups.

#### C. SCCS Opinions (Scientific Committee on Consumer Safety)
**What:** Individual scientific opinions on cosmetic ingredients published by the EU's SCCS. These are the actual safety evaluations that inform CosIng updates.

**URL:** `https://health.ec.europa.eu/scientific-committees/scientific-committee-consumer-safety-sccs/sccs-opinions_en`

**Value:** The most authoritative source for cosmetic ingredient safety. Each opinion includes margin of safety calculations, concentration limits, and specific risk scenarios. Reference these in `notes` for restricted/banned ingredients.

**Implementation:** These are PDF documents, not structured data. Maintain a curated index (JSON/CSV) mapping INCI names to SCCS opinion references and key conclusions. The sync worker already references SCCS — formalize this into a data file.

#### D. IFRA (International Fragrance Association) Standards
**What:** IFRA publishes usage standards for fragrance ingredients, including maximum concentration limits by product category (leave-on vs rinse-off, facial vs body, etc.).

**URL:** `https://ifrafragrance.org/safe-use/library`

**Value:** Critical for fragrance ingredient analysis. Currently, SafeScan flags undisclosed fragrance blends with a flat −5 penalty. IFRA data would allow nuanced scoring based on specific fragrance allergens and their concentrations.

#### E. CosDNA / Cosmily Ingredient Database
**What:** Community-maintained cosmetic ingredient databases with safety ratings, comedogenicity scores, and irritation potential.

**URLs:**
- `https://www.cosdna.com/` 
- `https://cosmily.com/`

**Value:** Comedogenicity and irritation ratings are useful consumer-facing metrics not covered by regulatory databases. These databases also have good alias coverage for INCI names.

**Caveat:** Community data — lower trust than CosIng/SCCS. Use to fill gaps, not override regulatory data. Fits in the trust hierarchy below OBF.

#### F. Paula's Choice Ingredient Dictionary
**What:** A well-researched ingredient reference with plain-language safety assessments for ~2,000 cosmetic ingredients.

**URL:** `https://www.paulaschoice.com/ingredient-dictionary`

**Value:** Good consumer-facing descriptions for the `notes` field. Particularly useful for explaining why an ingredient is classified as "caution" in terms a consumer can understand.

#### G. Health Canada Cosmetic Ingredient Hotlist
**What:** Canada's list of prohibited and restricted cosmetic ingredients. Largely mirrors the EU list but with some differences (e.g., different concentration limits for certain preservatives).

**URL:** `https://www.canada.ca/en/health-canada/services/consumer-product-safety/cosmetics/cosmetic-ingredient-hotlist-prohibited-restricted-ingredients.html` (downloadable)

**Value:** A second regulatory voice beyond the EU. Differences between EU and Canadian limits could be surfaced as additional context.


### 3.3 Cross-Category Sources

#### A. PubChem
**What:** NIH's open chemistry database with safety data, toxicity information, and bioassay results for millions of compounds.

**URL:** `https://pubchem.ncbi.nlm.nih.gov/` (REST API: `https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest`)

**Value:** Lookup by CAS number to get GHS hazard classifications, LD50 values, and links to toxicological studies. Useful as a "deep dive" data source when Claude needs to classify a truly unknown ingredient.

#### B. IARC Monographs (Agents Classified by the IARC)
**What:** The International Agency for Research on Cancer's classification of substances by carcinogenicity (Group 1, 2A, 2B, 3, or "not classifiable").

**URL:** `https://monographs.iarc.who.int/agents-classified-by-the-iarc/` (downloadable list)

**Value:** You already reference IARC groups in the scoring rubric. Import the full list as structured data so the local analyzer can apply carcinogen penalties without needing Claude.

**Implementation:** Download the IARC agents list, map to `ingredients` by CAS number or name. Add `iarc_group` column to `ingredients` table or store in `concerns` as `"iarc_group_1"`, `"iarc_group_2a"`, etc.


### 3.4 Priority Implementation Order

Based on coverage impact and implementation difficulty:

| Priority | Source | Type | Difficulty | Coverage Gain |
|----------|--------|------|------------|---------------|
| 1 | IARC Monographs | Food + Cosmetic | Easy | Structured carcinogen data for local analyzer |
| 2 | Prop 65 List | Food + Cosmetic | Easy | US safety signal, downloadable Excel |
| 3 | ECHA REACH/SVHC | Cosmetic | Medium | Authoritative EU chemical safety data |
| 4 | RASFF Alerts | Food | Medium | EU recall coverage alongside FDA |
| 5 | ~~UPCitemdb~~ ✅ Session B | Food + Cosmetic | Easy | Runtime fallback in `lookup_product()`; trial endpoint (100/day, no key); name+brand+category only |
| 6 | Health Canada Hotlist | Cosmetic | Easy | Second regulatory perspective |
| 7 | SCCS Opinions Index | Cosmetic | Medium | Reference-grade safety evidence |
| 8 | EWG Skin Deep | Cosmetic | Hard | Large ingredient coverage, no public API |
| 9 | Nutritionix | Food | Medium | US restaurant/fast food coverage |
| 10 | CosDNA/Cosmily | Cosmetic | Medium | Comedogenicity + irritation ratings |

---

## Part 4: Quick Wins Checklist

These are changes that can be made immediately with minimal risk:

- [x] Fix `grade="E"` fallback in `scanner.py` → change to `grade="D"`
- [x] Fix Phase 2 prompt: remove "/E" from "A/B/C/D/E" → "A/B/C/D"
- [x] Add `cache_control` to system prompt blocks in all agent files
- [x] Add `thinking.display: "omitted"` to Phase 1 in `scanner.py`
- [x] Verify `products.source` CHECK constraint includes `'usda'` and `'openfda'`
- [x] Switch image agent and ingredient resolver to Sonnet 4.6
- [x] Download IARC agents list and add to seed data *(completed Session A — 2026-04-05)*
- [x] Download Prop 65 list and add to seed data *(completed Session A — 2026-04-05)*
- [x] Add structured error handling around `messages.parse()` calls
- [x] Update CLAUDE.md with new best practices after changes
