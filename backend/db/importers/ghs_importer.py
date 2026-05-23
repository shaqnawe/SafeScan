"""
GHS hazard classification importer — ECHA Annex VI CLP (primary source).

Enriches existing rows in the `ingredients` table with GHS-based concern tags.
Never inserts new rows — only updates rows matched by CAS number or name.

Primary data source — ECHA Annex VI to CLP Regulation (harmonised EU classifications):
  Download: https://echa.europa.eu/information-on-chemicals/annex-vi-to-clp
  Direct URL (ATP21, current):
    https://echa.europa.eu/documents/10162/17218/annex_vi_clp_table_atp21_en.xlsx/306afdb8-2ac0-8bb6-05eb-6842f6e5900c?t=1728453462885

  curl command:
    curl -L "<URL above>" \\
      -H "Referer: https://echa.europa.eu/information-on-chemicals/annex-vi-to-clp" \\
      -H "User-Agent: Mozilla/5.0" \\
      -o backend/db/seed/data/ghs_YYYY-MM-DD.xlsx

Coverage: ~4,400 EU-harmonised substances with legally binding classification.
Format: Excel (.xlsx) with columns including "CAS No" and "Hazard Statement Code(s)".

Also accepts CSV files in CompTox/generic format (see _detect_columns() for variants).

GHS hazard codes mapped to concern tags:
  H340 / H341 (mutagenicity)        → ghs_mutagen
  H350 / H350i (carcinogenicity)    → ghs_carcinogen_cat1
  H351         (suspected carcin.)  → ghs_carcinogen_cat2
  H360 / H360* (reproductive)       → ghs_reproductive_toxin
  H361 / H361* (susp. reproductive) → ghs_reproductive_toxin

Scoring impact (see scoring_rubric.md and local_analyzer.py):
  ghs_carcinogen_cat1    −25 pts
  ghs_carcinogen_cat2    −12 pts
  ghs_reproductive_toxin −15 pts
  ghs_mutagen            −12 pts

Usage:
    python -m db.importers.ghs_importer
    python -m db.importers.ghs_importer --dry-run
    python -m db.importers.ghs_importer --file /path/to/ghs.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import asyncpg
from dotenv import load_dotenv

from db.importers._match_helpers import build_update_sql, match_and_update

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

DATABASE_URL = os.environ.get("DATABASE_URL")

_SEED_DIR = Path(__file__).parent.parent / "seed" / "data"

BATCH_SIZE = 500

# GHS codes → concern tag. Base code (H350) matched after stripping suffixes.
_CODE_TAG: dict[str, str] = {
    "H340": "ghs_mutagen",
    "H341": "ghs_mutagen",
    "H350": "ghs_carcinogen_cat1",
    "H351": "ghs_carcinogen_cat2",
    "H360": "ghs_reproductive_toxin",
    "H361": "ghs_reproductive_toxin",
}


def _base_code(raw: str) -> str:
    """Strip suffixes/variants: 'H350i' → 'H350', 'H360Df' → 'H360'."""
    m = re.match(r'(H\d{3})', raw.strip(), re.IGNORECASE)
    return m.group(1).upper() if m else raw.strip().upper()


def _codes_to_tags(cell: str) -> list[str]:
    """
    Parse a cell that may contain one or more H-codes and return
    the unique concern tags that apply.

    Handles ECHA format ('H350i H360D H341'), CSV format ('H350;H351'),
    and mixed separators.
    """
    tags: list[str] = []
    seen: set[str] = set()
    for part in re.split(r'[\s,;]+', cell):
        tag = _CODE_TAG.get(_base_code(part))
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_INSERT_SYNC_LOG = """
INSERT INTO sync_log (source, started_at, status)
VALUES ('ghs', NOW(), 'running')
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
# Column detection
# ---------------------------------------------------------------------------

# ECHA Annex VI column names first, then CompTox/generic variants.
_CAS_COLS  = ("cas no", "cas no.", "casrn", "cas_number", "cas number", "cas")
_NAME_COLS = ("international chemical identification", "preferred_name",
              "chem_name", "chemical_name", "preferred name", "name")
_CODE_COLS = ("hazard statement code(s)", "hazard statement codes",
              "hazard_code", "ghs_hazard_code", "h_code", "ghscode",
              "hazard statement code", "hazardcode")


def _normalise_header(h: str) -> str:
    return h.strip().lower()


def _detect_columns(headers: list[str]) -> dict[str, str]:
    """Map logical roles to actual column names (case-insensitive)."""
    lower = {_normalise_header(h): h for h in headers}
    result: dict[str, str] = {}
    for role, candidates in (
        ("cas",  _CAS_COLS),
        ("name", _NAME_COLS),
        ("code", _CODE_COLS),
    ):
        for c in candidates:
            if c in lower:
                result[role] = lower[c]
                break
    return result


