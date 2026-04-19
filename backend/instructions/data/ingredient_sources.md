# Ingredient Data Sources

## Overview

This document describes every external data source used to populate and validate the SafeScan ingredient database. Agents should use this reference when deciding which source to trust for a given field, how fresh the data is, and how to access or refresh it.

---

## 1. CosIng — EU Cosmetic Ingredients Database

**What it is:** CosIng (Cosmetic Ingredient) is the official European Commission database for cosmetic substances and ingredients. Maintained by DG GROW (Directorate-General for Internal Market, Industry, Entrepreneurship and SMEs). It is the authoritative source for EU cosmetics regulatory status.

**URL:** https://ec.europa.eu/growth/tools-databases/cosing/

**Coverage:**
- Approximately 26,000+ cosmetic substances
- All substances listed in the Annexes of EU Cosmetics Regulation EC No 1223/2009:
  - Annex II: Prohibited substances (banned)
  - Annex III: Restricted substances (allowed with conditions)
  - Annex IV: Colorants
  - Annex V: Preservatives
  - Annex VI: UV filters
- INCI names, CAS numbers, EC numbers, function descriptions

**Update frequency:** Updated when new SCCS (Scientific Committee on Consumer Safety) opinions are published or when regulation amendments are passed. Major updates are infrequent (months to years); minor corrections are occasional.

**Data quality:** Authoritative for EU regulatory status. INCI names are the gold standard. Does not contain safety scores or toxicology data directly — only regulatory classification.

**Access:**
- Web search interface at the URL above (rate-limited, not suitable for bulk queries)
- No official bulk export API. Community CSV exports are circulated periodically.
- Store the latest CSV export in `data/cosing_export.csv`. Filename should include the export date.

**Fields of interest:** INCI Name, CAS No., EC No., Function, Annex, Restriction/Conditions, Reference

**Trust level:** 4/5 — Highest for EU regulatory status. Does not cover food.

---

## 2. EFSA Food Additives Register

**What it is:** The European Food Safety Authority's register of food additives authorized for use in the EU. Covers all E-numbered food additives with their Acceptable Daily Intake (ADI) values, authorized uses, and re-evaluation status.

**URL:** https://www.efsa.europa.eu/en/data/data-on-food-additives

**Coverage:**
- All EU-authorized food additives (E100–E1521 range)
- ADI values (mg/kg body weight/day)
- Authorized food categories and maximum use levels
- Re-evaluation schedule and outcomes (ongoing programme since 2010)

**Update frequency:** The register is updated as new opinions are published. Re-evaluation opinions are published continuously. Full register refresh: approximately annually.

**Data quality:** Authoritative for food additives within the EU. ADI and use-level data is precise. Re-evaluation status important — "under re-evaluation" means current data may change.

**Access:**
- Excel/CSV download from the data URL above. Format changes periodically.
- Also available via Open Data APIs on data.europa.eu.

**Fields of interest:** E-number, Substance name, Function, ADI (mg/kg bw/day), Authorization status, EFSA opinion reference, Conditions/Restrictions

**Trust level:** 3/5 — Authoritative for food additives, EU-only scope.

---

## 3. IARC Carcinogen Classifications

**What it is:** The International Agency for Research on Cancer (IARC), part of WHO, classifies substances by their evidence for carcinogenicity in humans. The IARC Monographs programme is the global reference for carcinogen classification.

**URL:** https://monographs.iarc.who.int/

**Classification Groups:**

| Group | Meaning | Example Substances |
|---|---|---|
| Group 1 | Carcinogenic to humans — sufficient evidence | Formaldehyde, Benzene, Asbestos, Aflatoxins |
| Group 2A | Probably carcinogenic to humans — limited evidence in humans, sufficient in animals | Red meat, Nitrite in processed meat, Acrylamide |
| Group 2B | Possibly carcinogenic to humans — limited evidence | Aloe vera (whole leaf extract), Talc, Coffee (reversed 2016) |
| Group 3 | Not classifiable as to carcinogenicity | Most common chemicals not classified above |

**Note on Group 2B:** This classification indicates limited evidence and does NOT mean the substance is dangerous at normal use levels. Many Group 2B agents are common foods and substances. Context and exposure level matter greatly.

