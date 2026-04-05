# Scoring Rubric

## Overview

Every product receives a safety score from **0 to 100** and a letter grade. The score starts at 100 and penalties are subtracted. Bonuses may be added. The final score is clamped to 0–100.

There is no E grade. D (0–24) is the worst grade.

---

## Grade Thresholds

| Grade | Score Range | Color | Meaning |
|---|---|---|---|
| A | 75–100 | Green | Excellent — mostly natural/safe ingredients, minimal concerns |
| B | 50–74 | Light Green | Good — minor concerns only, generally safe for regular use |
| C | 25–49 | Orange | Average — several concerning ingredients, consider frequency of use |
| D | 0–24 | Red | Poor — significant safety concerns, banned substances, or extreme processing |

---

## Base Score

All products start at **100 points**.

Apply penalties first, then bonuses. Clamp the final result: `score = max(0, min(100, score))`.

---

## Penalty Table — Food Products

### Per-Ingredient Penalties

| Condition | Penalty per Occurrence |
|---|---|
| Ingredient with `safety_level = 'avoid'` | −15 pts |
| Ingredient with `safety_level = 'caution'` | −7 pts |
| Declared allergen (`is_allergen = true`) | −3 pts |

### Additive Category Penalties (applied once per category, not per ingredient)

| Category | Penalty |
|---|---|
| Artificial colorant present (E100–E199 range) | −5 pts |
| Artificial preservative present (E200–E299 range) | −5 pts |
| Artificial sweetener present (E900–E999 range) | −5 pts |

### Processing Level Penalties (NOVA)

| NOVA Group | Description | Penalty |
|---|---|---|
| NOVA 4 | Ultra-processed food | −20 pts |
| NOVA 3 | Processed food | −10 pts |
| NOVA 1–2 | Minimally processed / Culinary ingredient | 0 pts |
| Unknown / not available | No penalty applied | 0 pts |

### Nutritional Grade Penalties (Nutri-Score)

| Nutri-Score | Penalty |
|---|---|
| E | −20 pts |
| D | −10 pts |
| C | −5 pts |
| B | 0 pts |
| A | 0 pts |
| Unknown / not available | 0 pts |

---

## Penalty Table — Cosmetic Products

### Per-Ingredient Penalties

| Condition | Penalty per Occurrence | Notes |
|---|---|---|
| EU-banned substance (`eu_status = 'banned'`) | −30 pts AND score floor to D (max 24) | Applied immediately; score cannot exceed 24 |
| EU-restricted substance (`eu_status = 'restricted'`) | −15 pts | |
| Endocrine disruptor (`concerns` includes `endocrine_disruptor`) | −20 pts | |
| IARC Group 1 carcinogen | −25 pts | Confirmed carcinogen in humans |
| IARC Group 2A carcinogen | −25 pts | Probable carcinogen in humans |
| IARC Group 2B carcinogen (`concerns` includes `carcinogen`) | −12 pts | Possible carcinogen |
| Paraben (`concerns` includes `paraben`) | −10 pts | Each distinct paraben type |
| SLS — Sodium Lauryl Sulfate (`concerns` includes `sls`) | −8 pts | |
| SLES — Sodium Laureth Sulfate (`concerns` includes `sles`) | −8 pts | |
| Formaldehyde releaser (`concerns` includes `formaldehyde_releaser`) | −20 pts | |
| Undisclosed fragrance blend (`is_fragrance_blend = true`) | −5 pts | Listed as "Parfum" or "Fragrance" |
| Declared allergen | −3 pts | |

### EU-Banned Substance Floor Rule

If any ingredient has `eu_status = 'banned'`:
1. Apply the −30 pt penalty.
2. Apply all other penalties normally.
3. **Clamp the score to a maximum of 24** — the product cannot score above D regardless of bonuses.
4. Set `eu_banned_floor_applied: true` in `scoring_breakdown`.

