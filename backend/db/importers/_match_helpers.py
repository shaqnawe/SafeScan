"""
Shared SQL builders and matching utilities for ingredient enrichment importers.

Used by: iarc_importer.py, prop65_importer.py
Any future source-specific importer that enriches the `ingredients` table
via CAS number or name matching should use these helpers.

Design contract:
- These helpers ONLY append to `concerns` and `sources`, and fill `cas_number`
  if missing.  They never touch `safety_level`, `eu_status`, or `score_penalty`.
- Matching is two-pass: CAS number (preferred) then canonical/INCI name.
- Returns are string literals: "cas", "name", or "unmatched" — callers use
  these to accumulate stats without relying on asyncpg Record truthiness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import asyncpg


# ---------------------------------------------------------------------------
# SQL builders
# ---------------------------------------------------------------------------

def build_update_sql(source: str) -> tuple[str, str]:
    """
    Build CAS-match and name-match UPDATE SQL for the given source label.

    Both queries:
    - Append `concern_tag` ($2) to `concerns` array, deduplicating.
    - Append `source` to `sources` array, deduplicating.
    - Fill `cas_number` ($1) if the row currently has none.
    - Set `updated_at = NOW()`.
    - Return the matched row id(s) via RETURNING.

    Returns (cas_sql, name_sql).
    Parameters for cas_sql:  $1=cas_number, $2=concern_tag
    Parameters for name_sql: $1=cas_number, $2=concern_tag, $3=agent_name
    """
    _set_clause = f"""
    SET
        cas_number = COALESCE(ingredients.cas_number, $1),
        concerns   = ARRAY(
                       SELECT DISTINCT unnest(
                           COALESCE(ingredients.concerns, ARRAY[]::text[]) ||
                           ARRAY[$2]::text[]
                       )
                     ),
        sources    = ARRAY(
                       SELECT DISTINCT unnest(
                           COALESCE(ingredients.sources, ARRAY[]::text[]) ||
                           ARRAY['{source}']::text[]
                       )
                     ),
        updated_at = NOW()
"""
    cas_sql = f"UPDATE ingredients{_set_clause}WHERE cas_number = $1 RETURNING id"

    name_sql = (
        f"UPDATE ingredients{_set_clause}"
        "WHERE lower(name) = lower($3)\n"
        "   OR lower(inci_name) = lower($3)\n"
        "RETURNING id"
    )
    return cas_sql, name_sql


# ---------------------------------------------------------------------------
# Two-pass match-and-update
# ---------------------------------------------------------------------------

async def match_and_update(
    conn: asyncpg.Connection,
    cas_number: Optional[str],
    agent_name: str,
    concern_tag: str,
    cas_sql: str,
    name_sql: str,
) -> str:
    """
    Try to match an ingredient row and apply the concern tag.

    Pass 1 — CAS number (preferred, only attempted when cas_number is set).
    Pass 2 — case-insensitive name match against `name` and `inci_name`.

    Returns one of: "cas", "name", "unmatched".
    Callers should accumulate counts by comparing the return value to these
    string literals rather than checking truthiness of asyncpg Records.
    """
    if cas_number:
        rows = await conn.fetch(cas_sql, cas_number, concern_tag)
        if rows:
            return "cas"

    rows = await conn.fetch(name_sql, cas_number, concern_tag, agent_name)
    if rows:
        return "name"

    return "unmatched"


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_latest_csv(seed_dir: Path, prefix: str) -> Optional[Path]:
    """
    Return the most recently dated {prefix}_*.csv in seed_dir, or None.

    Convention: files are named  {prefix}_YYYY-MM-DD.csv  so lexicographic
    reverse sort gives the newest first.
    """
    candidates = sorted(seed_dir.glob(f"{prefix}_*.csv"), reverse=True)
    return candidates[0] if candidates else None
