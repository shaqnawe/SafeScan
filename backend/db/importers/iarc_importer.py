"""
IARC Monographs carcinogen classification importer.

Reads the locally-downloaded IARC agents CSV and enriches existing rows in the
`ingredients` table with IARC group concern tags. Never inserts new rows —
only updates rows that can be matched by CAS number or ingredient name.

Trust hierarchy position: iarc (rank 6) — below cosing/efsa, above obf/off.
Appends to `concerns` and fills `cas_number` if missing.
Does NOT overwrite `safety_level`, `eu_status`, or `score_penalty`.

Source file: backend/db/seed/data/iarc_agents_YYYY-MM-DD.csv
  Columns: cas_number, agent, iarc_group, year
  Produced by parsing the IARC Monographs PDF (Volumes 1–123).

Usage:
    python -m db.importers.iarc_importer
    python -m db.importers.iarc_importer --dry-run
    python -m db.importers.iarc_importer --file /path/to/iarc_agents.csv
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

# IARC Group 3 = "unclassifiable as to carcinogenicity" — no health signal.
_SKIP_GROUPS = {"3"}

_GROUP_TAG: dict[str, str] = {
    "1":  "iarc_group_1",
    "2A": "iarc_group_2a",
    "2B": "iarc_group_2b",
}

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_INSERT_SYNC_LOG = """
INSERT INTO sync_log (source, started_at, status)
VALUES ('iarc', NOW(), 'running')
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

def _load_csv(path: Path) -> list[dict]:
    """
    Load and normalise the IARC agents CSV.

    Returns dicts with keys: cas_number, agent, iarc_group, tag.
    Skips Group 3 (unclassifiable) and rows with no agent name.
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            group = row.get("iarc_group", "").strip()
            if group in _SKIP_GROUPS:
                continue
            tag = _GROUP_TAG.get(group)
            if tag is None:
                continue
            agent = row.get("agent", "").strip()
            if not agent:
                continue
            cas = row.get("cas_number", "").strip() or None
            rows.append({"cas_number": cas, "agent": agent, "iarc_group": group, "tag": tag})
    return rows


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

async def _run_import(csv_path: Path, dry_run: bool) -> None:
    if DATABASE_URL is None:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    print(f"IARC importer — source: {csv_path.name}")
    if dry_run:
        print("DRY RUN — no database writes.")

    rows = _load_csv(csv_path)
    print(f"Loaded {len(rows):,} IARC entries (Group 3 excluded).")
    for g, tag in sorted(_GROUP_TAG.items()):
        c = sum(1 for r in rows if r["iarc_group"] == g)
        print(f"  Group {g} ({tag}): {c:,}")

    cas_sql, name_sql = build_update_sql("iarc")

    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    sync_log_id: int = await conn.fetchval(_INSERT_SYNC_LOG)
    print(f"sync_log id={sync_log_id}\n")

    total_cas  = 0
    total_name = 0
    all_unmatched: list[dict] = []
    error_msg: Optional[str] = None
    start_time = time.monotonic()

    try:
        for batch_start in range(0, len(rows), BATCH_SIZE):
            batch = rows[batch_start : batch_start + BATCH_SIZE]
            batch_cas = batch_name = 0
            batch_unmatched: list[dict] = []

            async with conn.transaction():
                if not dry_run:
                    for entry in batch:
                        result = await match_and_update(
                            conn,
                            cas_number=entry["cas_number"],
                            agent_name=entry["agent"],
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
                f"  [{processed:,}/{len(rows):,}] "
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
            0,             # records_added  — never inserts
            total_matched,
            error_msg,
        )
        await conn.close()

        print(
            f"\n{'='*60}\n"
            f"IARC import {status}.\n"
            f"  Total entries processed : {len(rows):,}\n"
            f"  Matched by CAS number   : {total_cas:,}\n"
            f"  Matched by name         : {total_name:,}\n"
            f"  Total matched           : {total_matched:,}\n"
            f"  Unmatched               : {len(all_unmatched):,}\n"
            f"  Elapsed                 : {elapsed:.1f}s\n"
            f"{'='*60}"
        )

        if all_unmatched:
            print(f"\nSample unmatched entries (up to 10 of {len(all_unmatched)}):")
            for u in all_unmatched[:10]:
                print(
                    f"  Group {u['iarc_group']:>2}  "
                    f"CAS={str(u['cas_number'] or '—'):>15}  "
                    f"{u['agent']}"
                )

        if error_msg:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich ingredients table with IARC carcinogen group tags."
    )
    parser.add_argument(
        "--file", metavar="PATH", default=None,
        help="Path to iarc_agents_*.csv. Defaults to latest file in db/seed/data/.",
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
        csv_path = find_latest_csv(_SEED_DIR, "iarc_agents")
        if csv_path is None:
            print(
                f"ERROR: No iarc_agents_*.csv found in {_SEED_DIR}. "
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
