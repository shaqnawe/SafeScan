"""
OpenFDA drug label importer.

Fetches the openFDA drug/label bulk-download manifest, then streams each
partition zip and imports OTC drug products (barcodes + ingredients) into
the safescan products + product_ingredients tables.

Dataset: ~256 K drug label records; we keep only Human OTC Drug entries that
have a UPC barcode.  Typical yield: ~30–50 K OTC products.

Usage:
    # Full import (downloads all 13 partition files):
    python -m db.importers.openfda_importer

    # Test with first 2 partitions only:
    python -m db.importers.openfda_importer --partitions 2

    # Skip ingredient rows:
    python -m db.importers.openfda_importer --skip-ingredients
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

import asyncpg
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

DATABASE_URL = os.environ.get("DATABASE_URL")

MANIFEST_URL = "https://api.fda.gov/download.json"
BATCH_SIZE   = 200
LOG_INTERVAL = 5_000

# Only import OTC drugs (skip prescription-only products).
OTC_MARKER = "OTC"

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_UPSERT_PRODUCT = """
INSERT INTO products (
    barcode, name, brand, product_type, image_url,
    nutriscore, nova_group, categories, source, last_synced_at
)
VALUES ($1, $2, $3, 'drug', NULL, NULL, NULL, $4, 'openfda', NOW())
ON CONFLICT (barcode) DO UPDATE SET
    name           = COALESCE(EXCLUDED.name,  products.name),
    brand          = COALESCE(EXCLUDED.brand, products.brand),
    last_synced_at = NOW()
RETURNING id
"""

_INSERT_INGREDIENT = """
INSERT INTO product_ingredients (product_id, ingredient_name, ingredient_id, position)
VALUES ($1, $2, NULL, $3)
ON CONFLICT (product_id, position) DO NOTHING
"""

_INSERT_SYNC_LOG = """
INSERT INTO sync_log (source, started_at, status)
VALUES ('openfda', NOW(), 'running')
RETURNING id
"""

_UPDATE_SYNC_LOG_PROGRESS = """
UPDATE sync_log SET records_added = $2, records_updated = $3 WHERE id = $1
"""

_UPDATE_SYNC_LOG_COMPLETE = """
UPDATE sync_log
SET completed_at = NOW(), status = $2,
    records_added = $3, records_updated = $4, error = $5
WHERE id = $1
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first(lst: list, default: str = "") -> str:
    return lst[0].strip() if lst else default


def _parse_ingredient_text(raw: str) -> list[str]:
    """
    Split an openFDA ingredient string into individual ingredient names.

    openFDA ingredient fields look like:
      "Active ingredients Ibuprofen 200 mg"
      "Inactive ingredients Cetostearyl alcohol, glycerin, purified water"

    Strategy: strip the header phrase, then split on comma/semicolon.
    """
    # Remove header phrases like "Active ingredients", "Inactive ingredients"
    text = re.sub(
        r'^(active|inactive)\s+ingredients?\s*',
        '', raw, flags=re.IGNORECASE
    ).strip()

    if not text:
        return []

    parts = re.split(r'[,;]', text)
    tokens = []
    for part in parts:
        # Strip dosage amounts: "Ibuprofen 200 mg" → "Ibuprofen"
        token = re.sub(r'\s+\d[\d.,]*\s*(mg|mcg|%|g|ml|iu|meq)\b.*', '', part,
                       flags=re.IGNORECASE).strip()
        if token and len(token) > 1:
            tokens.append(token)
    return tokens


