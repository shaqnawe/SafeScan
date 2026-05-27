"""
Local safety report generator — zero Claude API calls.

Implements the scoring rubric from instructions/data/scoring_rubric.md exactly.
Used as the fast path when a product is found in the local DB.

Returns None when there is not enough resolved ingredient data to produce
a meaningful report (falls back to Claude in that case).
"""

from __future__ import annotations

import re
from typing import Any

from models import SafetyReport, IngredientAnalysis, ScoringBreakdown, ScoreLineItem
from agents.category import derive_category_slug

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Minimum resolved ingredients needed to produce a local report.
# Even 1 resolved ingredient is useful — score is still directional.
# Set to 0 to always use the local path for known products.
MIN_RESOLVED = 1

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_E_NUM_RE = re.compile(r'\bE(\d{3})[a-z]?\b', re.IGNORECASE)

_NOVA_PENALTY = {4: 20, 3: 10, 2: 0, 1: 0}
_NUTRISCORE_PENALTY = {'e': 20, 'd': 10, 'c': 5, 'b': 0, 'a': 0}


def _e_number_range(raw: str) -> int | None:
    """Return the numeric part of an E-number found in raw text, or None."""
    m = _E_NUM_RE.search(raw)
    return int(m.group(1)) if m else None


def _score_to_grade(score: int) -> str:
    if score >= 75: return 'A'
    if score >= 50: return 'B'
    if score >= 25: return 'C'
    return 'D'


def _carcinogen_penalty(concerns: list[str]) -> int:
    """
    Return the total point penalty for IARC / GHS / Prop 65 carcinogen,
    reproductive-toxin, and mutagen tags found in `concerns`.

    Tag families are mutually independent — a substance with both an IARC
    and a Prop 65 carcinogen listing pays both penalties. Within IARC, the
    severity tiers (Group 1/2A vs 2B) are mutually exclusive because they
    represent a single jurisdiction's verdict.

    Applied to both food and cosmetic paths so post-hoc enrichment from
    importers has uniform impact on scoring.
    """
    penalty = 0

    # IARC: Group 1 / 2A both indicate established or strong carcinogen
    # evidence and share the heavier penalty. Group 2B / legacy `carcinogen`
    # share the lighter penalty.
    if 'iarc_group_1' in concerns or 'iarc_group_2a' in concerns:
        penalty += 25
    elif 'iarc_group_2b' in concerns or 'carcinogen' in concerns:
        penalty += 12

    # GHS (CLP / CompTox)
    if 'ghs_carcinogen_cat1' in concerns:
        penalty += 25
    if 'ghs_carcinogen_cat2' in concerns:
        penalty += 12
    if 'ghs_reproductive_toxin' in concerns:
        penalty += 15
    if 'ghs_mutagen' in concerns:
        penalty += 12

    # California Prop 65
    if 'prop65_carcinogen' in concerns:
        penalty += 12
    if 'prop65_developmental_toxin' in concerns:
        penalty += 15
    if 'prop65_reproductive_toxin' in concerns:
        penalty += 15

    return penalty


def _ingredient_score_impact(ing: dict, product_type: str) -> int | None:
    """
    Per-ingredient point deduction (negative number) that this ingredient
    contributes to the product score. Mirrors the deductions inside
    `_compute_score`. Returns None if no deduction applies.

    Used to populate `IngredientAnalysis.score_impact` so the UI can show
    "Octocrylene  −15" next to each flagged ingredient.
    """
    safety           = ing.get('safety_level')
    if not safety:
        return None
    concerns         = ing.get('concerns') or []
    eu_status        = ing.get('eu_status') or 'unknown'
    explicit_penalty = ing.get('score_penalty') or 0

    impact = 0
    if product_type == 'food':
        if explicit_penalty > 0:
            impact += explicit_penalty
        elif safety == 'avoid':
            impact += 15
        elif safety == 'caution':
            impact += 7
        impact += _carcinogen_penalty(concerns)
    else:  # cosmetic
        if eu_status == 'banned':
            impact += 30
        elif explicit_penalty > 0:
            impact += explicit_penalty
        else:
            if eu_status == 'restricted':
                impact += 15
            if 'endocrine_disruptor' in concerns:
                impact += 20
            if 'paraben' in concerns:
                impact += 10
            if 'sls' in concerns:
                impact += 8
            if 'sles' in concerns:
                impact += 8
            if 'formaldehyde_releaser' in concerns:
                impact += 20
            if safety == 'avoid':
                impact += 15
            elif safety == 'caution':
                impact += 7
        impact += _carcinogen_penalty(concerns)
    if ing.get('is_allergen'):
        impact += 3

    return -impact if impact > 0 else None


