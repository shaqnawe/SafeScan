"""
Product recall integration.

Sources:
  1. openFDA food enforcement API — structured JSON, queryable by product name
  2. FDA RSS feed — latest recalls, used for the weekly sync

The `recalls` table is populated from the FDA RSS feed via fetch_and_store_recalls().
check_product_recalls() queries BOTH the local table AND the openFDA API in real time
so results are always current.

Usage (standalone, seeds DB from FDA RSS):
    python -m db.recall_store
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from db.connection import get_conn

_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# FDA RSS — latest food/drug/cosmetic recalls (~100 most recent)
FDA_RSS_URL = (
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/recalls/rss.xml"
)

# openFDA food enforcement API — queryable by product description
OPENFDA_FOOD_URL = "https://api.fda.gov/food/enforcement.json"

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
# FDA RSS parsing
# ---------------------------------------------------------------------------

_NS = {"dc": "http://purl.org/dc/elements/1.1/"}

_EDT_RE = re.compile(r"\s+EDT$|\s+EST$")  # strip timezone suffix for strptime


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = _EDT_RE.sub(" +0000", raw.strip())
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S +0000"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_fda_rss(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []

    items: list[dict] = []
    for item in channel.findall("item"):
        title       = (item.findtext("title") or "").strip()
        link        = (item.findtext("link")  or "").strip()
        description = (item.findtext("description") or "").strip()
        guid_el     = item.find("guid")
        guid        = (guid_el.text or "").strip() if guid_el is not None else ""
        pub_date    = _parse_date(item.findtext("pubDate"))

        if not guid:
            guid = hashlib.sha1(link.encode()).hexdigest()

        if not title:
            continue

        items.append({
            "guid":         guid,
            "title":        title,
            "description":  description or None,
            "risk_level":   None,   # RSS doesn't include class
            "category":     "food",
            "countries":    ["US"],
            "link":         link or None,
            "published_at": pub_date,
        })

    return items


# ---------------------------------------------------------------------------
# Fetch + store (FDA RSS → local DB)
# ---------------------------------------------------------------------------

_UPSERT_RECALL = """
INSERT INTO recalls (guid, title, description, risk_level, category, countries, link, published_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (guid) DO UPDATE SET
    title        = EXCLUDED.title,
    description  = EXCLUDED.description,
    fetched_at   = NOW()
"""


async def fetch_and_store_recalls(url: str = FDA_RSS_URL) -> dict[str, int]:
    """
    Fetch the FDA RSS recall feed and upsert entries into the `recalls` table.
    Returns a dict with 'fetched' and 'upserted' counts.
    """
    print(f"[RECALLS] Fetching {url} ...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        xml_bytes = response.content

    items = _parse_fda_rss(xml_bytes)
    print(f"[RECALLS] Parsed {len(items)} entries from feed.")

    async with get_conn() as conn:
        for item in items:
            await conn.execute(
                _UPSERT_RECALL,
                item["guid"],
                item["title"],
                item["description"],
                item["risk_level"],
                item["category"],
                item["countries"],
                item["link"],
                item["published_at"],
            )

    print(f"[RECALLS] Upserted {len(items)} recall entries.")
    return {"fetched": len(items), "upserted": len(items)}


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


async def _query_openfda(product_name: str, brand: str) -> list[dict[str, Any]]:
    """
    Real-time query to openFDA food enforcement API.
    Returns a list of matching recall dicts.
    """
    # Build a search query from the most meaningful tokens
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
                return []  # no results
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
            "category":     "food",
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
      3. Real-time openFDA API query (current data)
    Deduplicates and returns combined results.
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

    # 3: real-time openFDA
    openfda_results = await _query_openfda(product_name, brand)
    for r in openfda_results:
        key = r["title"].lower()[:80]
        if key not in seen_titles:
            seen_titles.add(key)
            results.append(r)

    return results[:5]  # cap at 5 total


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

async def _main() -> None:
    await ensure_recalls_table()
    stats = await fetch_and_store_recalls()
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
