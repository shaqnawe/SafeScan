"""
California Proposition 65 chemical list importer.

Reads the locally-downloaded Prop 65 CSV and enriches existing rows in the
`ingredients` table with Prop 65 concern tags. Never inserts new rows —
only updates rows matched by CAS number or ingredient name.

Trust hierarchy position: prop65 (rank 5) — below cosing/efsa/iarc, above obf/off.
Appends to `concerns` and fills `cas_number` if missing.
Does NOT overwrite `safety_level`, `eu_status`, or `score_penalty`.

Concern tags applied:
  - Type "cancer"                        → prop65_carcinogen
  - Type "developmental"                 → prop65_developmental_toxin
  - Type "female" / "male" / "male female" → prop65_reproductive_toxin

A single chemical may receive multiple tags (e.g. both prop65_carcinogen and
prop65_developmental_toxin) if its Prop 65 entry lists multiple toxicity types.

Source file: backend/db/seed/data/prop65_list_YYYY-MM-DD.csv
  From: https://oehha.ca.gov/proposition-65/proposition-65-list
  Header row is at line 11 (0-indexed); lines 0-10 are OEHHA metadata.

Usage:
    python -m db.importers.prop65_importer
    python -m db.importers.prop65_importer --dry-run
    python -m db.importers.prop65_importer --file /path/to/prop65_list.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import time
from pathlib import Path
from typing import Optional

import asyncpg
from dotenv import load_dotenv

from db.importers._match_helpers import build_update_sql, find_latest_csv, match_and_update

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

DATABASE_URL = os.environ.get("DATABASE_URL")

_SEED_DIR = Path(__file__).parent.parent / "seed" / "data"

BATCH_SIZE = 1000

# Number of metadata lines before the real column header row in the OEHHA CSV.
_HEADER_SKIP = 11

# Map lowercase Prop 65 toxicity tokens → concern tag(s)
_TOX_TAG: dict[str, str] = {
    "cancer":        "prop65_carcinogen",
    "developmental": "prop65_developmental_toxin",
    "female":        "prop65_reproductive_toxin",
    "male":          "prop65_reproductive_toxin",
    "reproductive":  "prop65_reproductive_toxin",
}

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_INSERT_SYNC_LOG = """
INSERT INTO sync_log (source, started_at, status)
VALUES ('prop65', NOW(), 'running')
RETURNING id
"""

_UPDATE_SYNC_LOG_PROGRESS = """
UPDATE sync_log SET records_updated = $2 WHERE id = $1
"""

_UPDATE_SYNC_LOG_COMPLETE = """
UPDATE sync_log
SET completed_at = NOW(), status = $2,
    records_added = $3, records_updated = $4, error = $5