def _compute_score(
    product_type: str,
    resolved: list[dict],
    total_ingredients: int,
    nova_group: int | None,
    nutriscore: str,
) -> tuple[int, ScoringBreakdown]:
    """
    Compute final score AND a per-line breakdown explaining how it got
    there. Per-ingredient deductions are tallied by category and emitted
    as one summary line per category to keep the breakdown UI-friendly
    (typically 4–8 lines vs. 50 ingredient rows).
    """
    score = 100
    has_banned = False

    # Per-ingredient deduction tallies, keyed by reason → (count, total points).
    # Aggregated and emitted at the end so the breakdown stays compact.
    tally: dict[str, list[int]] = {}  # reason → [count, total_neg_points]

    def add_ing(reason: str, points: int) -> None:
        """Record a per-ingredient deduction (points should be negative)."""
        if reason not in tally:
            tally[reason] = [0, 0]
        tally[reason][0] += 1
        tally[reason][1] += points

    for ing in resolved:
        safety = ing.get('safety_level')
        if not safety:
            continue

        concerns = ing.get('concerns') or []
        eu_status = ing.get('eu_status') or 'unknown'
        explicit_penalty = ing.get('score_penalty') or 0

        if product_type == 'food':
            if explicit_penalty > 0:
                score -= explicit_penalty
                add_ing('Flagged food ingredients', -explicit_penalty)
            elif safety == 'avoid':
                score -= 15
                add_ing('Ingredients to avoid', -15)
            elif safety == 'caution':
                score -= 7
                add_ing('Caution ingredients', -7)

            carc = _carcinogen_penalty(concerns)
            if carc > 0:
                score -= carc
                add_ing('Carcinogen / reproductive / mutagen tags', -carc)

        else:  # cosmetic
            if eu_status == 'banned':
                has_banned = True
                score -= 30
                add_ing('EU-banned cosmetic ingredients', -30)
            elif explicit_penalty > 0:
                score -= explicit_penalty
                add_ing('Flagged cosmetic ingredients', -explicit_penalty)
            else:
                if eu_status == 'restricted':
                    score -= 15
                    add_ing('EU-restricted ingredients', -15)
                if 'endocrine_disruptor' in concerns:
                    score -= 20
                    add_ing('Endocrine disruptors', -20)
                if 'paraben' in concerns:
                    score -= 10
                    add_ing('Parabens', -10)
                if 'sls' in concerns:
                    score -= 8
                    add_ing('Sulfates (SLS)', -8)
                if 'sles' in concerns:
                    score -= 8
                    add_ing('Sulfates (SLES)', -8)
                if 'formaldehyde_releaser' in concerns:
                    score -= 20
                    add_ing('Formaldehyde releasers', -20)
                if safety == 'avoid' and explicit_penalty == 0:
                    score -= 15
                    add_ing('Ingredients to avoid', -15)
                elif safety == 'caution' and explicit_penalty == 0:
                    score -= 7
                    add_ing('Caution ingredients', -7)

                carc = _carcinogen_penalty(concerns)
                if carc > 0:
                    score -= carc
                    add_ing('Carcinogen / reproductive / mutagen tags', -carc)

        if ing.get('is_allergen'):
            score -= 3
            add_ing('Allergens present', -3)

    # ── Food-only meta penalties ─────────────────────────────────────────────
    breakdown = ScoringBreakdown(base_score=100, final_score=0)

    # Roll up per-ingredient tallies into compact breakdown lines.
    for reason, (count, total) in tally.items():
        label = f"{reason} ({count})" if count > 1 else reason
        breakdown.penalties.append(ScoreLineItem(reason=label, points=total))

    if product_type == 'food':
        nova_pen = _NOVA_PENALTY.get(nova_group or 0, 0)
        if nova_pen > 0:
            score -= nova_pen
            label = (f"Ultra-processed food (NOVA {nova_group})"
                     if nova_group == 4 else f"Processed food (NOVA {nova_group})")
            breakdown.penalties.append(ScoreLineItem(reason=label, points=-nova_pen))

        nutri_pen = _NUTRISCORE_PENALTY.get(nutriscore.lower(), 0)
        if nutri_pen > 0:
            score -= nutri_pen
            breakdown.penalties.append(ScoreLineItem(
                reason=f"Poor nutritional quality (Nutri-Score {nutriscore.upper()})",
                points=-nutri_pen,
            ))

        e_ranges = set()
        for ing in resolved:
            n = _e_number_range(ing.get('e_number') or ing.get('name') or '')
            if n:
                if 100 <= n <= 199: e_ranges.add('artificial colorants')
                elif 200 <= n <= 299: e_ranges.add('artificial preservatives')
                elif 900 <= n <= 999: e_ranges.add('artificial sweeteners')
        if e_ranges:
            score -= len(e_ranges) * 5
            breakdown.penalties.append(ScoreLineItem(
                reason=f"Additive categories ({len(e_ranges)}): {', '.join(sorted(e_ranges))}",
                points=-len(e_ranges) * 5,
            ))

    # ── Bonuses ──────────────────────────────────────────────────────────────
    caution_or_worse = [i for i in resolved if i.get('safety_level') in ('caution', 'avoid')]

    if total_ingredients and total_ingredients <= 8:
        score += 5
        breakdown.bonuses.append(ScoreLineItem(
            reason=f"Short ingredient list ({total_ingredients})",
            points=5,
        ))
    if resolved and not caution_or_worse:
        score += 3
        breakdown.bonuses.append(ScoreLineItem(
            reason="All analyzed ingredients are safe",
            points=3,
        ))

    # ── Clamp ────────────────────────────────────────────────────────────────
    score = max(0, min(100, score))

    # ── EU-banned floor (cosmetics) ──────────────────────────────────────────
    if has_banned:
        clamped = min(score, 24)
        if clamped < score:
            breakdown.penalties.append(ScoreLineItem(
                reason="EU-banned floor applied (max grade D)",
                points=clamped - score,
            ))
        score = clamped
        breakdown.eu_banned_floor_applied = True

    breakdown.final_score = score
    return score, breakdown


