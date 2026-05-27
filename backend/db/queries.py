"""
Database query helpers for the SafeScan backend.

All functions acquire a connection from the shared pool via get_conn().
"""

from __future__ import annotations

import json
from typing import Any

from db.connection import get_conn
from db.ingredient_resolver import resolve_ingredients

# ---------------------------------------------------------------------------
# Safety report cache
# ---------------------------------------------------------------------------

_GET_CACHED_REPORT = """
SELECT report
FROM safety_reports
WHERE barcode = $1
  AND expires_at > NOW()
ORDER BY created_at DESC
LIMIT 1
"""

_UPSERT_CACHED_REPORT = """
INSERT INTO safety_reports (barcode, report, claude_used, expires_at)
VALUES ($1, $2::jsonb, $3, NOW() + INTERVAL '7 days')
ON CONFLICT (barcode) DO UPDATE
SET report      = EXCLUDED.report,
    claude_used = EXCLUDED.claude_used,
    expires_at  = EXCLUDED.expires_at,
    updated_at  = NOW()
"""


async def get_cached_report(barcode: str) -> dict | None:
    """Return a cached SafetyReport dict if one exists and has not expired."""
    async with get_conn() as conn:
        row = await conn.fetchrow(_GET_CACHED_REPORT, barcode)
    if row is None:
        return None
    # asyncpg returns JSONB as a string; parse it
    raw = row["report"]
    return json.loads(raw) if isinstance(raw, str) else raw


async def cache_report(barcode: str, report_json: str, claude_used: bool) -> None:
    """Upsert a safety report into the cache with a 7-day TTL. One row per
    barcode, kept in place via ON CONFLICT — `updated_at` is bumped on each
    overwrite, `created_at` stays at first-cached time."""
    async with get_conn() as conn:
        await conn.execute(_UPSERT_CACHED_REPORT, barcode, report_json, claude_used)


# ---------------------------------------------------------------------------
# Recommended alternatives
# ---------------------------------------------------------------------------
#
# Returns up to N already-cached products in the same product_type with a
# strictly better score than the current scan. Optionally filters to products
# sharing at least one category label.  Pure SQL — no model invocation —
# so it's cheap to call on every scan and naturally improves as the cache
# grows.  When the cache is sparse this returns an empty list and the UI
# hides the panel.

_FIND_ALTERNATIVES = """
SELECT r.barcode,
       r.report->>'product_name'                                  AS product_name,
       r.report->>'brand'                                         AS brand,
       r.report->>'image_url'                                     AS image_url,
       COALESCE(r.report->>'product_type', p.product_type, 'unknown') AS product_type,
       r.report->>'grade'                                         AS grade,
       (r.report->>'score')::int                                  AS score
FROM safety_reports r
LEFT JOIN products p ON p.barcode = r.barcode
WHERE r.barcode <> $1
  -- expires_at intentionally NOT filtered: a slightly-stale "this product
  -- in your category scored well last time" is still useful info, and the
  -- TTL is meant to gate the user's own freshly-shown report.
  AND (r.report->>'product_type') = $2
  AND (r.report->>'score')::int > $3
  AND (r.report->>'category_slug') = $4
ORDER BY (r.report->>'score')::int DESC,
         r.updated_at DESC
LIMIT $5
"""


async def find_alternatives(
    barcode:        str,
    product_type:   str,
    score:          int,
    category_slug:  str | None,
    limit:          int = 3,
) -> list[dict[str, Any]]:
    """
    Return up to `limit` cached alternative products with the same
    `category_slug` (use-case bucket) and a strictly higher score than
    the current scan.

    Returns [] when the current product has no slug (cannot match a peer
    safely) or product_type is "unknown"/"drug".  Drug alternatives are
    intentionally out of scope — brand-name vs generic Rx similarity is a
    different domain.
    """
    if not category_slug:
        return []
    if product_type in ("unknown", "drug", "", None):
        return []

    async with get_conn() as conn:
        rows = await conn.fetch(
            _FIND_ALTERNATIVES, barcode, product_type, score, category_slug, limit,
        )
    return [dict(r) for r in rows]


_GET_PRODUCT_CATEGORIES = """
SELECT categories FROM products WHERE barcode = $1 LIMIT 1
"""


