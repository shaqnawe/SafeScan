"""
Seed script for the ingredients and ingredient_aliases tables.

Loads EU E-numbers (e_numbers.json) and flagged cosmetic ingredients
(cosing_flagged.json) then upserts them into PostgreSQL via asyncpg.

Usage:
    python -m db.seed.seed_ingredients
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
import os

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

# backend/.env  (this file lives at backend/db/seed/seed_ingredients.py,
# so three parents up reaches the backend/ directory)
_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set. Check your .env file.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Data file paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent / "data"
_E_NUMBERS_PATH = _DATA_DIR / "e_numbers.json"
_COSING_PATH = _DATA_DIR / "cosing_flagged.json"
_FOOD_PATH = _DATA_DIR / "food_flagged.json"
_FRAGRANCE_PATH = _DATA_DIR / "fragrance_allergens_flagged.json"

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_UPSERT_INGREDIENT = """
INSERT INTO ingredients (
    name, inci_name, e_number, cas_number, ingredient_type, safety_level,
    score_penalty, concerns, eu_status, sources, notes, updated_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
ON CONFLICT (name) DO UPDATE SET
    safety_level  = EXCLUDED.safety_level,
    score_penalty = EXCLUDED.score_penalty,
    concerns      = EXCLUDED.concerns,
    eu_status     = EXCLUDED.eu_status,
    notes         = EXCLUDED.notes,
    cas_number    = COALESCE(EXCLUDED.cas_number, ingredients.cas_number),
    updated_at    = NOW()
RETURNING id
"""

_UPSERT_ALIAS = """
INSERT INTO ingredient_aliases (ingredient_id, alias, language)
VALUES ($1, $2, 'en')
ON CONFLICT (ingredient_id, alias) DO NOTHING
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> list[dict]:
    """Load and return a JSON array from *path*."""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_records(
    entries: list[dict],
) -> list[tuple]:
    """
    Convert raw JSON dicts into (name, inci_name, e_number, cas_number,
    ingredient_type, safety_level, score_penalty, concerns, eu_status,
    sources, notes, aliases) tuples.
    """
    rows = []
    for entry in entries:
        name = entry["name"].lower().strip()
        inci_name = entry.get("inci_name") or None
        e_number = entry.get("e_number") or None
        cas_number = entry.get("cas_number") or None
        ingredient_type = entry.get("ingredient_type")
        safety_level = entry.get("safety_level")
        score_penalty = int(entry.get("score_penalty", 0))
        concerns = entry.get("concerns") or []
        eu_status = entry.get("eu_status")
        sources = entry.get("sources") or []
        notes = entry.get("notes") or None
        aliases = [a for a in (entry.get("aliases") or []) if a]

        rows.append((
            name,
            inci_name,
            e_number,
            cas_number,
            ingredient_type,
            safety_level,
            score_penalty,
            concerns,
            eu_status,
            sources,
            notes,
            aliases,
        ))
    return rows


# ---------------------------------------------------------------------------
# Core seeding logic
# ---------------------------------------------------------------------------


async def _seed_batch(
    conn: asyncpg.Connection,
    records: list[tuple],
    source_label: str,
) -> tuple[int, int]:
    """
    Upsert *records* within a single transaction.

    Returns (ingredients_upserted, aliases_upserted).
    """
    ingredients_count = 0
    aliases_count = 0

    async with conn.transaction():
        for rec in records:
            (
                name, inci_name, e_number, cas_number, ingredient_type,
                safety_level, score_penalty, concerns,
                eu_status, sources, notes, aliases,
            ) = rec

            ingredient_id: int = await conn.fetchval(
                _UPSERT_INGREDIENT,
                name, inci_name, e_number, cas_number, ingredient_type,
                safety_level, score_penalty, concerns,
                eu_status, sources, notes,
            )
            ingredients_count += 1

            for alias in aliases:
                result = await conn.execute(_UPSERT_ALIAS, ingredient_id, alias)
                # asyncpg returns "INSERT 0 N" style strings
                if result and result.endswith("1"):
                    aliases_count += 1

    return ingredients_count, aliases_count


async def main() -> None:
    """Entry-point: load all data files and seed the database."""

    # Load data
    print(f"Loading {_E_NUMBERS_PATH.name} ...")
    e_number_entries = _load_json(_E_NUMBERS_PATH)
    print(f"  -> {len(e_number_entries)} E-number entries")

    print(f"Loading {_COSING_PATH.name} ...")
    cosing_entries = _load_json(_COSING_PATH)
    print(f"  -> {len(cosing_entries)} CosIng-flagged entries")

    food_entries: list[dict] = []
    if _FOOD_PATH.exists():
        print(f"Loading {_FOOD_PATH.name} ...")
        food_entries = _load_json(_FOOD_PATH)
        print(f"  -> {len(food_entries)} food-flagged entries")
    else:
        print(f"(No {_FOOD_PATH.name} found — skipping)")

    fragrance_entries: list[dict] = []
    if _FRAGRANCE_PATH.exists():
        print(f"Loading {_FRAGRANCE_PATH.name} ...")
        fragrance_entries = _load_json(_FRAGRANCE_PATH)
        print(f"  -> {len(fragrance_entries)} fragrance allergen entries")
    else:
        print(f"(No {_FRAGRANCE_PATH.name} found — skipping)")

    # Build typed records
    e_records = _build_records(e_number_entries)
    c_records = _build_records(cosing_entries)
    f_records = _build_records(food_entries)
    fr_records = _build_records(fragrance_entries)

    # Connect
    print(f"\nConnecting to database ...")
    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    print("  -> Connected.")

    try:
        # Seed E-numbers
        print("\nSeeding E-numbers ...")
        e_ing, e_ali = await _seed_batch(conn, e_records, "e_numbers")
        print(f"  -> {e_ing} ingredients upserted, {e_ali} aliases inserted")

        # Seed CosIng
        print("\nSeeding CosIng-flagged cosmetic ingredients ...")
        c_ing, c_ali = await _seed_batch(conn, c_records, "cosing")
        print(f"  -> {c_ing} ingredients upserted, {c_ali} aliases inserted")

        # Seed food-flagged
        if f_records:
            print("\nSeeding food-flagged ingredients ...")
            f_ing, f_ali = await _seed_batch(conn, f_records, "food")
            print(f"  -> {f_ing} ingredients upserted, {f_ali} aliases inserted")
        else:
            f_ing = f_ali = 0

        if fr_records:
            print("\nSeeding fragrance allergen ingredients ...")
            fr_ing, fr_ali = await _seed_batch(conn, fr_records, "fragrance")
            print(f"  -> {fr_ing} ingredients upserted, {fr_ali} aliases inserted")
        else:
            fr_ing = fr_ali = 0

    finally:
        await conn.close()

    # Summary
    total_ing = e_ing + c_ing + f_ing + fr_ing
    total_ali = e_ali + c_ali + f_ali + fr_ali
    print(
        f"\nDone. Total: {total_ing} ingredients upserted, "
        f"{total_ali} aliases inserted."
    )


if __name__ == "__main__":
    asyncio.run(main())