# ---------------------------------------------------------------------------
# Prose generation
# ---------------------------------------------------------------------------

_NOVA_LABELS = {
    1: 'unprocessed or minimally processed',
    2: 'culinary ingredient',
    3: 'processed food',
    4: 'ultra-processed',
}

_NUTRISCORE_LABELS = {
    'a': 'excellent (Nutri-Score A)',
    'b': 'good (Nutri-Score B)',
    'c': 'average (Nutri-Score C)',
    'd': 'poor (Nutri-Score D)',
    'e': 'very poor (Nutri-Score E)',
}


def _generate_summary(
    name: str,
    brand: str,
    product_type: str,
    score: int,
    grade: str,
    resolved: list[dict],
    total: int,
    nova_group: int | None,
    nutriscore: str,
) -> str:
    safe    = sum(1 for i in resolved if i.get('safety_level') == 'safe')
    caution = sum(1 for i in resolved if i.get('safety_level') == 'caution')
    avoid   = sum(1 for i in resolved if i.get('safety_level') == 'avoid')
    n_resolved = len(resolved)

    parts = []
    product_label = name or ('food product' if product_type == 'food' else 'cosmetic product')
    by_brand = f' by {brand}' if brand else ''
    parts.append(f"{product_label}{by_brand} received a Grade {grade} ({score}/100).")

    if product_type == 'food':
        if nova_group and nova_group in _NOVA_LABELS:
            parts.append(f"It is classified as {_NOVA_LABELS[nova_group]} (NOVA {nova_group}).")
        if nutriscore and nutriscore.lower() in _NUTRISCORE_LABELS:
            parts.append(f"Nutritional quality is {_NUTRISCORE_LABELS[nutriscore.lower()]}.")

    if n_resolved > 0:
        parts.append(
            f"Of {n_resolved} analyzed ingredient{'s' if n_resolved != 1 else ''}: "
            f"{safe} safe, {caution} caution, {avoid} to avoid."
        )
    else:
        parts.append("No ingredients were matched against the safety database.")

    if total > n_resolved:
        unmatched = total - n_resolved
        parts.append(
            f"{unmatched} ingredient{'s' if unmatched != 1 else ''} "
            "could not be matched and are not reflected in this score."
        )

    return ' '.join(parts)