# ---------------------------------------------------------------------------
# File readers — returns list of (cas, name, [tags])
# ---------------------------------------------------------------------------

def _read_xlsx(path: Path) -> list[tuple[Optional[str], str, list[str]]]:
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl is required for .xlsx files. Run: pip install openpyxl",
              file=sys.stderr)
        sys.exit(1)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    def _cell(v: object) -> str:
        return str(v).strip() if v is not None else ""

    # ECHA files start with a disclaimer block, then a two-row header:
    #   Row N:   section names (Classification, Labelling, …) — merged cells blank
    #   Row N+1: sub-column names (Hazard Statement Code(s), …)
    # Strategy: scan rows looking for one that contains a recognisable column name
    # (e.g. "CAS No" or "International Chemical Identification"), then merge it
    # with the next row to handle the two-row header.
    all_rows = list(ws.iter_rows(values_only=True))

    header_row_idx: int | None = None
    for idx, row in enumerate(all_rows):
        if row is None:
            continue
        cells = [_cell(c).lower() for c in row]
        if any(c in _CAS_COLS or c in _NAME_COLS or c in _CODE_COLS for c in cells):
            header_row_idx = idx
            break

    if header_row_idx is None:
        print(
            "ERROR: Could not locate a header row containing any known column name.\n"
            f"  Scanned {len(all_rows)} rows.\n"
            f"  Looking for CAS  : {_CAS_COLS}\n"
            f"  Looking for Name : {_NAME_COLS}\n"
            f"  Looking for Code : {_CODE_COLS}",
            file=sys.stderr,
        )
        wb.close()
        sys.exit(1)

    row1 = all_rows[header_row_idx]
    row2 = all_rows[header_row_idx + 1] if header_row_idx + 1 < len(all_rows) else None

    r1 = [_cell(c) for c in row1]
    r2 = [_cell(c) for c in row2] if row2 else [""] * len(r1)
    while len(r2) < len(r1):
        r2.append("")

    # Prefer sub-header (row 2) when present; fall back to section header (row 1)
    headers = [sub if sub else top for top, sub in zip(r1, r2)]
    cols_detected = _detect_columns(headers)

    # If merging didn't yield all three roles, try row 1 alone (single-row header case).
    if not all(r in cols_detected for r in ("cas", "name", "code")):
        single = _detect_columns(r1)
        if all(r in single for r in ("cas", "name", "code")):
            headers = r1
            cols_detected = single
            # Re-read assumes data starts immediately after row1
            data_start_idx = header_row_idx + 1
        else:
            print(
                f"ERROR: Could not find all required columns.\n"
                f"  Header row {header_row_idx + 1}: {r1}\n"
                f"  Sub-header row {header_row_idx + 2}: {r2}\n"
                f"  Merged headers: {headers}\n"
                f"  Detected: {cols_detected}",
                file=sys.stderr,
            )
            wb.close()
            sys.exit(1)
    else:
        # Two-row header — data starts after row 2
        data_start_idx = header_row_idx + 2

    cols = cols_detected
    print(f"Column mapping: {cols}  (header at row {header_row_idx + 1})")

    # Use first occurrence — for ECHA files this picks the Classification
    # Hazard Statement Code(s) column before the Labelling one.
    cas_idx  = headers.index(cols["cas"])
    name_idx = headers.index(cols["name"])
    code_idx = headers.index(cols["code"])

    results: list[tuple[Optional[str], str, list[str]]] = []
    max_idx = max(cas_idx, name_idx, code_idx)
    for row in all_rows[data_start_idx:]:
        if row is None or len(row) <= max_idx:
            continue
        cas_val  = _cell(row[cas_idx])
        name_val = _cell(row[name_idx])
        code_val = _cell(row[code_idx])

        if not name_val or not code_val:
            continue

        tags = _codes_to_tags(code_val)
        if not tags:
            continue

        cas = cas_val if cas_val and cas_val.lower() not in ("none", "-", "") else None
        results.append((cas, name_val, tags))

    wb.close()
    return results


