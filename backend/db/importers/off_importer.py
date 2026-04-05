"""
Open Food Facts CSV dump importer.

Streams the gzipped CSV line-by-line (no full-file load) and batch-upserts
products + raw ingredients into PostgreSQL.

Usage:
    # Stream from a local file:
    python -m db.importers.off_importer --file /path/to/en.openfoodfacts.org.products.csv.gz

    # Stream directly from the OFF CDN:
    python -m db.importers.off_importer --url

    # Limit rows and skip ingredient linking:
    python -m db.importers.off_importer --url --limit 50000 --skip-ingredients
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
csv.field_size_limit(sys.maxsize)
import gzip
import io
import re
import sys
import time
from pathlib import Path
from typing import AsyncIterator, Optional
from urllib.request import urlopen

import asyncpg
from dotenv import load_dotenv
import os

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

DATABASE_URL = os.environ.get("DATABASE_URL")
OFF_DUMP_URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"

PRODUCT_TYPE = "food"
SOURCE = "off"
BATCH_SIZE = 500
LOG_INTERVAL = 10_000  # print progress every N rows

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_UPSERT_PRODUCT = """
INSERT INTO products (
    barcode, name, brand, product_type, image_url,
    nutriscore, nova_group, categories, source, last_synced_at
)
VALUES ($1, $2, $3, 'food', $4, $5, $6, $7, 'off', NOW())
ON CONFLICT (barcode) DO UPDATE SET
    name           = COALESCE(EXCLUDED.name,       products.name),
    brand          = COALESCE(EXCLUDED.brand,      products.brand),
    nutriscore     = COALESCE(EXCLUDED.nutriscore, products.nutriscore),
    nova_group     = COALESCE(EXCLUDED.nova_group, products.nova_group),
    last_synced_at = NOW()
RETURNING id
"""

_INSERT_PRODUCT_INGREDIENT = """
INSERT INTO product_ingredients (product_id, ingredient_name, ingredient_id, position)
VALUES ($1, $2, NULL, $3)
ON CONFLICT (product_id, position) DO NOTHING
"""

_INSERT_SYNC_LOG = """
INSERT INTO sync_log (source, started_at, status)
VALUES ('off', NOW(), 'running')
RETURNING id
"""

_UPDATE_SYNC_LOG_PROGRESS = """
UPDATE sync_log
SET records_added   = $2,
    records_updated = $3
WHERE id = $1
"""

_UPDATE_SYNC_LOG_COMPLETE = """
UPDATE sync_log
SET completed_at    = NOW(),
    status          = $2,
    records_added   = $3,
    records_updated = $4,
    error           = $5