_SEARCH_PRODUCTS = """
SELECT barcode,
       name,
       COALESCE(brand, '')           AS brand,
       image_url,
       COALESCE(product_type, 'unknown') AS product_type,
       -- Relevance: brand exact > name prefix > brand prefix > substring
       CASE
         WHEN lower(brand) = lower($1)             THEN 100
         WHEN lower(name)  LIKE lower($1) || '%'   THEN  80
         WHEN lower(brand) LIKE lower($1) || '%'   THEN  60
         WHEN lower(name)  LIKE '%' || lower($1) || '%' THEN 40
         WHEN lower(brand) LIKE '%' || lower($1) || '%' THEN 30
         ELSE 0
       END AS rank
FROM products
WHERE (name ILIKE '%' || $1 || '%' OR brand ILIKE '%' || $1 || '%')
  AND name IS NOT NULL
  AND ($2::text IS NULL OR product_type = $2)
ORDER BY rank DESC, LENGTH(COALESCE(name,'')) ASC
LIMIT $3
"""


async def search_products(
    query:        str,
    product_type: str | None = None,
    limit:        int = 20,
) -> list[dict[str, Any]]:
    """
    Fuzzy product search by name/brand via pg_trgm GIN index.

    Returns ranked results: brand-exact > name-prefix > brand-prefix >
    substring. Filters out rows with NULL name (mostly UPCitemdb stubs).
    Optional product_type filter.
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []
    async with get_conn() as conn:
        rows = await conn.fetch(_SEARCH_PRODUCTS, q, product_type, limit)
    return [
        {k: r[k] for k in ("barcode", "name", "brand", "image_url", "product_type")}
        for r in rows
    ]


_GET_PRODUCT_NUTRITION = """
SELECT nutriscore, nova_group FROM products WHERE barcode = $1 LIMIT 1
"""


async def get_product_nutrition(barcode: str) -> dict[str, Any]:
    """Return {'nutriscore': str|None, 'nova_group': int|None} for a barcode,
    or both None if not in the products table. Used to backfill the
    Nutri-Score / NOVA fields on cached reports that pre-date those fields
    in the SafetyReport schema."""
    async with get_conn() as conn:
        row = await conn.fetchrow(_GET_PRODUCT_NUTRITION, barcode)
    if row is None:
        return {"nutriscore": None, "nova_group": None}
    raw = row["nutriscore"]
    return {
        "nutriscore": raw.upper() if raw else None,
        "nova_group": row["nova_group"],
    }


async def get_product_categories(barcode: str) -> list[str]:
    """Return the categories array for a barcode, or [] if not in the
    products table."""
    async with get_conn() as conn:
        row = await conn.fetchrow(_GET_PRODUCT_CATEGORIES, barcode)
    if row is None:
        return []
    return list(row["categories"] or [])


# ---------------------------------------------------------------------------
# Product lookup
# ---------------------------------------------------------------------------

_GET_PRODUCT = """
SELECT id, barcode, name, brand, product_type, image_url,
       nutriscore, nova_group, categories, source
FROM products
WHERE barcode = $1
"""

_GET_INGREDIENTS = """
SELECT ingredient_name, position
FROM product_ingredients
WHERE product_id = $1
ORDER BY position
LIMIT 150
"""

_GET_USER_SUBMISSION = """
SELECT extracted_data
FROM user_submissions
WHERE barcode = $1
ORDER BY id DESC
LIMIT 1
"""


async def get_user_submission(barcode: str) -> dict[str, Any] | None:
    """
    Return the most recent user submission for this barcode as a product dict
    shaped the same as get_product_from_db(), or None if not found.
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(_GET_USER_SUBMISSION, barcode)
    if row is None:
        return None

    raw = row["extracted_data"]
    data = json.loads(raw) if isinstance(raw, str) else raw
    product = data.get("product", {})
    ingredients = data.get("ingredients", [])

    ingredient_names = [i["name"] for i in ingredients if i.get("name")]
    ingredients_text = ", ".join(ingredient_names) if ingredient_names else ""

    name  = product.get("product_name") or ""
    brand = product.get("brand") or ""
    if not name and not brand:
        return None

    return {
        "found":                True,
        "source":               "user_submission",
        "product_type":         product.get("product_type") or "unknown",
        "name":                 name,
        "brand":                brand,
        "image_url":            None,
        "nutriscore":           "",
        "nova_group":           None,
        "categories":           [],
        "ingredients":          ingredients_text,
        "resolved_ingredients": [],
        "db_resolved_count":    0,
        "total_ingredients":    len(ingredient_names),
    }