This rule ensures that a product with even one banned ingredient always receives a D grade.

### Penalty Stacking — Cosmetics

Multiple penalties stack additively on the same ingredient. Example: an ingredient that is both an endocrine disruptor and a paraben receives −20 (endocrine) + −10 (paraben) = −30 pts.

However: use the per-ingredient `score_penalty` field from the `ingredients` table as the authoritative penalty override when it is non-zero. The categorical penalties above are defaults applied when `score_penalty = 0`.

Do not double-count: if the `score_penalty` field already encodes all concerns, do not also apply categorical penalties.

---

## Bonus Points — All Product Types

| Condition | Bonus |
|---|---|
| Certified organic (any recognised certification: EU Organic, USDA Organic, Ecocert, Soil Association, etc.) | +5 pts |
| Short ingredient list — 8 or fewer total ingredients | +5 pts |
| All ingredients classified `safety_level = 'safe'` with no concerns | +3 pts |

Bonuses stack. Maximum possible bonus: +13 pts.

Bonuses are applied **after** all penalties, but **before** clamping.

---

## Score Computation Algorithm

```
score = 100

# Apply food or cosmetic penalties (based on product_type)
for ingredient in resolved_ingredients:
    if ingredient.score_penalty > 0:
        score -= ingredient.score_penalty
    else:
        # Apply categorical defaults
        score -= categorical_penalty(ingredient)

# Apply meta penalties (food only)
score -= nova_penalty(nova_group)
score -= nutriscore_penalty(nutriscore)
score -= additive_category_penalties(ingredients)

# Apply bonuses
if certified_organic:
    score += 5
if len(ingredients) <= 8:
    score += 5
if all(i.safety_level == 'safe' for i in resolved_ingredients):
    score += 3

# Clamp
score = max(0, min(100, score))

# EU-banned floor (cosmetics only)
if any(i.eu_status == 'banned' for i in resolved_ingredients):
    score = min(score, 24)

# Derive grade
if score >= 75:
    grade = 'A'
elif score >= 50:
    grade = 'B'
elif score >= 25:
    grade = 'C'
else:
    grade = 'D'
```

---

## Score Floor

The minimum score is **0**. Penalties cannot make a score negative.

The maximum score is **100** (before bonuses are applied, then re-clamped).

If a product has a banned EU substance, the effective maximum is **24** (D grade ceiling).

---

## Examples

### Example 1: Clean Food Product

- NOVA group 1 (unprocessed)
- Nutri-Score A
- 5 ingredients, all `safety_level = 'safe'`
- Certified organic

```
score = 100
No penalties.
Bonuses: +5 (organic) + 5 (short list) + 3 (all safe) = +13
score = 100 + 13 = 113 → clamped to 100
Grade: A (100)
```

### Example 2: Ultra-Processed Snack

- NOVA group 4: −20
- Nutri-Score D: −10
- 2 × 'avoid' additives: −30
- 4 × 'caution' additives: −28
- 2 × artificial colorants (category): −5
- 2 × allergens: −6

```
score = 100 − 20 − 10 − 30 − 28 − 5 − 6 = 1
Grade: D (1)
```

### Example 3: Cosmetic with Banned Substance

- 1 banned substance: −30 + floor to max 24
- 1 endocrine disruptor: −20
- Parfum (undisclosed): −5

```
score = 100 − 30 − 20 − 5 = 45 → then clamped to 24 (banned floor)
Grade: D (24)
```

### Example 4: Typical Shampoo (Grade B)

- SLES: −8
- Parfum: −5
- 1 × 'caution' preservative: −7
- 12 ingredients (no short-list bonus)

```
score = 100 − 8 − 5 − 7 = 80
Grade: A (80)
```

Wait — this result shows why nuance matters. A typical shampoo with SLES might score A. If additional concerns exist (e.g., another sensitizer), the score drops. The rubric is arithmetic; the Analysis Agent adds qualitative context.
