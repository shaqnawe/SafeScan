"""
Vegan classification for food products.

Deterministic keyword scan over the resolved/parsed ingredient list.
Returns one of three states:
  - True   : confident vegan (no non-vegan or uncertain-origin ingredients)
  - False  : confident NOT vegan (clear animal-derived ingredient found)
  - None   : uncertain (e.g. lecithin without a plant qualifier — could be
             soy or egg) — conservative; we omit the badge rather than
             guess. The user wanted enzymes/emulsifiers of uncertain
             origin flagged as not-confidently-vegan.

Detection is purely on the canonical/raw name field of each ingredient
entry. Word-boundary matching so "soy milk" doesn't false-positive on
"milk". A plant-hedge prefix (soy, oat, almond, coconut, etc.) suppresses
the dairy/butter/cream match.

Upgrade path (deferred, same as category_slug): hand classification to
Claude during Phase 2 emit. For v1 the heuristic covers the obvious 90%
of consumer products.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Pattern lists (ordered by category for readability; order doesn't affect
# correctness — we return on first non-vegan match)
# ---------------------------------------------------------------------------

_NON_VEGAN_PATTERNS: list[str] = [
    # Dairy
    r"\bmilk\b", r"\bbutter\b", r"\bcheese\b", r"\bcream\b", r"\bwhey\b",
    r"\bcasein", r"\blactose\b", r"\byog?h?urt\b", r"\bghee\b", r"\bquark\b",
    r"\bcurd\b", r"\bcondensed milk\b", r"\bevaporated milk\b",

    # Eggs
    r"\beggs?\b", r"\balbumen\b", r"\bovalbumin\b", r"\blysozyme\b",
    r"\begg white\b", r"\begg yolk\b",

    # Bee products
    r"\bhoney\b", r"\bbeeswax\b", r"\bpropolis\b", r"\broyal jelly\b",

    # Animal-derived gelling / structural
    r"\bgelatin(e)?\b", r"\bcollagen\b", r"\bisinglass\b",

    # Animal fats
    r"\blard\b", r"\btallow\b", r"\bsuet\b", r"\bschmaltz\b",

    # Meat / fish / seafood
    r"\bbroth\b", r"\bstock\b",
    r"\bbeef\b", r"\bpork\b", r"\bchicken\b", r"\bturkey\b", r"\bduck\b",
    r"\bfish\b", r"\banchov", r"\btuna\b", r"\bsalmon\b", r"\bsardine",
    r"\boyster\b", r"\bshrimp\b", r"\bcrab\b", r"\blobster\b", r"\bsquid\b",
    r"\bbacon\b", r"\bham\b", r"\bsausage\b",

    # Insect / shell / wax
    r"\bcarmine\b", r"\bcochineal\b", r"\bshellac\b", r"\blanolin\b",
    r"\bcastoreum\b",

    # Cheese-making + processing aids
    r"\brennet\b",

    # E-numbers of definite animal origin
    r"\be120\b",          # carmine
    r"\be441\b",          # gelatin
    r"\be542\b",          # bone phosphate
    r"\be901\b",          # beeswax
    r"\be904\b",          # shellac
    r"\be913\b",          # lanolin

    # D3 most commonly from lanolin (D2 is plant-derived from mushrooms)
    r"\bvitamin d[- ]?3\b", r"\bcholecalciferol\b",
]

_UNCERTAIN_PATTERNS: list[str] = [
    # Common emulsifiers / glycerides — plant or animal origin
    r"\blecithin\b",                         # commonly soy but also egg
    r"\bmono[- ]?and[- ]?diglycer",
    r"\bdiglyceride", r"\bmonoglyceride",
    r"\bglyceride",
    r"\be422\b",                             # glycerol
    r"\be471\b",                             # mono-/diglycerides of fatty acids
    r"\be472[a-f]?\b",                       # esters of mono-/diglycerides
    r"\be481\b", r"\be482\b",                # stearoyl lactylates
    r"\bcalcium stearate\b", r"\bmagnesium stearate\b",
    r"\bstearic acid\b", r"\bstearate\b",

    # Enzymes without a source-of-origin qualifier
    r"\benzyme",

    # Vague flavor / fragrance ingredients — natural flavor can be animal
    r"\bnatural flavou?r",
    r"\bflavour?ing\b",
]

# Plant-derived qualifiers that suppress a downstream dairy/butter/cream match.
# e.g. "soy milk" → vegan,  "almond butter" → vegan
_PLANT_HEDGES: tuple[str, ...] = (
    "soy",
    "soya",
    "oat",
    "almond",
    "coconut",
    "rice",
    "cashew",
    "hemp",
    "pea",
    "hazelnut",
    "walnut",
    "macadamia",
    "peanut",
    "sunflower",
    "vegetable",
    "plant",
    "cocoa",
    "shea",
    "cacao",
    "vegan",
)


def _is_hedged(name_lower: str, match: re.Match) -> bool:
    """Does a plant-hedge word immediately precede the matched token?"""
    before = name_lower[:match.start()].rstrip(" -_")
    return any(before.endswith(h) for h in _PLANT_HEDGES)


def assess_vegan(ingredient_names: list[str]) -> bool | None:
    """
    Classify a product's vegan status from its ingredient list.

    Args:
        ingredient_names: list of raw or canonical ingredient names. Order
                          doesn't matter. Empty list returns None (we can't
                          assert vegan with zero data).

    Returns:
        True  — confident vegan (no non-vegan or uncertain-origin entries)
        False — confident not vegan (clear animal-derived entry found)
        None  — uncertain origin (e.g. lecithin without "soy"/"sunflower")
    """
    if not ingredient_names:
        return None

    found_uncertain = False

    for raw in ingredient_names:
        name = (raw or "").lower()
        if not name:
            continue

        # First: definitively non-vegan?
        for pattern in _NON_VEGAN_PATTERNS:
            m = re.search(pattern, name)
            if m and not _is_hedged(name, m):
                return False

        # Then: uncertain origin?
        for pattern in _UNCERTAIN_PATTERNS:
            if re.search(pattern, name):
                found_uncertain = True

    return None if found_uncertain else True