def _read_csv(path: Path) -> list[tuple[Optional[str], str, list[str]]]:
    results: list[tuple[Optional[str], str, list[str]]] = []
    unknown_codes: set[str] = set()

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("ERROR: CSV has no headers.", file=sys.stderr)
            sys.exit(1)

        cols = _detect_columns(list(reader.fieldnames))
        missing = [r for r in ("cas", "name", "code") if r not in cols]
        if missing:
            print(
                f"ERROR: Could not find columns for: {missing}.\n"
                f"  Headers: {list(reader.fieldnames)}",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Column mapping: {cols}")

        for row in reader:
            code_val = row.get(cols["code"], "").strip()
            name_val = row.get(cols["name"], "").strip()
            if not code_val or not name_val:
                continue

            tags = _codes_to_tags(code_val)
            if not tags:
                # Track unrecognised codes for reporting
                for part in re.split(r'[\s,;]+', code_val):
                    b = _base_code(part)
                    if b.startswith("H") and len(b) >= 4:
                        unknown_codes.add(b)
                continue

            cas_raw = row.get(cols["cas"], "").strip()
            cas = cas_raw if cas_raw and cas_raw.lower() not in ("none", "-", "") else None
            results.append((cas, name_val, tags))

    if unknown_codes:
        print(f"  Skipped {len(unknown_codes)} unrecognised GHS codes: {sorted(unknown_codes)[:10]}")

    return results


def _load_file(path: Path) -> list[tuple[Optional[str], str, list[str]]]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return _read_xlsx(path)
    return _read_csv(path)


def _find_latest(seed_dir: Path) -> Optional[Path]:
    """Return the most recently dated ghs_*.xlsx or ghs_*.csv in seed_dir."""
    candidates = sorted(
        list(seed_dir.glob("ghs_*.xlsx")) + list(seed_dir.glob("ghs_*.csv")),
        reverse=True,
    )
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

async def _run_import(path: Path, dry_run: bool) -> None:
    if DATABASE_URL is None:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    print(f"GHS importer — source: {path.name}")
    if dry_run:
        print("DRY RUN — no database writes.")

    raw_rows = _load_file(path)

    # Expand multi-tag rows into one entry per tag
    entries: list[dict] = []
    for cas, name, tags in raw_rows:
        for tag in tags:
            entries.append({"cas_number": cas, "name": name, "tag": tag})

    print(f"Loaded {len(raw_rows):,} substance rows → {len(entries):,} tag entries.")

    tag_counts: dict[str, int] = {}
    for e in entries:
        tag_counts[e["tag"]] = tag_counts.get(e["tag"], 0) + 1
    for tag, count in sorted(tag_counts.items()):
        print(f"  {tag}: {count:,}")

    cas_sql, name_sql = build_update_sql("ghs")

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
            batch = entries[batch_start: batch_start + BATCH_SIZE]
            batch_cas = batch_name = 0
            batch_unmatched: list[dict] = []

            async with conn.transaction():
                if not dry_run:
                    for entry in batch:
                        result = await match_and_update(
                            conn,
                            cas_number=entry["cas_number"],
                            agent_name=entry["name"],
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
            await conn.execute(_UPDATE_SYNC_LOG_PROGRESS, sync_log_id, total_cas + total_name)
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
            sync_log_id, status, 0, total_matched, error_msg,
        )
        await conn.close()

        print(
            f"\n{'='*60}\n"
            f"GHS import {status}.\n"
            f"  Substance rows loaded   : {len(raw_rows):,}\n"
            f"  Tag entries processed   : {len(entries):,}\n"
            f"  Matched by CAS number   : {total_cas:,}\n"
            f"  Matched by name         : {total_name:,}\n"
            f"  Total matched           : {total_matched:,}\n"
            f"  Unmatched               : {len(all_unmatched):,}\n"
            f"  Elapsed                 : {elapsed:.1f}s\n"
            f"{'='*60}"
        )

        if all_unmatched:
            print(f"\nSample unmatched (up to 10 of {len(all_unmatched)}):")
            for u in all_unmatched[:10]:
                print(f"  {u['tag']:30}  CAS={str(u['cas_number'] or '—'):>15}  {u['name']}")

        if error_msg:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich ingredients table with ECHA CLP / GHS hazard tags."
    )
    parser.add_argument(
        "--file", metavar="PATH", default=None,
        help="Path to ghs_*.xlsx or ghs_*.csv. Defaults to latest in db/seed/data/.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and count rows but make no database writes.",
    )
    args = parser.parse_args()

    if args.file:
        ghs_path = Path(args.file)
    else:
        ghs_path = _find_latest(_SEED_DIR)
        if ghs_path is None:
            print(
                f"ERROR: No ghs_*.xlsx or ghs_*.csv found in {_SEED_DIR}.\n\n"
                "Download the ECHA Annex VI CLP table:\n"
                "  curl -L 'https://echa.europa.eu/documents/10162/17218/"
                "annex_vi_clp_table_atp21_en.xlsx/306afdb8-2ac0-8bb6-05eb-6842f6e5900c"
                "?t=1728453462885' \\\n"
                "    -H 'Referer: https://echa.europa.eu/information-on-chemicals/annex-vi-to-clp' \\\n"
                "    -H 'User-Agent: Mozilla/5.0' \\\n"
                "    -o backend/db/seed/data/ghs_2026-05-23.xlsx",
                file=sys.stderr,
            )
            sys.exit(1)

    if not ghs_path.exists():
        print(f"ERROR: File not found: {ghs_path}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_run_import(ghs_path, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