def _generate_points(
    product_type: str,
    resolved: list[dict],
    total: int,
    nova_group: int | None,
    nutriscore: str,
    categories: list[str],
) -> tuple[list[str], list[str]]:
    positive: list[str] = []
    negative: list[str] = []

    safe_all    = [i for i in resolved if i.get('safety_level') == 'safe']
    caution_all = [i for i in resolved if i.get('safety_level') == 'caution']
    avoid_all   = [i for i in resolved if i.get('safety_level') == 'avoid']

    # ── Positive ─────────────────────────────────────────────────────────────
    if total <= 8 and total > 0:
        positive.append(f"Short ingredient list ({total} ingredients) — less processed")
    if resolved and not caution_all and not avoid_all:
        positive.append("All analyzed ingredients are considered safe")
    if product_type == 'food':
        if nova_group in (1, 2):
            positive.append(f"Minimally processed food (NOVA {nova_group})")
        if nutriscore and nutriscore.lower() in ('a', 'b'):
            positive.append(f"Good nutritional quality (Nutri-Score {nutriscore.upper()})")

    # ── Negative ─────────────────────────────────────────────────────────────
    if product_type == 'food':
        if nova_group == 4:
            negative.append("Ultra-processed food (NOVA 4) — high level of industrial processing")
        elif nova_group == 3:
            negative.append("Processed food (NOVA 3)")
        if nutriscore and nutriscore.lower() == 'e':
            negative.append("Very poor nutritional quality (Nutri-Score E)")
        elif nutriscore and nutriscore.lower() == 'd':
            negative.append("Poor nutritional quality (Nutri-Score D)")

        # Additive categories
        e_ranges: set[str] = set()
        for ing in resolved:
            n = _e_number_range(ing.get('e_number') or ing.get('name') or '')
            if n:
                if 100 <= n <= 199: e_ranges.add('artificial colorants')
                elif 200 <= n <= 299: e_ranges.add('artificial preservatives')
                elif 900 <= n <= 999: e_ranges.add('artificial sweeteners')
        for label in sorted(e_ranges):
            negative.append(f"Contains {label}")

    # Flagged ingredients
    for ing in avoid_all:
        concerns = ing.get('concerns') or []
        label = ing.get('canonical_name') or ing.get('name') or 'Unknown'
        concern_str = ', '.join(concerns) if concerns else 'flagged ingredient'
        negative.append(f"{label} — {concern_str}")

    for ing in caution_all:
        concerns = ing.get('concerns') or []
        if concerns:
            label = ing.get('canonical_name') or ing.get('name') or 'Unknown'
            negative.append(f"{label} — {', '.join(concerns)}")

    if product_type == 'cosmetic':
        has_banned = any(i.get('eu_status') == 'banned' for i in resolved)
        if has_banned:
            negative.append("Contains EU-banned substance — maximum grade is D")
        parabens = [i for i in resolved if 'paraben' in (i.get('concerns') or [])]
        if parabens:
            names = ', '.join(i.get('canonical_name') or i.get('name') for i in parabens[:3])
            negative.append(f"Contains parabens: {names}")
        ed = [i for i in resolved if 'endocrine_disruptor' in (i.get('concerns') or [])]
        if ed:
            names = ', '.join(i.get('canonical_name') or i.get('name') for i in ed[:3])
            negative.append(f"Endocrine disruptors detected: {names}")

    return positive, negative


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report(product_data: dict[str, Any], barcode: str) -> SafetyReport | None:
    """
    Build a SafetyReport from local DB data without calling Claude.

    Returns None if there is not enough data for a meaningful report.
    """
    product_type = product_data.get('product_type') or 'unknown'
    resolved     = [i for i in product_data.get('resolved_ingredients', []) if i.get('safety_level')]
    total        = product_data.get('total_ingredients', 0)
    name         = product_data.get('name') or ''
    brand        = product_data.get('brand') or ''
    nova_group   = product_data.get('nova_group')
    nutriscore   = product_data.get('nutriscore') or ''
    categories   = product_data.get('categories') or []

    # Need at least MIN_RESOLVED matched ingredients, OR no ingredients
    # listed at all (score via NOVA/nutriscore only), OR a known product_type.
    has_enough_signal = (
        len(resolved) >= MIN_RESOLVED
        or total == 0
        or product_type in ('food', 'cosmetic')
    )
    if not has_enough_signal:
        return None

    score, breakdown = _compute_score(product_type, resolved, total, nova_group, nutriscore)
    grade = _score_to_grade(score)

    summary = _generate_summary(
        name, brand, product_type, score, grade,
        resolved, total, nova_group, nutriscore,
    )
    positive, negative = _generate_points(
        product_type, resolved, total, nova_group, nutriscore, categories,
    )

    ingredients_analysis = [
        IngredientAnalysis(
            name=i.get('canonical_name') or i.get('name') or '',
            safety_level=i['safety_level'],
            concern=', '.join(i['concerns']) if i.get('concerns') else None,
            concerns=list(i.get('concerns') or []),
            sources=list(i.get('sources') or []),
            score_impact=_ingredient_score_impact(i, product_type),
        )
        for i in resolved
    ]

    return SafetyReport(
        product_name=name or 'Unknown Product',
        brand=brand or '',
        product_type=product_type,
        barcode=barcode,
        image_url=product_data.get('image_url'),
        score=score,
        grade=grade,
        summary=summary,
        ingredients_analysis=ingredients_analysis,
        positive_points=positive,
        negative_points=negative,
        not_found=False,
        category_slug=derive_category_slug(name, product_type, categories),
        nutriscore=(nutriscore.upper() if nutriscore else None),
        nova_group=nova_group,
        scoring_breakdown=breakdown,
    )
