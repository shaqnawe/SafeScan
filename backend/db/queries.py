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
    """Insert a safety report into the cache with a 7-day TTL."""
    async with get_conn() as conn:
        await conn.execute(_UPSERT_CACHED_REPORT, barcode, report_json, claude_used)


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