def _extract_ingredients(record: dict) -> list[str]:
    """
    Return a deduplicated ordered list of ingredient names from a drug record.
    Active ingredients first, then inactive.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(raw_list: list[str]) -> None:
        for raw in raw_list:
            for token in _parse_ingredient_text(raw):
                lower = token.lower()
                if lower not in seen:
                    seen.add(lower)
                    result.append(token)

    _add(record.get("active_ingredient", []))
    _add(record.get("inactive_ingredient", []))
    return result


def _get_partition_urls() -> list[str]:
    """Fetch the openFDA download manifest and return all drug/label partition URLs."""
    print(f"Fetching manifest from {MANIFEST_URL} ...")
    resp = urlopen(MANIFEST_URL)
    manifest = json.loads(resp.read())
    partitions = manifest["results"]["drug"]["label"]["partitions"]
    urls = [p["file"] for p in partitions]
    print(f"  Found {len(urls)} drug/label partition(s).")
    return urls


def _download_partition(url: str) -> list[dict]:
    """Download a partition zip and return its list of drug label records."""
    resp = urlopen(url)
    data = resp.read()
    zf   = zipfile.ZipFile(io.BytesIO(data))
    with zf.open(zf.namelist()[0]) as f:
        return json.load(f).get("results", [])


# ---------------------------------------------------------------------------
# DB batch flush
# ---------------------------------------------------------------------------

async def _flush_batch(
    conn: asyncpg.Connection,
    batch: list[dict],
    skip_ingredients: bool,
) -> tuple[int, int]:
    products_saved    = 0
    ingredient_rows   = 0

    async with conn.transaction():
        for p in batch:
            product_id = await conn.fetchval(
                _UPSERT_PRODUCT,
                p["barcode"],
                p["name"],
                p["brand"],
                p["categories"],
            )
            products_saved += 1

            if not skip_ingredients and p["ingredients"]:
                for pos, token in enumerate(p["ingredients"], 1):
                    if pos > 32767:
                        break
                    await conn.execute(_INSERT_INGREDIENT, product_id, token, pos)
                    ingredient_rows += 1

    return products_saved, ingredient_rows


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

async def _run_import(
    max_partitions: Optional[int],
    skip_ingredients: bool,
) -> None:
    if DATABASE_URL is None:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    sync_log_id: int = await conn.fetchval(_INSERT_SYNC_LOG)
    print(f"sync_log id={sync_log_id}")

    total_products    = 0
    total_ingredients = 0
    records_seen      = 0
    skipped           = 0
    start_time        = time.monotonic()
    batch: list[dict] = []
    error_msg: Optional[str] = None

    try:
        partition_urls = _get_partition_urls()
        if max_partitions:
            partition_urls = partition_urls[:max_partitions]

        for part_idx, url in enumerate(partition_urls, 1):
            print(f"\nPartition {part_idx}/{len(partition_urls)}: {url.split('/')[-1]}")
            records = _download_partition(url)
            print(f"  {len(records):,} records in partition")

            for record in records:
                records_seen += 1

                openfda = record.get("openfda", {})

                # Only OTC drugs
                product_types = openfda.get("product_type", [])
                if not any(OTC_MARKER in pt for pt in product_types):
                    skipped += 1
                    continue

                upcs = openfda.get("upc", [])
                if not upcs:
                    skipped += 1
                    continue

                brand_names = openfda.get("brand_name", [])
                generic_names = openfda.get("generic_name", [])
                manufacturer = openfda.get("manufacturer_name", [])
                purpose_raw  = record.get("purpose", [""])[0] if record.get("purpose") else ""

                name  = _first(brand_names) or _first(generic_names) or None
                brand = _first(manufacturer) or None

                # Build category from purpose (first 80 chars)
                purpose = re.sub(r'\s+', ' ', purpose_raw).strip()[:80]
                categories = [purpose] if purpose else []

                ingredients = _extract_ingredients(record) if not skip_ingredients else []

                # One row per UPC (a label record can cover multiple SKUs)
                for upc in upcs:
                    barcode = upc.strip()
                    if not barcode or len(barcode) not in (12, 13):
                        continue
                    # Normalise 12-digit UPC-A to EAN-13
                    if len(barcode) == 12:
                        barcode = '0' + barcode

                    batch.append({
                        "barcode":     barcode,
                        "name":        name,
                        "brand":       brand,
                        "categories":  categories,
                        "ingredients": ingredients,
                    })

                    if len(batch) >= BATCH_SIZE:
                        p, i = await _flush_batch(conn, batch, skip_ingredients)
                        total_products    += p
                        total_ingredients += i
                        batch.clear()

                if records_seen % LOG_INTERVAL == 0:
                    elapsed = time.monotonic() - start_time
                    rate    = records_seen / elapsed if elapsed else 0
                    print(
                        f"  [{records_seen:,} records | {total_products:,} products | "
                        f"{skipped:,} skipped | {rate:.0f} rec/s]"
                    )
                    await conn.execute(
                        _UPDATE_SYNC_LOG_PROGRESS, sync_log_id, total_products, 0
                    )

        if batch:
            p, i = await _flush_batch(conn, batch, skip_ingredients)
            total_products    += p
            total_ingredients += i

    except Exception as exc:
        error_msg = str(exc)
        print(f"\nERROR: {error_msg}", file=sys.stderr)

    finally:
        elapsed = time.monotonic() - start_time
        status  = "failed" if error_msg else "completed"
        await conn.execute(
            _UPDATE_SYNC_LOG_COMPLETE, sync_log_id, status,
            total_products, 0, error_msg,
        )
        await conn.close()
        print(
            f"\n{'='*60}\n"
            f"Import {status}.\n"
            f"  Records seen    : {records_seen:,}\n"
            f"  Products saved  : {total_products:,}\n"
            f"  Ingredient rows : {total_ingredients:,}\n"
            f"  Skipped         : {skipped:,}\n"
            f"  Elapsed         : {elapsed:.1f}s\n"
            f"{'='*60}"
        )
        if error_msg:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import openFDA OTC drug labels into the safescan database."
    )
    parser.add_argument(
        "--partitions", type=int, default=None, metavar="N",
        help="Process only the first N partition files (default: all).",
    )
    parser.add_argument(
        "--skip-ingredients", action="store_true",
        help="Skip product_ingredients rows (faster metadata-only import).",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run_import(
        max_partitions=args.partitions,
        skip_ingredients=args.skip_ingredients,
    ))


if __name__ == "__main__":
    main()
