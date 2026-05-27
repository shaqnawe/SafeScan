"""
Use-case category classification ("slug") for matching alternative products.

The `Alternative` recommendation feature needs to match products by *use case*
("hand soap → hand soap", "body lotion → body lotion") rather than the
broad parent categories (`Health & Beauty > Personal Care > Cosmetics`) that
OBF / UPCitemdb provide. Broad parents match across use cases — that's how
a hand soap ended up recommended as an alternative to a moisturizer.

This module implements a deterministic keyword heuristic over product name +
ingredient list + categories. The result is a single canonical slug from a
controlled vocabulary, or None when no confident match exists. The slug is
written into `SafetyReport.category_slug` and used by `find_alternatives`
to filter candidates with `WHERE category_slug = $X`.

Drugs are intentionally skipped — brand-name vs. generic alternatives is a
different domain problem (active-ingredient matching, prescription class
similarity, etc.) and "recommend a cleaner Rx" makes no sense.

Upgrade path (deferred): hand classification off to Claude during Phase 2,
using the same vocabulary. The matching query stays identical, so we get a
robustness upgrade without changing anything downstream.
"""

from __future__ import annotations

import re

# Ordered: more specific patterns first so they win against generic ones.
# e.g. "hand soap" must match before "soap".  Each pattern is a regex tested
# case-insensitively against the lowercased product name (and the joined
# category labels).
_COSMETIC_PATTERNS: list[tuple[str, str]] = [
    # Cleansers — hand vs body vs face
    (r"\bhand[- ]?(soap|wash|cleanser)\b",          "hand_soap"),
    (r"\bbody[- ]?(wash|cleanser|gel)\b",           "body_wash"),
    (r"\bshower[- ]?(gel|cream)\b",                 "body_wash"),
    (r"\bface[- ]?(wash|cleanser|cleansing)\b",     "face_cleanser"),
    (r"\bfacial[- ]?(wash|cleanser|cleansing)\b",   "face_cleanser"),
    (r"\bmicellar\b",                               "face_cleanser"),
    (r"\bbar[- ]?soap\b",                           "bar_soap"),
    (r"\b(soap[- ]?bar|cleansing[- ]?bar)\b",       "bar_soap"),

    # Hair
    (r"\bshampoo\b",                                "shampoo"),
    (r"\bconditioner\b",                            "conditioner"),
    (r"\bdry[- ]?shampoo\b",                        "shampoo"),
    (r"\bhair[- ]?(mask|treatment|oil|serum)\b",    "hair_treatment"),
    (r"\bhair[- ]?(gel|mousse|spray|cream|wax|pomade)\b", "hair_styling"),
    (r"\bhair[- ]?(color|dye|bleach)\b",            "hair_color"),

    # Moisturizers — face / eye / hand / body
    (r"\beye[- ]?(cream|gel|serum|patch)\b",        "eye_care"),
    (r"\bhand[- ]?(cream|lotion|balm|sanitizer)\b", "hand_cream"),
    (r"\bfoot[- ]?(cream|lotion|balm)\b",           "foot_cream"),
    (r"\bface[- ]?(cream|moisturizer|moisturiser)\b",       "face_moisturizer"),
    (r"\bfacial[- ]?(cream|moisturizer|moisturiser)\b",     "face_moisturizer"),
    (r"\b(day|night|anti[- ]?aging)[- ]?(cream|moisturizer|moisturiser)\b", "face_moisturizer"),
    (r"\b(face|facial)[- ]?(serum|essence)\b",      "face_serum"),
    (r"\bbody[- ]?(lotion|cream|butter|milk|moisturizer|moisturiser|oil)\b", "body_lotion"),
    (r"\blotion\b",                                 "body_lotion"),
    (r"\bmoisturiz",                                "face_moisturizer"),
    (r"\bmoisturis",                                "face_moisturizer"),

    # Sun
    (r"\bsunscreen\b",                              "sunscreen"),
    (r"\bsun[- ]?(block|cream|lotion|spray)\b",     "sunscreen"),
    (r"\bspf[- ]?\d",                               "sunscreen"),
    (r"\bafter[- ]?sun\b",                          "after_sun"),
    (r"\b(self[- ]?)?tan(ner|ning)\b",              "self_tanner"),

    # Oral / Personal
    (r"\btooth[- ]?paste\b",                        "toothpaste"),
    (r"\bdentif",                                   "toothpaste"),
    (r"\bmouth[- ]?(wash|rinse)\b",                 "mouthwash"),
    (r"\banti[- ]?cavity\b",                        "mouthwash"),
    (r"\b(fluoride|treatment|oral|dental)[- ]?rinse\b", "mouthwash"),
    (r"\bdeodorant\b",                              "deodorant"),
    (r"\b(anti[- ]?perspirant|antiperspirant)\b",   "deodorant"),
    (r"\bshav(e|ing)\b",                            "shaving"),
    (r"\bafter[- ]?shave\b",                        "after_shave"),

    # Lips / Eyes / Face makeup
    (r"\blip[- ]?(balm|stick|gloss|liner|color|colour|tint)\b", "lip"),
    (r"\bchapstick\b",                              "lip"),
    (r"\bmascara\b",                                "mascara"),
    (r"\beye[- ]?(liner|shadow)\b",                 "eye_makeup"),
    (r"\bfoundation\b",                             "foundation"),
    (r"\bconcealer\b",                              "concealer"),
    (r"\bblush(er)?\b",                             "blush"),
    (r"\bbronzer\b",                                "bronzer"),
    (r"\bpowder\b",                                 "face_powder"),
    (r"\bprimer\b",                                 "face_primer"),

    # Fragrance
    (r"\beau[- ]?de[- ]?(parfum|toilette|cologne)\b", "fragrance"),
    (r"\bperfume\b",                                "fragrance"),
    (r"\bcologne\b",                                "fragrance"),

    # Treatments
    (r"\bface[- ]?mask\b",                          "face_mask"),
    (r"\bsheet[- ]?mask\b",                         "face_mask"),
    (r"\bclay[- ]?mask\b",                          "face_mask"),
    (r"\bserum\b",                                  "face_serum"),
    (r"\btoner\b",                                  "toner"),
    (r"\bexfoliant\b",                              "exfoliant"),
    (r"\b(retinol|retinoid)\b",                     "face_serum"),

    # Baby
    (r"\bbaby[- ]?(shampoo|wash|lotion|oil|cream|powder)\b", "baby_care"),
    (r"\bdiaper[- ]?(cream|rash)\b",                "baby_care"),

    # Nails
    (r"\bnail[- ]?(polish|laquer|lacquer|color|colour|enamel)\b", "nail_polish"),
    (r"\bcuticle\b",                                "nail_care"),

    # Generic fallbacks — only run if nothing more specific matched
    (r"\bsoap\b",                                   "bar_soap"),
    (r"\bcream\b",                                  "body_lotion"),
]

