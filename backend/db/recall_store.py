"""
FDA food enforcement recall integration — openFDA API.

Source: openFDA food enforcement API — public, no API key required.
  https://api.fda.gov/food/enforcement.json

Writes into the shared `recalls` table with source='fda'.
Mirrors the structure of db/rasff_store.py.

The FDA RSS feed was retired in favour of this module because the RSS
only exposes the rolling ~20 most recent items; openFDA has the full
dataset (~28 K food enforcement records from 2012 onwards).

Weekly delta sync (last 45 days — called by weekly_sync.sh):
    python -m db.recall_store

One-time full backfill (2012 to present):
    python -m db.recall_store --backfill

check_product_recalls() queries BOTH the local table (FTS) AND the
openFDA API in real time so results are always current.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from db.connection import get_conn

_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# ---------------------------------------------------------------------------
# API config
# ---------------------------------------------------------------------------

# openFDA food enforcement API — queryable by product description, date, etc.
OPENFDA_FOOD_URL = "https://api.fda.gov/food/enforcement.json"

# openFDA imposes a skip+limit cap of 26,000 per query; we use year-by-year
# date-range pagination to stay within this ceiling for the full backfill.
_OPENFDA_PAGE_SIZE = 1000

# Earliest year with records in the openFDA food enforcement dataset.
_BACKFILL_START_YEAR = 2012

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS recalls (
    id           SERIAL PRIMARY KEY,
    source       TEXT        NOT NULL DEFAULT 'fda',
    guid         TEXT        UNIQUE,
    title        TEXT        NOT NULL,
    description  TEXT,
    risk_level   TEXT,                        -- Class I / Class II / Class III
    category     TEXT,
    countries    TEXT[]      NOT NULL DEFAULT '{}',
    link         TEXT,
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_FTS_INDEX = """
CREATE INDEX IF NOT EXISTS recalls_fts_idx
    ON recalls
    USING GIN (
        to_tsvector('english',
            title || ' ' || COALESCE(description, '')
        )
    );
"""

_CREATE_PUBLISHED_INDEX = """
CREATE INDEX IF NOT EXISTS recalls_published_at_idx
    ON recalls (published_at DESC);
