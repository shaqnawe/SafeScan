"""
After-test diff helper for image-agent ingredient OCR.

Compares ingredients extracted from a product image (the image agent's output)
against a ground-truth list (typically transcribed by hand from the same label,
or copied from a manufacturer site). Surfaces:
  - matches          (exact, after normalization)
  - misses           (in truth, absent from extracted)  -> OCR didn't see
  - extras           (in extracted, absent from truth)  -> hallucination / fusion
  - fuzzy matches    (>=0.80 similarity)                -> likely OCR typos

Plus recall and precision percentages so you can track image-agent quality
over time across multiple test scans.

Usage:
  cd backend

  # Pull extracted from a DB submission, compare against a truth file:
  python -m scratch.diff_extraction --submission-id 8 --truth-file truth.txt

  # Most recent submission for a barcode:
  python -m scratch.diff_extraction --submission-barcode 8809838658313 --truth-file truth.txt

  # Truth on stdin (handy if pasting from a manufacturer site):
  python -m scratch.diff_extraction --submission-id 8 --truth-stdin

  # Pure text vs text, no DB:
  python -m scratch.diff_extraction \\
      --extracted-text "Water, Glycerin, Sodium Chloride" \\
      --truth-text "Water, Glycerin, Salicylic Acid"

Truth/extracted file format: ingredients separated by commas OR one per line.
Lines starting with '#' are ignored. Mixing both works (commas within a line
are split too).
"""

import argparse
import asyncio
import difflib
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


_INCI_SPLIT = re.compile(r",\s+")
_NUMERIC_COMMA_SPACE = re.compile(r"(\d),\s+(\d)")


def split_list(text: str) -> list[str]:
    """Parse a comma- or newline-separated ingredient blob into clean items.

    INCI convention: ingredients are separated by ', ' (comma+space). Chemical
    names that contain commas (e.g. '1,2-Hexanediol') use a bare comma with no
    space, so splitting on ', ' preserves them intact. Some sources slip an
    errant space into chemical names ('1, 2-Hexanediol') — we glue those back
    together before splitting so they don't fragment.
    """
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = _NUMERIC_COMMA_SPACE.sub(r"\1,\2", line)
        for piece in _INCI_SPLIT.split(line):
            piece = piece.strip().rstrip(",")
            if piece:
                items.append(piece)
    return items


_PUNCT_TRIM = re.compile(r"[\s\.;:]+$")
_MULTI_SPACE = re.compile(r"\s+")


def normalize(ing: str) -> str:
    """Normalize for matching. INCI-aware: handles whitespace, paren spacing,
    and the '1, 2-Hexanediol' style intra-number spacing OCR commonly varies on."""
    s = ing.lower().strip()
    s = _PUNCT_TRIM.sub("", s)
    # Collapse "1, 2" -> "1,2" so "1, 2-Hexanediol" matches "1,2-Hexanediol"
    s = re.sub(r"(\d),\s+(\d)", r"\1,\2", s)
    # Normalize parenthetical spacing: "Water(Aqua)" / "Water (Aqua)" -> "water (aqua)"
    s = re.sub(r"\s*\(\s*", " (", s)
    s = re.sub(r"\s*\)\s*", ")", s)
    s = _MULTI_SPACE.sub(" ", s)
    return s.strip()


async def fetch_extracted_from_db(
    submission_id: int | None, barcode: str | None
) -> tuple[list[str], str]:
    """Return (ingredient_names, label) for the requested submission."""
    from db.connection import get_conn

    async with get_conn() as conn:
        if submission_id is not None:
            row = await conn.fetchrow(
                "SELECT id, barcode, status, extracted_data "
                "FROM user_submissions WHERE id = $1",
                submission_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT id, barcode, status, extracted_data FROM user_submissions "
                "WHERE barcode = $1 ORDER BY id DESC LIMIT 1",
                barcode,
            )
    if row is None:
        raise SystemExit("No submission found.")
    raw = row["extracted_data"]
    if raw is None:
        raise SystemExit(
            f"Submission id={row['id']} has no extracted_data "
            f"(status={row['status']}; ingredient extraction probably failed)."
        )
    data = json.loads(raw) if isinstance(raw, str) else raw
    names = [i["name"] for i in data.get("ingredients", []) if i.get("name")]
    label = f"submission id={row['id']} barcode={row['barcode']} status={row['status']}"
    return names, label


def read_text(path: str | None, use_stdin: bool, inline: str | None) -> str:
    if inline:
        return inline
    if use_stdin:
        return sys.stdin.read()
    if path:
        return Path(path).read_text()
    return ""