_FOOD_PATTERNS: list[tuple[str, str]] = [
    # Beverages — cola first, then juice, then generic
    (r"\b(cola|coke|pepsi|coca[- ]?cola|root[- ]?beer|cream[- ]?soda)\b", "soda"),
    (r"\b(soda|soft[- ]?drink|pop|carbonated)\b",   "soda"),
    (r"\benergy[- ]?drink\b",                       "energy_drink"),
    (r"\bsports[- ]?drink\b",                       "sports_drink"),
    (r"\b(coffee|espresso|latte|cappuccino|americano)\b", "coffee"),
    (r"\b(tea|kombucha)\b",                         "tea"),
    (r"\b(beer|lager|ale|stout|ipa)\b",             "beer"),
    (r"\b(wine|champagne|prosecco|sparkling[- ]?wine)\b", "wine"),
    (r"\b(whisk(e)?y|vodka|gin|rum|tequila|bourbon)\b",   "spirits"),
    (r"\bsparkling[- ]?water\b",                    "sparkling_water"),
    (r"\b(spring|mineral|drinking|distilled)[- ]?water\b", "water"),
    (r"\bjuice\b",                                  "juice"),
    (r"\bsmoothie\b",                               "juice"),

    # Dairy + alternatives
    (r"\b(almond|oat|soy|coconut|cashew|rice|pea)[- ]?milk\b", "plant_milk"),
    (r"\b(skim|whole|2%|1%|reduced[- ]?fat)?[- ]?milk\b", "milk"),
    (r"\b(yogh?urt|yog)\b",                         "yogurt"),
    (r"\bkefir\b",                                  "yogurt"),
    (r"\b(cheese|cheddar|gouda|mozzarella|brie|feta|parmesan|swiss)\b", "cheese"),
    (r"\b(butter|margarine|ghee)\b",                "butter"),
    (r"\bice[- ]?cream\b",                          "ice_cream"),
    (r"\bgelato\b",                                 "ice_cream"),
    (r"\b(cream cheese|sour cream|whipped cream|cream)\b", "cream"),

    # Bakery + grains
    (r"\b(bread|loaf|bun|roll|bagel|baguette|focaccia|toast)\b", "bread"),
    (r"\b(cereal|granola|muesli|oatmeal|porridge)\b", "cereal"),
    (r"\b(cracker|crispbread)\b",                   "cracker"),
    (r"\b(cookie|biscuit|wafer)\b",                 "cookie"),
    (r"\b(cake|pastry|donut|doughnut|muffin|brownie|croissant|scone|cupcake)\b", "baked_good"),
    (r"\b(chocolate|cocoa)\b",                      "chocolate"),
    (r"\b(candy|gummy|gummies|lollipop|lozenge|caramel|toffee|jelly[- ]?bean|hard[- ]?candy)\b", "candy"),
    (r"\bbon[- ]?bons?\b",                          "candy"),

    # Salty snacks
    (r"\b(chip|crisp|popcorn|pretzel|tortilla)\b",  "snack_chip"),
    (r"\b(nut|almond|cashew|peanut|pistachio|walnut|hazelnut)s?\b", "nuts"),
    (r"\b(jerky|biltong)\b",                        "jerky"),

    # Mealtime / protein
    (r"\b(pasta|noodle|spaghetti|penne|fettuccine|linguine|ramen|udon)\b", "pasta"),
    (r"\b(rice|risotto|paella|pilaf)\b",            "rice"),
    (r"\b(soup|broth|bisque|chowder)\b",            "soup"),
    (r"\b(frozen[- ]?meal|tv[- ]?dinner|microwave[- ]?meal)\b", "frozen_meal"),
    (r"\b(pizza|calzone)\b",                        "pizza"),
    (r"\b(burger|patty|sausage|hotdog|hot[- ]?dog|bacon|ham|salami|prosciutto)\b", "processed_meat"),
    (r"\b(canned|tinned)[- ]?(meat|fish|tuna|salmon|sardine)\b", "canned_protein"),
    (r"\b(tofu|tempeh|seitan)\b",                   "plant_protein"),

    # Condiments / spreads
    (r"\b(ketchup|catsup|mustard|mayo|mayonnaise|sriracha|aioli)\b", "condiment"),
    (r"\b(jam|jelly|preserve|marmalade)\b",         "spread"),
    (r"\b(peanut[- ]?butter|almond[- ]?butter|nut[- ]?butter)\b", "spread"),
    (r"\b(honey|syrup|agave|maple)\b",              "sweetener_syrup"),
    (r"\b(sauce|gravy|salsa|pesto|hummus|tapenade)\b", "sauce"),
    (r"\b(salad[- ]?dressing|vinaigrette)\b",       "dressing"),
    (r"\b(marinade|dressing)\b",                    "dressing"),
    (r"\b(oil|olive[- ]?oil|vegetable[- ]?oil|coconut[- ]?oil)\b", "cooking_oil"),
    (r"\b(vinegar|balsamic)\b",                     "vinegar"),

    # Baby / supplements
    (r"\bbaby[- ]?food\b",                          "baby_food"),
    (r"\binfant[- ]?formula\b",                     "infant_formula"),
    (r"\b(protein[- ]?powder|whey|casein)\b",       "protein_powder"),
    (r"\b(vitamin|supplement|multivitamin)\b",      "supplement"),
    (r"\b(protein[- ]?bar|energy[- ]?bar|granola[- ]?bar|meal[- ]?bar)\b", "snack_bar"),

    # Produce
    (r"\b(salad|leafy[- ]?green)\b",                "produce_salad"),
    (r"\b(apple|banana|orange|grape|berry|berries|strawberr|blueberr|raspberr)\b", "produce_fruit"),
]


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace; preserve hyphens which patterns rely on."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _match(patterns: list[tuple[str, str]], haystack: str) -> str | None:
    for pattern, slug in patterns:
        if re.search(pattern, haystack):
            return slug
    return None


def derive_category_slug(
    name: str | None,
    product_type: str | None,
    categories: list[str] | None = None,
) -> str | None:
    """
    Classify a product into a canonical use-case slug.

    Matching strategy: lowercase the product name + joined categories, then
    test ordered patterns from most-specific to least-specific. First match
    wins. Returns None when no confident classification can be made — the
    `find_alternatives` query treats nulls as non-matchable so we never
    surface a false positive.

    `product_type='drug'` always returns None — brand-name vs. generic Rx
    alternative recommendations are out of scope.
    """
    if not name:
        return None
    if product_type in ("drug", "unknown", None, ""):
        return None

    haystack_parts = [name]
    if categories:
        haystack_parts.extend(categories)
    haystack = _normalize(" | ".join(haystack_parts))

    if product_type == "cosmetic":
        return _match(_COSMETIC_PATTERNS, haystack)
    if product_type == "food":
        return _match(_FOOD_PATTERNS, haystack)

    return None