"""


async def ensure_recalls_table() -> None:
    async with get_conn() as conn:
        await conn.execute(_CREATE_TABLE)
        await conn.execute(_CREATE_FTS_INDEX)
        await conn.execute(_CREATE_PUBLISHED_INDEX)


# ---------------------------------------------------------------------------
# Risk level mapping
# FDA classification → recalls.risk_level
# ---------------------------------------------------------------------------

def _classification_to_risk(cls: str | None) -> str | None:
    """Map FDA Class I/II/III to our risk_level field."""
    if not cls:
        return None
    cls_lower = cls.lower()
    if "class i" in cls_lower and "class ii" not in cls_lower:
        return "serious"
    if "class ii" in cls_lower:
        return "high"
    if "class iii" in cls_lower:
        return "medium"
    return None


# ---------------------------------------------------------------------------
# openFDA record parser
# ---------------------------------------------------------------------------

def _parse_openfda_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map one openFDA food enforcement record to a recalls-table row dict.
    Returns None for records that should be skipped (no recall_number or
    product_description).
    """
    recall_number = (raw.get("recall_number") or "").strip()
    if not recall_number:
        return None

    product_desc = (raw.get("product_description") or "").strip()
    if not product_desc:
        return None

    pub_date: datetime | None = None
    raw_date = raw.get("report_date")
    if raw_date:
        try:
            pub_date = datetime.strptime(raw_date, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # openFDA product_type: "Food", "Drugs", "Devices", "Animal Food", etc.
    product_type = (raw.get("product_type") or "food").strip().lower()

    return {
        "guid":         recall_number,
        "title":        product_desc[:400],
        "description":  (raw.get("reason_for_recall") or "").strip() or None,
        "risk_level":   _classification_to_risk(raw.get("classification")),
        "category":     product_type,
        "countries":    ["US"],
        "published_at": pub_date,
    }


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

_UPSERT_FDA_RECALL = """
INSERT INTO recalls
    (source, guid, title, description, risk_level, category, countries, link, published_at)
VALUES
    ('fda', $1, $2, $3, $4, $5, $6, NULL, $7)
ON CONFLICT (guid) DO UPDATE SET
    title        = EXCLUDED.title,
    description  = EXCLUDED.description,
    risk_level   = EXCLUDED.risk_level,
    category     = EXCLUDED.category,
    countries    = EXCLUDED.countries,
    fetched_at   = NOW()
RETURNING (xmax = 0) AS inserted
"""


async def _upsert_fda_batch(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    """
    Upsert a batch of parsed recall rows within a single connection.
    Returns (inserted, updated, errors).
    """
    inserted = updated = errors = 0
    async with get_conn() as conn:
        for row in rows:
            try:
                was_inserted = await conn.fetchval(
                    _UPSERT_FDA_RECALL,
                    row["guid"],
                    row["title"],
                    row["description"],
                    row["risk_level"],
                    row["category"],
                    row["countries"],
                    row["published_at"],
                )
                if was_inserted:
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                print(f"  [FDA] DB error for {row['guid']!r}: {e}")
                errors += 1
    return inserted, updated, errors


# ---------------------------------------------------------------------------
# openFDA pagination helpers
# ---------------------------------------------------------------------------

async def _fetch_openfda_range(
    http_client: httpx.AsyncClient,
    date_start: str,
    date_end: str,
    stats: dict[str, int],
    label: str = "",
) -> None:
    """
    Fetch all food enforcement records in [date_start, date_end] (YYYYMMDD)
    and upsert into the recalls table.  Uses skip/limit pagination within the
    date window — safe because no single year exceeds the 25K skip ceiling.
    """
    skip = 0
    while True:
        params: dict[str, Any] = {
            "search": f"report_date:[{date_start} TO {date_end}]",
            "limit":  _OPENFDA_PAGE_SIZE,
            "skip":   skip,
        }
        try:
            r = await http_client.get(OPENFDA_FOOD_URL, params=params)
            if r.status_code == 404:
                break  # no records in this window
            r.raise_for_status()
            data = r.json()
        except httpx.TimeoutException as e:
            print(f"  [FDA] Timeout {label} skip={skip}: {e}")
            stats["errors"] += 1
            break
        except httpx.HTTPStatusError as e:
            print(f"  [FDA] HTTP {e.response.status_code} {label} skip={skip}: {e}")
            stats["errors"] += 1
            break
        except Exception as e:
            print(f"  [FDA] Fetch error {label} skip={skip}: {e}")
            stats["errors"] += 1
            break

        results = data.get("results", [])
        if not results:
            break

        total = data["meta"]["results"]["total"]
        stats["fetched"] += len(results)

        batch: list[dict[str, Any]] = []
        for raw in results:
            parsed = _parse_openfda_record(raw)
            if parsed is None:
                stats["skipped"] += 1
            else:
                batch.append(parsed)

        if batch:
            ins, upd, err = await _upsert_fda_batch(batch)
            stats["inserted"] += ins
            stats["updated"]  += upd
            stats["errors"]   += err

        skip += len(results)
        if skip >= total:
            break


# ---------------------------------------------------------------------------
# Main fetch + store
# ---------------------------------------------------------------------------

async def fetch_and_store_openfda(
    *,
    since_date: str | None = None,
    max_years: int | None = None,
) -> dict[str, int]:
    """
    Fetch FDA food enforcement records from openFDA and upsert into the
    local `recalls` table (source='fda').

    Args:
        since_date: Start date as "YYYYMMDD". If None, runs a full backfill
                    from _BACKFILL_START_YEAR to the current year, paginating
                    year by year to stay within the openFDA 26K skip ceiling.
                    If set, fetches only records from since_date to today —
                    safe for delta/weekly syncs where the window is small.
        max_years:  Limit to this many years (for testing). None = all years.

    Returns:
        dict with fetched, inserted, updated, skipped, errors counts.
    """
    stats: dict[str, int] = {
        "fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": 0,
    }

    today_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    current_year = datetime.now(tz=timezone.utc).year

    if since_date:
        print(f"[FDA] Starting delta sync from {since_date} to {today_str} ...")
    else:
        print(f"[FDA] Starting full backfill {_BACKFILL_START_YEAR}–{current_year} ...")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        ) as http_client:

            if since_date:
                # Delta sync: single date-range window
                await _fetch_openfda_range(
                    http_client, since_date, today_str, stats,
                    label=f"[{since_date}→{today_str}]",
                )
            else:
                # Full backfill: iterate year by year
                years = list(range(_BACKFILL_START_YEAR, current_year + 1))
                if max_years is not None:
                    years = years[:max_years]

                for year in years:
                    year_start = f"{year}0101"
                    year_end   = f"{year}1231"
                    await _fetch_openfda_range(
                        http_client, year_start, year_end, stats,
                        label=f"[year={year}]",
                    )
                    print(
                        f"[FDA] Year {year} done — "
                        f"fetched={stats['fetched']} inserted={stats['inserted']} "
                        f"updated={stats['updated']} skipped={stats['skipped']} "
                        f"errors={stats['errors']}"
                    )

    except Exception as e:
        print(f"[FDA] Fatal error — sync aborted (non-fatal to caller): {e}")
        stats["errors"] += 1

    print(
        f"[FDA] Done. "
        f"fetched={stats['fetched']} inserted={stats['inserted']} "
        f"updated={stats['updated']} skipped={stats['skipped']} "
        f"errors={stats['errors']}"
    )
    return stats


# ---------------------------------------------------------------------------
# Product recall checker — local DB + real-time openFDA query
# ---------------------------------------------------------------------------

_FTS_QUERY = """
SELECT id, title, description, risk_level, category, link, published_at
FROM recalls
WHERE
    to_tsvector('english', title || ' ' || COALESCE(description, ''))
    @@ plainto_tsquery('english', $1)
    AND (published_at IS NULL OR published_at > NOW() - INTERVAL '2 years')
ORDER BY published_at DESC NULLS LAST
LIMIT 5
"""

_BARCODE_QUERY = """
SELECT id, title, description, risk_level, category, link, published_at
FROM recalls
WHERE
    (description ILIKE '%' || $1 || '%' OR title ILIKE '%' || $1 || '%')
    AND (published_at IS NULL OR published_at > NOW() - INTERVAL '2 years')
ORDER BY published_at DESC NULLS LAST
LIMIT 5
"""

_STOP = {"the", "a", "an", "of", "and", "with", "for", "in", "by", "de", "le", "la"}


def _build_fts_query(product_name: str, brand: str) -> str:
    tokens = re.findall(r"[a-zA-Z0-9]+", f"{product_name} {brand}")
    meaningful = [t for t in tokens if len(t) > 2 and t.lower() not in _STOP]
    return " ".join(meaningful[:8])


async def _query_openfda(product_name: str, brand: str) -> list[dict[str, Any]]:
    """
    Real-time query to openFDA food enforcement API.
    Returns a list of matching recall dicts.
    """
    tokens = re.findall(r"[a-zA-Z]{3,}", f"{product_name} {brand}")
    tokens = [t for t in tokens if t.lower() not in _STOP][:4]
    if not tokens:
        return []

    search_term = " ".join(tokens)
    params = {
        "search": f'product_description:"{search_term}"',
        "limit":  5,
        "sort":   "report_date:desc",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(OPENFDA_FOOD_URL, params=params)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"  [RECALLS] openFDA query failed (non-fatal): {e}")
        return []

    results = []
    for item in data.get("results", []):
        pub_date = None
        raw_date = item.get("report_date")
        if raw_date:
            try:
                pub_date = datetime.strptime(raw_date, "%Y%m%d")
            except ValueError:
                pass

        results.append({
            "id":           f"fda_{item.get('recall_number', '')}",
            "title":        item.get("product_description", "Unknown product")[:200],
            "description":  item.get("reason_for_recall"),
            "risk_level":   _classification_to_risk(item.get("classification")),
            "category":     (item.get("product_type") or "food").lower(),
            "link":         None,
            "published_at": pub_date,
        })

    return results


async def check_product_recalls(
    product_name: str,
    brand: str,
    barcode: str,
) -> list[dict[str, Any]]:
    """
    Return recalls that plausibly match this product.
    Checks:
      1. Local DB full-text search (fast, offline-capable)
      2. Local DB barcode literal search
      3. Real-time openFDA API query (covers the ~7-day lag window)
    Deduplicates and returns combined results capped at 5.
    """
    seen_titles: set[str] = set()
    results: list[dict[str, Any]] = []

    # 1 + 2: local DB
    fts_query = _build_fts_query(product_name, brand)
    async with get_conn() as conn:
        if fts_query.strip():
            rows = await conn.fetch(_FTS_QUERY, fts_query)
            for row in rows:
                d = dict(row)
                key = d["title"].lower()[:80]
                if key not in seen_titles:
                    seen_titles.add(key)
                    results.append(d)

        if barcode and len(barcode) >= 8:
            rows = await conn.fetch(_BARCODE_QUERY, barcode)
            for row in rows:
                d = dict(row)
                key = d["title"].lower()[:80]
                if key not in seen_titles:
                    seen_titles.add(key)
                    results.append(d)

    # 3: real-time openFDA — catches recalls within the ~7-day indexing lag
    openfda_results = await _query_openfda(product_name, brand)
    for r in openfda_results:
        key = r["title"].lower()[:80]
        if key not in seen_titles:
            seen_titles.add(key)
            results.append(r)

    return results[:5]


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

import re  # noqa: E402  (needed by _build_fts_query above)


async def _main() -> None:
    from db.connection import get_pool, close_pool
    await get_pool()
    await ensure_recalls_table()

    backfill = "--backfill" in sys.argv
    if backfill:
        # One-time full historical backfill (2012 → today)
        stats = await fetch_and_store_openfda()
    else:
        # Weekly delta: last 45 days (covers the ~7-day openFDA indexing lag
        # with plenty of overlap so no recalls slip through the cracks)
        since = (datetime.now(tz=timezone.utc) - timedelta(days=45)).strftime("%Y%m%d")
        stats = await fetch_and_store_openfda(since_date=since)

    print(stats)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(_main())