**Coverage:** ~1,200 agents evaluated as of 2024. New monographs published in batches.

**Update frequency:** New volumes published several times per year, each covering a batch of agents.

**Access:** Searchable at monographs.iarc.who.int. PDF monographs are the primary deliverable. No structured API; data must be curated manually or from secondary sources.

**Fields of interest:** Agent name, Group, Evaluation volume and year, CAS number

**Trust level:** Specialized — authoritative for carcinogenicity classification only. Use in combination with other sources.

---

## 4. Open Food Facts

**What it is:** A free, collaborative, non-profit food products database. The "Wikipedia of food". Contains product metadata and ingredient lists for hundreds of thousands of products worldwide, crowd-sourced and partially verified.

**URL:** https://world.openfoodfacts.org/

**Coverage:**
- 3 million+ food products (as of 2024)
- Global coverage; best coverage for EU and North American markets
- Barcode → product name, brand, ingredient list, Nutri-Score, NOVA group, additives, allergens, nutrition data, images

**Data quality:**
- Variable. Crowd-sourced entries may contain errors, outdated information, or incomplete data.
- Nutri-Score and NOVA group computed algorithmically by OFF from available data; may be incorrect if input data is wrong.
- Ingredient lists often in the language of the product's origin market.
- Best practice: treat as a starting point, verify critical fields (especially ingredients) from other sources or product images.

**Access:**
- **API**: `https://world.openfoodfacts.org/api/v0/product/{barcode}.json`
- **Delta files**: `https://world.openfoodfacts.org/data/delta/` (JSONL by date)
- **Full dump**: `https://world.openfoodfacts.org/data/` (multi-GB, updated monthly)

**Rate limits:** API is free but rate-limited. Respect robots.txt. Use bulk downloads for batch processing.

**Trust level:** 1/5 for safety classification. 3/5 for product existence and basic metadata.

---

## 5. Open Beauty Facts

**What it is:** The cosmetic equivalent of Open Food Facts. A free, collaborative database of cosmetic and personal care products.

**URL:** https://world.openbeautyfacts.org/

**Coverage:**
- 200,000+ cosmetic products (as of 2024)
- Barcode → product name, brand, ingredient list (INCI format), categories, images
- Coverage skewed toward European and globally-distributed brands

**Data quality:**
- Similar caveats to Open Food Facts: crowd-sourced, variable quality.
- INCI ingredient lists are generally more reliable than food ingredient lists because INCI is a standardized format.
- Does not provide safety classifications or regulatory status directly.

**Access:**
- **API**: `https://world.openbeautyfacts.org/api/v0/product/{barcode}.json`
- **Delta files**: `https://world.openbeautyfacts.org/data/delta/`

**Trust level:** 2/5 for cosmetic product metadata. Do not use for safety classification.

---

## Trust Hierarchy

When data from multiple sources conflicts, apply this priority order:

```
1. user          (rank 5) — manually verified by a human reviewer; highest trust
2. cosing        (rank 4) — official EU regulatory data for cosmetics
3. efsa          (rank 3) — official EU regulatory data for food additives
4. obf           (rank 2) — crowd-sourced cosmetic data; use for metadata only
5. off           (rank 1) — crowd-sourced food data; use for metadata only
```

### Application Rules

| Field | Trusted Source |
|---|---|
| `eu_status` for cosmetic ingredients | CosIng exclusively |
| `eu_status` for food additives | EFSA exclusively |
| `safety_level`, `concerns` for cosmetics | CosIng → IARC → OBF |
| `safety_level`, `concerns` for food | EFSA → IARC → OFF |
| `inci_name` | CosIng → OBF |
| `e_number` | EFSA → OFF |
| `name`, `brand`, `image_url` for products | Most recent non-null, any source |
| `score_penalty` | Derived from above; never taken directly from crowd sources |

### Conflict Logging

When sources conflict on safety-critical fields (`safety_level`, `eu_status`, `score_penalty`), log:
```
CONFLICT: ingredient "<name>", field "<field>", existing_source="<source>/<rank>", new_source="<source>/<rank>", existing_value="<val>", new_value="<val>", action="kept_existing | updated"
```
This log should be reviewable by human reviewers.