_LIST_SUBMISSIONS = """
SELECT id, barcode, status, extracted_data, report, analyzed_at, created_at, error
FROM user_submissions
ORDER BY created_at DESC
LIMIT 50
"""

_SET_SUBMISSION_ANALYZING = """
UPDATE user_submissions SET status = 'analyzing' WHERE id = $1
"""

_SET_SUBMISSION_COMPLETE = """
UPDATE user_submissions
SET status = 'complete', report = $2::jsonb, analyzed_at = NOW()
WHERE id = $1
"""

_SET_SUBMISSION_FAILED = """
UPDATE user_submissions
SET status = 'failed', error = $2, analyzed_at = NOW()
WHERE id = $1
"""

_GET_SUBMISSION = """
SELECT id, barcode, status, extracted_data, report, analyzed_at, created_at, error
FROM user_submissions
WHERE id = $1
"""


async def list_user_submissions() -> list[dict[str, Any]]:
    async with get_conn() as conn:
        rows = await conn.fetch(_LIST_SUBMISSIONS)
    return [dict(r) for r in rows]


async def get_submission(submission_id: int) -> dict[str, Any] | None:
    async with get_conn() as conn:
        row = await conn.fetchrow(_GET_SUBMISSION, submission_id)
    return dict(row) if row else None


async def set_submission_analyzing(submission_id: int) -> None:
    async with get_conn() as conn:
        await conn.execute(_SET_SUBMISSION_ANALYZING, submission_id)


async def set_submission_complete(submission_id: int, report_json: str) -> None:
    async with get_conn() as conn:
        await conn.execute(_SET_SUBMISSION_COMPLETE, submission_id, report_json)


async def set_submission_failed(submission_id: int, error: str) -> None:
    async with get_conn() as conn:
        await conn.execute(_SET_SUBMISSION_FAILED, submission_id, error)


async def get_product_from_db(barcode: str) -> dict[str, Any] | None:
    """
    Look up a product and its resolved ingredients from the local database.

    Runs the full 4-step ingredient resolution cascade (exact → alias →
    E-number → FTS → Claude write-back) via ingredient_resolver.

    Returns a dict shaped the same as lookup_product() so scanner.py can
    treat local and API results identically.  Returns None if not found.
    """
    async with get_conn() as conn:
        product_row = await conn.fetchrow(_GET_PRODUCT, barcode)
        if product_row is None:
            return None

        product_id = product_row["id"]
        ingredient_rows = await conn.fetch(_GET_INGREDIENTS, product_id)

    raw_names: list[str] = [r["ingredient_name"] for r in ingredient_rows]

    # Full resolution cascade: exact → alias → E-number → FTS → Claude
    resolved_map = await resolve_ingredients(raw_names) if raw_names else {}

    # Build ordered list (preserves label position)
    resolved_ingredients = []
    for raw in raw_names:
        entry: dict[str, Any] = {"name": raw}
        if raw in resolved_map:
            entry.update(resolved_map[raw])
        resolved_ingredients.append(entry)

    # Plain text for Claude's context (first 80 names)
    ingredients_text = ", ".join(raw_names[:80])
    if len(raw_names) > 80:
        ingredients_text += f" ... ({len(raw_names) - 80} more)"

    product = dict(product_row)
    return {
        "found":                True,
        "source":               "local_db",
        "db_source":            product["source"] or "",
        "product_type":         product["product_type"] or "unknown",
        "name":                 product["name"] or "",
        "brand":                product["brand"] or "",
        "image_url":            product["image_url"],
        "nutriscore":           product["nutriscore"] or "",
        "nova_group":           product["nova_group"],
        "categories":           list(product["categories"] or []),
        "ingredients":          ingredients_text,
        "resolved_ingredients": resolved_ingredients,
        "db_resolved_count":    len(resolved_map),
        "total_ingredients":    len(raw_names),
    }
