"""
DailyMed prescription drug importer.

Imports HUMAN PRESCRIPTION DRUG records from the openFDA drug/label API
(which mirrors the NIH DailyMed SPL dataset). The existing openfda_importer.py
already handles OTC drugs; this importer handles Rx-only products.

Barcode strategy (priority order):
  1. openfda.upc — 12/13-digit UPC barcode on packaging (preferred).
  2. openfda.package_ndc — normalized to NDC-11 (11 digits, 5-4-2 zero-padded).
     Code 128 barcodes on Rx boxes encode the NDC-11 directly, so phones return
     an 11-digit string.  Stored as-is so scanner.py can look it up.

Source tag: 'dailymed'.  Ingredients: active then inactive, same as openfda_importer.

Usage:
    python -m db.importers.dailymed_importer
    python -m db.importers.dailymed_importer --partitions 2
    python -m db.importers.dailymed_importer --skip-ingredients
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

# Only import Rx (Human Prescription Drug); OTC is handled by openfda_importer.
RX_MARKER  = "HUMAN PRESCRIPTION DRUG"

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_UPSERT_PRODUCT = """
INSERT INTO products (
    barcode, name, brand, product_type, image_url,
    nutriscore, nova_group, categories, source, last_synced_at
)
VALUES ($1, $2, $3, 'drug', NULL, NULL, NULL, $4, 'dailymed', NOW())
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
VALUES ('dailymed', NOW(), 'running')
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


def _normalize_ndc(ndc: str) -> str | None:
    """
    Normalize an NDC string (any format) to 11-digit NDC-11 (5-4-2).

    openFDA package_ndc values are formatted as 'XXXXX-XXXX-XX' with dashes,
    though some appear as 4-4-2 or 5-3-2.  Zero-pad each dash-separated
    segment to its canonical width.

    Returns None for any format that cannot be safely resolved.
    """
    parts = ndc.strip().split('-')
    if len(parts) == 3:
        labeler, product, package = parts
        return labeler.zfill(5) + product.zfill(4) + package.zfill(2)
    digits = re.sub(r'\D', '', ndc)
    if len(digits) == 11:
        return digits
    return None


def _parse_ingredient_text(raw: str) -> list[str]:
    text = re.sub(
        r'^(active|inactive)\s+ingredients?\s*',
        '', raw, flags=re.IGNORECASE
    ).strip()
    if not text:
        return []
    parts = re.split(r'[,;]', text)
    tokens = []
    for part in parts:
        token = re.sub(
            r'\s+\d[\d.,]*\s*(mg|mcg|%|g|ml|iu|meq)\b.*',
            '', part, flags=re.IGNORECASE
        ).strip()
        if token and len(token) > 1:
            tokens.append(token)
    return tokens


def _extract_ingredients(record: dict) -> list[str]:
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
    print(f"Fetching manifest from {MANIFEST_URL} ...")
    resp = urlopen(MANIFEST_URL)
    manifest = json.loads(resp.read())
    partitions = manifest["results"]["drug"]["label"]["partitions"]
    urls = [p["file"] for p in partitions]
    print(f"  Found {len(urls)} drug/label partition(s).")
    return urls


def _download_partition(url: str) -> list[dict]:
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
    products_saved  = 0
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
    upc_barcodes      = 0
    ndc_barcodes      = 0
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

                # Only Rx prescription drugs (OTC handled by openfda_importer)
                product_types = openfda.get("product_type", [])
                if not any(RX_MARKER in pt for pt in product_types):
                    skipped += 1
                    continue

                brand_names   = openfda.get("brand_name", [])
                generic_names = openfda.get("generic_name", [])
                manufacturer  = openfda.get("manufacturer_name", [])
                purpose_raw   = record.get("purpose", [""])[0] if record.get("purpose") else ""

                name  = _first(brand_names) or _first(generic_names) or None
                brand = _first(manufacturer) or None

                purpose    = re.sub(r'\s+', ' ', purpose_raw).strip()[:80]
                categories = [purpose] if purpose else []

                ingredients = _extract_ingredients(record) if not skip_ingredients else []

                # --- Barcode resolution ---
                # Priority 1: UPC (same as OTC drugs — some Rx products have UPC)
                upcs = openfda.get("upc", [])
                for upc in upcs:
                    bc = upc.strip()
                    if not bc or len(bc) not in (12, 13):
                        continue
                    if len(bc) == 12:
                        bc = '0' + bc
                    batch.append({"barcode": bc, "name": name, "brand": brand,
                                  "categories": categories, "ingredients": ingredients})
                    upc_barcodes += 1

                if upcs:
                    if len(batch) >= BATCH_SIZE:
                        p, i = await _flush_batch(conn, batch, skip_ingredients)
                        total_products    += p
                        total_ingredients += i
                        batch.clear()
                    continue

                # Priority 2: NDC → NDC-11 (11-digit Code 128 barcode on Rx boxes)
                ndcs = openfda.get("package_ndc", [])
                for ndc_raw in ndcs:
                    ndc11 = _normalize_ndc(ndc_raw)
                    if not ndc11:
                        continue
                    batch.append({"barcode": ndc11, "name": name, "brand": brand,
                                  "categories": categories, "ingredients": ingredients})
                    ndc_barcodes += 1

                if not ndcs:
                    skipped += 1

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
            f"  Records seen       : {records_seen:,}\n"
            f"  Products saved     : {total_products:,}\n"
            f"  Ingredient rows    : {total_ingredients:,}\n"
            f"  Skipped            : {skipped:,}\n"
            f"  UPC barcodes       : {upc_barcodes:,}\n"
            f"  NDC-11 barcodes    : {ndc_barcodes:,}\n"
            f"  Elapsed            : {elapsed:.1f}s\n"
            f"{'='*60}"
        )
        if error_msg:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import DailyMed Rx drug labels into the safescan database."
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