WHERE id = $1
"""

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_NUTRISCORE_RE = re.compile(r"^[a-e]$")
_NOVA_RE = re.compile(r"^[1-4]$")


def _parse_nutriscore(raw: str) -> Optional[str]:
    """Return lowercase single letter a-e, or None."""
    v = raw.strip().lower()
    return v if _NUTRISCORE_RE.match(v) else None


def _parse_nova(raw: str) -> Optional[int]:
    """Return int 1-4, or None."""
    try:
        v = int(raw.strip())
        return v if 1 <= v <= 4 else None
    except (ValueError, AttributeError):
        return None


def _parse_categories(raw: str) -> list[str]:
    """Split comma-separated categories, strip whitespace."""
    if not raw.strip():
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def _parse_ingredients(raw: str) -> list[str]:
    """
    Split raw ingredients text by comma and semicolon.
    Returns non-empty stripped tokens.
    """
    if not raw.strip():
        return []
    parts = re.split(r"[,;]", raw)
    return [p.strip() for p in parts if p.strip()]


def _map_row(row: dict) -> Optional[dict]:
    """
    Map a CSV row dict to a product dict.
    Returns None if barcode is missing/empty.
    """
    barcode = row.get("code", "").strip()
    if not barcode:
        return None

    name = (
        row.get("product_name_en", "").strip()
        or row.get("product_name", "").strip()
        or None
    )
    brand = row.get("brands", "").strip() or None
    image_url = row.get("image_url", "").strip() or None
    nutriscore = _parse_nutriscore(row.get("nutriscore_grade", ""))
    nova_group = _parse_nova(row.get("nova_group", ""))
    categories = _parse_categories(row.get("categories_en", ""))
    ingredients_text = (
        row.get("ingredients_text_en", "").strip()
        or row.get("ingredients_text", "").strip()
    )

    return {
        "barcode": barcode,
        "name": name,
        "brand": brand,
        "image_url": image_url,
        "nutriscore": nutriscore,
        "nova_group": nova_group,
        "categories": categories,
        "ingredients_text": ingredients_text,
    }


# ---------------------------------------------------------------------------
# Streaming reader
# ---------------------------------------------------------------------------


def _open_gz_stream(path: Optional[str], use_url: bool):
    """
    Return a (binary) file-like object for the gzip source.
    Streams byte-by-byte from URL; opens a local file otherwise.
    """
    if use_url:
        print(f"Streaming from {OFF_DUMP_URL} ...")
        resp = urlopen(OFF_DUMP_URL)
        return gzip.GzipFile(fileobj=resp)
    else:
        print(f"Reading from {path} ...")
        return gzip.open(path, "rb")


# ---------------------------------------------------------------------------
# DB batch operations
# ---------------------------------------------------------------------------


async def _flush_batch(
    conn: asyncpg.Connection,
    batch: list[dict],
    skip_ingredients: bool,
) -> tuple[int, int]:
    """
    Upsert a batch of product dicts within a single transaction.

    Returns (products_upserted, ingredients_rows_inserted).
    """
    products_upserted = 0
    ingredients_rows = 0

    async with conn.transaction():
        for product in batch:
            product_id = await conn.fetchval(
                _UPSERT_PRODUCT,
                product["barcode"],
                product["name"],
                product["brand"],
                product["image_url"],
                product["nutriscore"],
                product["nova_group"],
                product["categories"],
            )
            products_upserted += 1

            if not skip_ingredients and product["ingredients_text"]:
                tokens = _parse_ingredients(product["ingredients_text"])
                for pos, token in enumerate(tokens, start=1):
                    if pos > 32767:
                        break
                    await conn.execute(
                        _INSERT_PRODUCT_INGREDIENT,
                        product_id,
                        token,
                        pos,
                    )
                    ingredients_rows += 1

    return products_upserted, ingredients_rows


# ---------------------------------------------------------------------------
# Main import coroutine
# ---------------------------------------------------------------------------


async def _run_import(
    file_path: Optional[str],
    use_url: bool,
    limit: Optional[int],
    skip_ingredients: bool,
) -> None:
    if DATABASE_URL is None:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)

    # Create sync_log entry
    sync_log_id: int = await conn.fetchval(_INSERT_SYNC_LOG)
    print(f"sync_log id={sync_log_id} created.")

    total_products = 0
    total_ingredients = 0
    rows_seen = 0
    start_time = time.monotonic()
    batch: list[dict] = []
    error_msg: Optional[str] = None

    try:
        gz_stream = _open_gz_stream(file_path, use_url)
        text_stream = io.TextIOWrapper(gz_stream, encoding="utf-8", errors="replace")
        reader = csv.DictReader(text_stream, delimiter="\t")

        for raw_row in reader:
            if limit is not None and rows_seen >= limit:
                break

            rows_seen += 1

            product = _map_row(raw_row)
            if product is None:
                continue

            batch.append(product)

            if len(batch) >= BATCH_SIZE:
                p, i = await _flush_batch(conn, batch, skip_ingredients)
                total_products += p
                total_ingredients += i
                batch.clear()

            # Progress logging
            if rows_seen % LOG_INTERVAL == 0:
                elapsed = time.monotonic() - start_time
                rate = rows_seen / elapsed if elapsed > 0 else 0
                print(
                    f"  [{rows_seen:,} rows | {total_products:,} products | "
                    f"{total_ingredients:,} ingredient rows | {rate:.0f} rows/s]"
                )
                # Update sync_log with current counts
                await conn.execute(
                    _UPDATE_SYNC_LOG_PROGRESS,
                    sync_log_id,
                    total_products,
                    0,  # records_updated not tracked separately
                )

        # Flush remaining batch
        if batch:
            p, i = await _flush_batch(conn, batch, skip_ingredients)
            total_products += p
            total_ingredients += i

    except Exception as exc:
        error_msg = str(exc)
        print(f"\nERROR: {error_msg}", file=sys.stderr)

    finally:
        elapsed = time.monotonic() - start_time
        status = "failed" if error_msg else "completed"

        await conn.execute(
            _UPDATE_SYNC_LOG_COMPLETE,
            sync_log_id,
            status,
            total_products,
            0,
            error_msg,
        )

        await conn.close()

        print(
            f"\n{'=' * 60}\n"
            f"Import {status}.\n"
            f"  Rows scanned  : {rows_seen:,}\n"
            f"  Products saved: {total_products:,}\n"
            f"  Ingredient rows: {total_ingredients:,}\n"
            f"  Elapsed       : {elapsed:.1f}s\n"
            f"{'=' * 60}"
        )

        if error_msg:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Open Food Facts CSV dump into the safescan database."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--file",
        metavar="PATH",
        help="Path to a local .csv.gz dump file.",
    )
    source.add_argument(
        "--url",
        action="store_true",
        help=f"Stream directly from {OFF_DUMP_URL}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after processing N CSV rows (useful for testing).",
    )
    parser.add_argument(
        "--skip-ingredients",
        action="store_true",
        help="Do not insert product_ingredients rows (faster for product-only syncs).",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(
        _run_import(
            file_path=args.file,
            use_url=args.url,
            limit=args.limit,
            skip_ingredients=args.skip_ingredients,
        )
    )


if __name__ == "__main__":
    main()