WHERE id = $1
"""

# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _tox_to_tags(tox_field: str) -> list[str]:
    """
    Convert the raw "Type of Toxicity" field to a deduplicated list of
    concern tags.

    Examples:
      "cancer"                  → ["prop65_carcinogen"]
      "developmental, female, male" → ["prop65_developmental_toxin",
                                        "prop65_reproductive_toxin"]
      ""                        → []
    """
    tags: list[str] = []
    seen: set[str] = set()
    for token in tox_field.lower().split(","):
        token = token.strip()
        tag = _TOX_TAG.get(token)
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def _load_csv(path: Path) -> list[dict]:
    """
    Load and normalise the Prop 65 CSV.

    Skips the OEHHA metadata header, empty rows, and rows with no chemical
    name. Returns dicts with keys: cas_number, chemical, tags (list[str]).
    """
    entries: list[dict] = []

    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        # Skip metadata lines; line _HEADER_SKIP is the real column header.
        for _ in range(_HEADER_SKIP):
            next(f)

        reader = csv.DictReader(f)
        for row in reader:
            chemical = row.get("Chemical", "").strip()
            if not chemical:
                continue

            tox_raw = row.get("Type of Toxicity", "").strip()
            tags = _tox_to_tags(tox_raw)
            if not tags:
                continue  # empty or unrecognised toxicity type — skip

            cas = row.get("CAS No.", "").strip() or None

            # One entry per (chemical, tag) pair so match_and_update is called
            # once per tag, allowing each to be independently tracked.
            for tag in tags:
                entries.append({
                    "cas_number": cas,
                    "chemical":   chemical,
                    "tag":        tag,
                })

    return entries


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

async def _run_import(csv_path: Path, dry_run: bool) -> None:
    if DATABASE_URL is None:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Prop 65 importer — source: {csv_path.name}")
    if dry_run:
        print("DRY RUN — no database writes.")

    entries = _load_csv(csv_path)
    print(f"Loaded {len(entries):,} Prop 65 (chemical, tag) pairs.")

    # Summary by tag
    from collections import Counter
    tag_counts = Counter(e["tag"] for e in entries)
    for tag, cnt in sorted(tag_counts.items()):
        print(f"  {tag}: {cnt:,}")

    cas_sql, name_sql = build_update_sql("prop65")

    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    sync_log_id: int = await conn.fetchval(_INSERT_SYNC_LOG)
    print(f"sync_log id={sync_log_id}\n")

    total_cas  = 0
    total_name = 0
    all_unmatched: list[dict] = []
    error_msg: Optional[str] = None
    start_time = time.monotonic()

    try:
        for batch_start in range(0, len(entries), BATCH_SIZE):
            batch = entries[batch_start : batch_start + BATCH_SIZE]
            batch_cas = batch_name = 0
            batch_unmatched: list[dict] = []

            async with conn.transaction():
                if not dry_run:
                    for entry in batch:
                        result = await match_and_update(
                            conn,
                            cas_number=entry["cas_number"],
                            agent_name=entry["chemical"],
                            concern_tag=entry["tag"],
                            cas_sql=cas_sql,
                            name_sql=name_sql,
                        )
                        if result == "cas":
                            batch_cas += 1
                        elif result == "name":
                            batch_name += 1
                        else:
                            batch_unmatched.append(entry)

            total_cas  += batch_cas
            total_name += batch_name
            all_unmatched.extend(batch_unmatched)

            processed = batch_start + len(batch)
            await conn.execute(
                _UPDATE_SYNC_LOG_PROGRESS,
                sync_log_id,
                total_cas + total_name,
            )
            print(
                f"  [{processed:,}/{len(entries):,}] "
                f"CAS={total_cas} name={total_name} unmatched={len(all_unmatched)}"
            )

    except Exception as exc:
        error_msg = str(exc)
        print(f"\nERROR: {error_msg}", file=sys.stderr)

    finally:
        elapsed = time.monotonic() - start_time
        total_matched = total_cas + total_name
        status = "failed" if error_msg else "completed"

        await conn.execute(
            _UPDATE_SYNC_LOG_COMPLETE,
            sync_log_id, status,
            0,
            total_matched,
            error_msg,
        )
        await conn.close()

        print(
            f"\n{'='*60}\n"
            f"Prop 65 import {status}.\n"
            f"  Total (chemical, tag) pairs processed : {len(entries):,}\n"
            f"  Matched by CAS number                 : {total_cas:,}\n"
            f"  Matched by name                       : {total_name:,}\n"
            f"  Total matched                         : {total_matched:,}\n"
            f"  Unmatched                             : {len(all_unmatched):,}\n"
            f"  Elapsed                               : {elapsed:.1f}s\n"
            f"{'='*60}"
        )

        if all_unmatched:
            # Deduplicate for display (same chemical may appear for multiple tags)
            seen: set[str] = set()
            sample: list[dict] = []
            for u in all_unmatched:
                key = u["chemical"]
                if key not in seen:
                    seen.add(key)
                    sample.append(u)
                if len(sample) >= 10:
                    break
            print(f"\nSample unmatched chemicals (up to 10 of {len(seen)} unique):")
            for u in sample:
                print(
                    f"  CAS={str(u['cas_number'] or '—'):>15}  "
                    f"{u['chemical'][:55]}"
                )

        if error_msg:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich ingredients table with California Prop 65 concern tags."
    )
    parser.add_argument(
        "--file", metavar="PATH", default=None,
        help="Path to prop65_list_*.csv. Defaults to latest file in db/seed/data/.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and count rows but make no database writes.",
    )
    args = parser.parse_args()

    csv_path: Optional[Path]
    if args.file:
        csv_path = Path(args.file)
    else:
        csv_path = find_latest_csv(_SEED_DIR, "prop65_list")
        if csv_path is None:
            print(
                f"ERROR: No prop65_list_*.csv found in {_SEED_DIR}. "
                "Pass --file or re-run the download step.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not csv_path.exists():
        print(f"ERROR: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_run_import(csv_path, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
