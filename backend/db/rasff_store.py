"""
EU RASFF (Rapid Alert System for Food and Feed) recall integration.

Source: EC DG SANTE Datalake API — public, no authentication required.
  https://api.datalake.sante.service.ec.europa.eu/rasff/irasff-general-info-view

Mirrors the structure of db/recall_store.py.
Writes into the shared `recalls` table with source='rasff'.

Usage (standalone — populates recalls table from RASFF):
    python -m db.rasff_store
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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

RASFF_API_URL = (
    "https://api.datalake.sante.service.ec.europa.eu"
    "/rasff/irasff-general-info-view"
)
_API_VERSION = "v1.1"

# ---------------------------------------------------------------------------
# Risk level mapping
# RASFF RISK_DECISION_DESC → recalls.risk_level
# Entries with no risk are skipped — they are non-safety informational alerts.
# ---------------------------------------------------------------------------

_RISK_MAP: dict[str, str | None] = {
    "serious":             "serious",
    "potentially serious": "high",
    "potential risk":      "high",
    "not serious":         "medium",
    "undecided":           "medium",
    "no risk":             None,   # skip — not a safety recall
}


# ---------------------------------------------------------------------------
# Record parser
# ---------------------------------------------------------------------------

def _parse_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Map one RASFF API record to a recalls-table row dict.
    Returns None for entries that should be skipped (no-risk or incomplete).
    """
    risk_raw = (raw.get("RISK_DECISION_DESC") or "").strip().lower()
    risk_level = _RISK_MAP.get(risk_raw, "medium")
    if risk_level is None:
        return None  # skip no-risk informational entries

    notif_ref = (raw.get("NOTIFICATION_REFERENCE") or "").strip()
    if not notif_ref:
        return None

    product_name = (raw.get("PRODUCT_NAME") or "").strip()
    subject      = (raw.get("NOTIF_SUBJECT")  or "").strip()
    title = (product_name or subject)[:400]
    if not title:
        return None

    # Countries: "Germany *** France *** Italy" → ["Germany", "France", "Italy"]
    dist_raw = raw.get("DISTRIBUTION_COUNTRY_DESC") or ""
    countries = [c.strip() for c in dist_raw.split("***") if c.strip()]

    pub_date: datetime | None = None
    raw_date = raw.get("NOTIF_DATE")
    if raw_date:
        try:
            pub_date = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return {
        "guid":         notif_ref,
        "title":        title,
        "description":  subject or None,
        "risk_level":   risk_level,
        "category":     (raw.get("PRODUCT_CATEGORY_DESC") or "").strip() or None,
        "countries":    countries,
        "published_at": pub_date,
    }


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

_UPSERT_RECALL = """
INSERT INTO recalls
    (source, guid, title, description, risk_level, category, countries, link, published_at)
VALUES
    ('rasff', $1, $2, $3, $4, $5, $6, NULL, $7)
ON CONFLICT (guid) DO UPDATE SET
    title        = EXCLUDED.title,
    description  = EXCLUDED.description,
    risk_level   = EXCLUDED.risk_level,
    category     = EXCLUDED.category,
    countries    = EXCLUDED.countries,
    fetched_at   = NOW()
RETURNING (xmax = 0) AS inserted
"""


async def _upsert_batch(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    """
    Upsert a batch of parsed recall rows within a single connection.
    Returns (inserted, updated, errors).
    """
    inserted = updated = errors = 0
    async with get_conn() as conn:
        for row in rows:
            try:
                was_inserted = await conn.fetchval(
                    _UPSERT_RECALL,
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
                print(f"  [RASFF] DB error for {row['guid']!r}: {e}")
                errors += 1
    return inserted, updated, errors


# ---------------------------------------------------------------------------
# Main fetch + store
# ---------------------------------------------------------------------------

async def fetch_and_store_rasff(
    *,
    max_pages: int | None = None,
) -> dict[str, int]:
    """
    Fetch all RASFF notifications from the EC DG SANTE Datalake API and upsert
    them into the local `recalls` table (source='rasff').

    Pagination is cursor-based via `nextLink`. The API does not support date
    filtering, so all pages are fetched each run; upserts are idempotent.
    Entries with RISK_DECISION_DESC='no risk' are skipped.

    Args:
        max_pages: Stop after this many pages (for testing). None = all pages.

    Returns:
        dict with fetched, inserted, updated, skipped, errors counts.
    """
    stats: dict[str, int] = {
        "fetched": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": 0,
    }

    print(f"[RASFF] Starting fetch ...")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        ) as http_client:

            url: str | None = RASFF_API_URL
            first_page = True
            page_count = 0

            while url:
                if max_pages is not None and page_count >= max_pages:
                    print(f"[RASFF] Stopped at max_pages={max_pages}.")
                    break

                try:
                    if first_page:
                        r = await http_client.get(
                            url,
                            params={"format": "json", "api-version": _API_VERSION},
                        )
                        first_page = False
                    else:
                        r = await http_client.get(url)  # nextLink already has params

                    r.raise_for_status()
                    data = r.json()

                except httpx.TimeoutException as e:
                    print(f"[RASFF] Timeout on page {page_count + 1}: {e}")
                    stats["errors"] += 1
                    break
                except httpx.HTTPStatusError as e:
                    print(f"[RASFF] HTTP {e.response.status_code} on page {page_count + 1}: {e}")
                    stats["errors"] += 1
                    break
                except Exception as e:
                    print(f"[RASFF] Fetch error on page {page_count + 1}: {e}")
                    stats["errors"] += 1
                    break

                records = data.get("value", [])
                page_count += 1
                stats["fetched"] += len(records)

                batch: list[dict[str, Any]] = []
                for raw in records:
                    parsed = _parse_record(raw)
                    if parsed is None:
                        stats["skipped"] += 1
                    else:
                        batch.append(parsed)

                if batch:
                    ins, upd, err = await _upsert_batch(batch)
                    stats["inserted"] += ins
                    stats["updated"]  += upd
                    stats["errors"]   += err

                if page_count % 20 == 0:
                    print(
                        f"[RASFF] Page {page_count}: "
                        f"fetched={stats['fetched']} new={stats['inserted']} "
                        f"updated={stats['updated']} skipped={stats['skipped']}"
                    )

                url = data.get("nextLink")

    except Exception as e:
        # Never let a RASFF outage crash the caller (weekly_sync, startup, etc.)
        print(f"[RASFF] Fatal error — sync aborted (non-fatal to caller): {e}")
        stats["errors"] += 1

    print(
        f"[RASFF] Done. pages={page_count} fetched={stats['fetched']} "
        f"inserted={stats['inserted']} updated={stats['updated']} "
        f"skipped={stats['skipped']} errors={stats['errors']}"
    )
    return stats


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

async def _main() -> None:
    from db.connection import get_pool, close_pool
    from db.recall_store import ensure_recalls_table
    await get_pool()
    await ensure_recalls_table()
    stats = await fetch_and_store_rasff()
    print(stats)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(_main())
