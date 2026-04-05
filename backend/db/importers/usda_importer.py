"""
USDA FoodData Central branded food importer.

Downloads the FoodData Central CSV zip and imports US branded food products
into the safescan products + product_ingredients tables.

Dataset: ~500K branded food products with GTIN/UPC barcodes and ingredient text.
Download page: https://fdc.nal.usda.gov/download-data/

Usage:
    # Download and import directly from USDA:
    python -m db.importers.usda_importer --url

    # Use a pre-downloaded zip:
    python -m db.importers.usda_importer --file /path/to/FoodData_Central_csv_2024-10-31.zip

    # Test run (first 20 000 products):
    python -m db.importers.usda_importer --url --limit 20000

    # Skip ingredient rows (faster, metadata only):
    python -m db.importers.usda_importer --url --skip-ingredients
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import io
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

# Latest USDA FoodData Central CSV release.
# Check https://fdc.nal.usda.gov/download-data/ for a newer zip if this 404s.
USDA_CSV_URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_csv_2024-10-31.zip"

BATCH_SIZE  = 500
LOG_INTERVAL = 10_000

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_UPSERT_PRODUCT = """
INSERT INTO products (
    barcode, name, brand, product_type, image_url,
    nutriscore, nova_group, categories, source, last_synced_at
)
VALUES ($1, $2, $3, 'food', NULL, NULL, NULL, $4, 'usda', NOW())
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
VALUES ('usda', NOW(), 'running')
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
# GTIN normalisation
# ---------------------------------------------------------------------------

def _to_ean13(raw: str) -> Optional[str]:
    """
    Normalise a GTIN of any length to a 13-digit EAN-13 string, or None.

    USDA stores GTINs as 14-digit strings (GTIN-14).  The leading digit is a
    packaging-level indicator; for retail items it is always 0, making the
    inner barcode a GTIN-13 (EAN-13).  We strip that one leading digit.

    GTIN-12 (UPC-A) is padded to 13 with a leading zero.
    GTIN-8  is left-padded to 13.
    Anything else (GTIN-14 with non-zero indicator) is dropped.
    """
    digits = re.sub(r'\D', '', raw)
    if not digits:
        return None
    length = len(digits)
    if length == 14:
        if digits[0] != '0':
            return None          # case/pallet GTIN — not a retail barcode
        return digits[1:]        # strip packaging indicator → 13 digits
    if length == 13:
        return digits
    if length == 12:
        return '0' + digits      # UPC-A → EAN-13
    if length == 8:
        return digits.zfill(13)  # EAN-8 → left-pad
    return None


# ---------------------------------------------------------------------------
# Ingredient text parser
# ---------------------------------------------------------------------------

def _parse_ingredients(raw: str) -> list[str]:
    """Split USDA ingredients text on commas/semicolons into token list."""
    if not raw.strip():
        return []
    parts = re.split(r'[,;]', raw)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Zip helpers
# ---------------------------------------------------------------------------

def _open_zip(file_path: Optional[str], use_url: bool) -> zipfile.ZipFile:
    if use_url:
        print(f"Downloading {USDA_CSV_URL} ...")
        print("(477 MB — this may take a few minutes)")
        resp = urlopen(USDA_CSV_URL)
        data = resp.read()
        return zipfile.ZipFile(io.BytesIO(data))
    else:
        print(f"Opening {file_path} ...")
        return zipfile.ZipFile(file_path)


def _find_csv(zf: zipfile.ZipFile, name: str) -> Optional[str]:
    """Return the zip entry whose filename (after the last '/') exactly matches `name`."""
    for entry in zf.namelist():
        if entry.split("/")[-1].lower() == name.lower():
            return entry
    return None


# ---------------------------------------------------------------------------
# DB batch flush
# ---------------------------------------------------------------------------

async def _flush_batch(
    conn: asyncpg.Connection,
    batch: list[dict],
    skip_ingredients: bool,
) -> tuple[int, int]:
    products_saved = 0
    ingredient_rows = 0

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

            if not skip_ingredients and p["ingredients_text"]:
                for pos, token in enumerate(_parse_ingredients(p["ingredients_text"]), 1):
                    if pos > 32767:
                        break
                    await conn.execute(_INSERT_INGREDIENT, product_id, token, pos)
                    ingredient_rows += 1

    return products_saved, ingredient_rows


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