def diff(extracted: list[str], truth: list[str], fuzzy_cutoff: float = 0.80) -> dict:
    """Bucket each ingredient as matched / missed / extra / fuzzy."""
    e_norm_to_orig: dict[str, str] = {}
    for x in extracted:
        e_norm_to_orig.setdefault(normalize(x), x)
    t_norm_to_orig: dict[str, str] = {}
    for x in truth:
        t_norm_to_orig.setdefault(normalize(x), x)

    e_set = set(e_norm_to_orig)
    t_set = set(t_norm_to_orig)
    matched_keys = e_set & t_set
    missed_keys = t_set - e_set
    extra_keys = e_set - t_set

    # For each miss, see if there's a fuzzy hit in extras — common OCR cases:
    # typo, fused with another ingredient, or split mid-name.
    fuzzy_pairs: list[tuple[str, str]] = []
    consumed_extras: set[str] = set()
    for m in sorted(missed_keys):
        candidates = [e for e in extra_keys if e not in consumed_extras]
        match = difflib.get_close_matches(m, candidates, n=1, cutoff=fuzzy_cutoff)
        if match:
            fuzzy_pairs.append((t_norm_to_orig[m], e_norm_to_orig[match[0]]))
            consumed_extras.add(match[0])

    missed_final = [
        t_norm_to_orig[k] for k in sorted(missed_keys)
        if not any(t_norm_to_orig[k] == p[0] for p in fuzzy_pairs)
    ]
    extra_final = [
        e_norm_to_orig[k] for k in sorted(extra_keys)
        if k not in consumed_extras
    ]

    return {
        "extracted_total": len(extracted),
        "truth_total": len(truth),
        "matched": sorted(t_norm_to_orig[k] for k in matched_keys),
        "missed": sorted(missed_final, key=str.lower),
        "extra": sorted(extra_final, key=str.lower),
        "fuzzy": sorted(fuzzy_pairs, key=lambda x: x[0].lower()),
    }


def render(d: dict) -> None:
    e_total = d["extracted_total"]
    t_total = d["truth_total"]
    matched = len(d["matched"])
    missed = len(d["missed"])
    extra = len(d["extra"])
    fuzzy = len(d["fuzzy"])

    # Count fuzzy as a match for recall/precision (they're real ingredients
    # the model captured, just imperfectly transcribed)
    captured = matched + fuzzy
    recall = captured / max(t_total, 1)
    precision = captured / max(e_total, 1)

    print("\n=== EXTRACTION DIFF ===")
    print(f"  extracted: {e_total}")
    print(f"  truth:     {t_total}")
    print()
    print(f"  matched (exact): {matched}")
    print(f"  matched (fuzzy): {fuzzy}")
    print(f"  missed (OCR didn't see):    {missed}")
    print(f"  extra  (in extracted only): {extra}")
    print()
    print(f"  recall:    {recall:>5.1%}   (captured / truth)")
    print(f"  precision: {precision:>5.1%}   (captured / extracted)")

    if d["missed"]:
        print(f"\n--- MISSED ({missed}) — OCR did not see these ---")
        for x in d["missed"]:
            print(f"  - {x}")

    if d["extra"]:
        print(f"\n--- EXTRA ({extra}) — OCR added these (hallucination or fusion?) ---")
        for x in d["extra"]:
            print(f"  + {x}")

    if d["fuzzy"]:
        print(f"\n--- FUZZY ({fuzzy}) — likely OCR typos ---")
        print("    (truth  ≈  extracted)")
        for t, e in d["fuzzy"]:
            print(f"  {t!r}\n    ≈  {e!r}")


async def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_argument_group("extracted (provide one)")
    src.add_argument("--submission-id", type=int, help="DB row id")
    src.add_argument("--submission-barcode", help="most recent submission for this barcode")
    src.add_argument("--extracted-text", help="comma/newline-separated ingredients")
    src.add_argument("--extracted-file", help="file with extracted ingredients")

    tru = p.add_argument_group("truth (provide one)")
    tru.add_argument("--truth-text", help="comma/newline-separated ingredients")
    tru.add_argument("--truth-file", help="file with ground-truth ingredients")
    tru.add_argument("--truth-stdin", action="store_true", help="read truth from stdin")

    p.add_argument(
        "--fuzzy-cutoff", type=float, default=0.80,
        help="similarity threshold for fuzzy matches (0..1, default 0.80)",
    )

    args = p.parse_args()

    # Resolve extracted
    if args.submission_id is not None or args.submission_barcode:
        extracted, src_label = await fetch_extracted_from_db(
            args.submission_id, args.submission_barcode
        )
    elif args.extracted_text or args.extracted_file:
        text = read_text(args.extracted_file, False, args.extracted_text)
        extracted = split_list(text)
        src_label = args.extracted_file or "inline --extracted-text"
    else:
        p.error("Need one of --submission-id / --submission-barcode / "
                "--extracted-text / --extracted-file")

    # Resolve truth
    if args.truth_text or args.truth_file or args.truth_stdin:
        text = read_text(args.truth_file, args.truth_stdin, args.truth_text)
        truth = split_list(text)
        truth_label = (
            "stdin" if args.truth_stdin
            else (args.truth_file or "inline --truth-text")
        )
    else:
        p.error("Need one of --truth-text / --truth-file / --truth-stdin")

    print(f"Extracted from: {src_label}  ({len(extracted)} items)")
    print(f"Truth from:     {truth_label}  ({len(truth)} items)")

    d = diff(extracted, truth, fuzzy_cutoff=args.fuzzy_cutoff)
    render(d)


if __name__ == "__main__":
    asyncio.run(main())