async def _run_import(
    file_path: Optional[str],
    use_url: bool,
    limit: Optional[int],
    skip_ingredients: bool,
) -> None:
    if DATABASE_URL is None:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    sync_log_id: int = await conn.fetchval(_INSERT_SYNC_LOG)
    print(f"sync_log id={sync_log_id}")

    total_products  = 0
    total_ingredients = 0
    rows_seen       = 0
    skipped         = 0
    start_time      = time.monotonic()
    batch: list[dict] = []
    error_msg: Optional[str] = None

    try:
        zf = _open_zip(file_path, use_url)

        # Step 1: load food.csv into memory for fdc_id → description lookup
        food_csv_name = _find_csv(zf, "food.csv")
        if not food_csv_name:
            raise RuntimeError("food.csv not found in zip")

        print("Loading food.csv descriptions into memory...")
        fdc_desc: dict[str, str] = {}
        with zf.open(food_csv_name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
            for row in reader:
                fdc_id = row.get("fdc_id", "").strip()
                desc   = row.get("description", "").strip()
                if fdc_id and desc:
                    fdc_desc[fdc_id] = desc
        print(f"  Loaded {len(fdc_desc):,} food descriptions.")

        # Step 2: stream branded_food.csv
        branded_csv_name = _find_csv(zf, "branded_food.csv")
        if not branded_csv_name:
            raise RuntimeError("branded_food.csv not found in zip")

        print("Streaming branded_food.csv...")
        with zf.open(branded_csv_name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
            for row in reader:
                if limit is not None and rows_seen >= limit:
                    break
                rows_seen += 1

                # Filter to US market only
                country = row.get("market_country", "").strip()
                if country and country not in ("United States", "US", ""):
                    skipped += 1
                    continue

                # Skip discontinued products
                if row.get("discontinued_date", "").strip():
                    skipped += 1
                    continue

                gtin_raw = row.get("gtin_upc", "").strip()
                barcode = _to_ean13(gtin_raw)
                if not barcode:
                    skipped += 1
                    continue

                fdc_id = row.get("fdc_id", "").strip()
                name   = (
                    fdc_desc.get(fdc_id, "").strip()
                    or row.get("short_description", "").strip()
                    or None
                )
                brand = (
                    row.get("brand_owner", "").strip()
                    or row.get("brand_name", "").strip()
                    or None
                )
                category = row.get("branded_food_category", "").strip() or None
                ingredients_text = row.get("ingredients", "").strip()

                if not name and not ingredients_text:
                    skipped += 1
                    continue

                batch.append({
                    "barcode":          barcode,
                    "name":             name,
                    "brand":            brand,
                    "categories":       [category] if category else [],
                    "ingredients_text": ingredients_text,
                })

                if len(batch) >= BATCH_SIZE:
                    p, i = await _flush_batch(conn, batch, skip_ingredients)
                    total_products    += p
                    total_ingredients += i
                    batch.clear()

                if rows_seen % LOG_INTERVAL == 0:
                    elapsed = time.monotonic() - start_time
                    rate    = rows_seen / elapsed if elapsed else 0
                    print(
                        f"  [{rows_seen:,} rows | {total_products:,} products | "
                        f"{total_ingredients:,} ingredient rows | {skipped:,} skipped | {rate:.0f} rows/s]"
                    )
                    await conn.execute(_UPDATE_SYNC_LOG_PROGRESS, sync_log_id, total_products, 0)

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
            f"  Rows scanned    : {rows_seen:,}\n"
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
        description="Import USDA FoodData Central branded foods into the safescan database."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", metavar="PATH",
                        help="Path to a local FoodData_Central_csv_*.zip file.")
    source.add_argument("--url", action="store_true",
                        help=f"Download from {USDA_CSV_URL}")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Stop after N CSV rows (for testing).")
    parser.add_argument("--skip-ingredients", action="store_true",
                        help="Skip product_ingredients rows (faster metadata-only import).")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run_import(
        file_path=args.file,
        use_url=args.url,
        limit=args.limit,
        skip_ingredients=args.skip_ingredients,
    ))


if __name__ == "__main__":
    main()
