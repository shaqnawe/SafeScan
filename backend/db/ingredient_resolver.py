"""
Ingredient resolution pipeline.

Resolves raw ingredient label text to canonical safety data through a
four-step cascade:

  1. Batch exact name + alias + E-number match  (single DB round-trip)
  2. Full-text search via GIN index             (per still-unresolved name)
  3. Claude classification                      (capped at CLAUDE_CAP/scan)
  4. Write-back                                 (new results persisted for
                                                 future lookups)

Public API
----------
  resolved = await resolve_ingredients(raw_names)
  # -> dict[raw_name, ResolvedIngredient]

Each value is a dict with keys:
  canonical_name, safety_level, score_penalty, concerns, e_number, eu_status
"""

from __future__ import annotations

import re
from typing import Any

import anthropic
from pydantic import BaseModel
from typing import Literal

from db.connection import get_conn

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLAUDE_CAP = 10          # max ingredients to send to Claude per call
FTS_MIN_RANK = 0.05      # minimum ts_rank to accept a FTS match
MODEL_LIGHT = "claude-sonnet-4-6"  # classification tasks

# ---------------------------------------------------------------------------
# Cleaning helpers
# ---------------------------------------------------------------------------

_PARENS_RE = re.compile(r'\(.*?\)')          # strip parenthetical notes
_E_NUMBER_RE = re.compile(r'\bE\d{3}[a-z]?\b', re.IGNORECASE)
_WHITESPACE_RE = re.compile(r'\s+')


def _clean(raw: str) -> str:
    """Normalize raw ingredient text for DB matching."""
    text = _PARENS_RE.sub('', raw)           # remove "(may contain nuts)"
    text = _WHITESPACE_RE.sub(' ', text)     # collapse whitespace
    return text.strip().lower()


def _extract_e_number(raw: str) -> str | None:
    """Extract the first E-number from a raw ingredient string, e.g. 'E471'."""
    m = _E_NUMBER_RE.search(raw)
    return m.group(0).upper() if m else None


# ---------------------------------------------------------------------------
# Step 1 — batch exact + alias + E-number (single query)
# ---------------------------------------------------------------------------

_BATCH_RESOLVE = """
WITH raw AS (
    SELECT unnest($1::text[]) AS raw_name
),
cleaned AS (
    SELECT raw_name, lower(trim(raw_name)) AS clean_name
    FROM raw
),
exact_match AS (
    SELECT c.raw_name, i.name AS canonical_name,
           i.safety_level, i.score_penalty, i.concerns, i.e_number, i.eu_status
    FROM cleaned c
    JOIN ingredients i ON i.name = c.clean_name
),
alias_match AS (
    SELECT c.raw_name, i.name AS canonical_name,
           i.safety_level, i.score_penalty, i.concerns, i.e_number, i.eu_status
    FROM cleaned c
    JOIN ingredient_aliases a ON lower(a.alias) = c.clean_name
    JOIN ingredients i ON i.id = a.ingredient_id
    WHERE c.raw_name NOT IN (SELECT raw_name FROM exact_match)
),
e_number_match AS (
    SELECT c.raw_name, i.name AS canonical_name,
           i.safety_level, i.score_penalty, i.concerns, i.e_number, i.eu_status
    FROM cleaned c
    JOIN ingredients i
         ON i.e_number IS NOT NULL
        AND upper(i.e_number) = upper(regexp_replace(c.clean_name, '\s.*', ''))
    WHERE c.raw_name NOT IN (SELECT raw_name FROM exact_match)
      AND c.raw_name NOT IN (SELECT raw_name FROM alias_match)
)
SELECT * FROM exact_match
UNION ALL
SELECT * FROM alias_match
UNION ALL
SELECT * FROM e_number_match
"""

# ---------------------------------------------------------------------------
# Step 2 — FTS via GIN index (one query per unresolved name)
# ---------------------------------------------------------------------------

_FTS_RESOLVE = """
SELECT i.name AS canonical_name,
       i.safety_level, i.score_penalty, i.concerns, i.e_number, i.eu_status,
       ts_rank(to_tsvector('english', a.alias),
               plainto_tsquery('english', $1)) AS rank
FROM ingredient_aliases a
JOIN ingredients i ON i.id = a.ingredient_id
WHERE to_tsvector('english', a.alias) @@ plainto_tsquery('english', $1)
ORDER BY rank DESC
LIMIT 1
"""

# ---------------------------------------------------------------------------
# Step 3 — Claude classification
# ---------------------------------------------------------------------------

class _IngredientClassification(BaseModel):
    raw_name: str
    canonical_name: str
    cas_number: str | None = None   # CAS registry number, e.g. "50-00-0"; null if unknown
    safety_level: Literal["safe", "caution", "avoid"]
    score_penalty: int          # 0–30
    concerns: list[str]         # e.g. ["allergen", "endocrine_disruptor"]
    eu_status: Literal["approved", "restricted", "banned", "unknown"]
    notes: str


class _ClassificationBatch(BaseModel):
    results: list[_IngredientClassification]


_CLAUDE_SYSTEM = """You are a food and cosmetic ingredient safety expert with deep knowledge of EU regulations (EFSA, CosIng, REACH).
For each ingredient provided, classify its safety based on scientific evidence and EU regulatory status.

safety_level rules:
- safe: well-studied, no significant concerns at typical doses
- caution: some evidence of concern, restricted use, or controversial
- avoid: banned/highly restricted in EU, strong evidence of harm, or endocrine disruptors

score_penalty: 0 = no penalty (safe), 5-10 = minor concern, 15-20 = moderate, 25-30 = serious

Common concern tags: allergen, carcinogen, endocrine_disruptor, neurotoxin, paraben,
sulfate, preservative, artificial_color, artificial_flavor, high_sugar, high_sodium,
nitrite, trans_fat, microplastic, formaldehyde_releaser

cas_number: provide the CAS Registry Number (e.g. "50-00-0") when you are confident of
the exact chemical identity. Use null if the ingredient name is ambiguous, refers to a
mixture, or you are not certain of the correct CAS."""


async def _classify_with_claude(names: list[str]) -> list[_IngredientClassification]:
    """Send up to CLAUDE_CAP unresolved ingredient names to Claude for classification."""
    if not names:
        return []

    names = names[:CLAUDE_CAP]
    client = anthropic.Anthropic()

    prompt = (
        "Classify the safety of each of the following ingredients. "
        "Return results for ALL of them.\n\n"
        + "\n".join(f"- {n}" for n in names)
    )

    try:
        response = client.messages.parse(
            model=MODEL_LIGHT,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": _CLAUDE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_format=_ClassificationBatch,  # SDK .parse() translates this to output_config internally
        )
        batch = response.parsed_output
        return batch.results if batch else []
    except Exception as e:
        print(f"  [RESOLVER] Claude classification error: {e}")
        return []


# ---------------------------------------------------------------------------
# Step 4 — write-back
# ---------------------------------------------------------------------------

_INSERT_INGREDIENT = """
INSERT INTO ingredients (name, cas_number, safety_level, score_penalty, concerns, eu_status, sources, notes)
VALUES ($1, $2, $3, $4, $5, $6, ARRAY['claude'], $7)
ON CONFLICT (name) DO NOTHING
RETURNING id
"""

_GET_INGREDIENT_ID = """
SELECT id FROM ingredients WHERE name = $1
"""

_INSERT_ALIAS = """
INSERT INTO ingredient_aliases (ingredient_id, alias, language)
VALUES ($1, $2, 'en')
ON CONFLICT (ingredient_id, alias) DO NOTHING
"""


async def _write_back(classifications: list[_IngredientClassification]) -> None:
    """Persist Claude-classified ingredients so future lookups hit steps 1-2."""
    if not classifications:
        return

    async with get_conn() as conn:
        async with conn.transaction():
            for c in classifications:
                # Insert canonical ingredient row
                ingredient_id = await conn.fetchval(
                    _INSERT_INGREDIENT,
                    c.canonical_name,
                    c.cas_number,
                    c.safety_level,
                    max(0, min(30, c.score_penalty)),
                    c.concerns or [],
                    c.eu_status,
                    c.notes,
                )

                # If INSERT hit a conflict, fetch the existing id
                if ingredient_id is None:
                    ingredient_id = await conn.fetchval(
                        _GET_INGREDIENT_ID, c.canonical_name
                    )

                if ingredient_id is None:
                    continue

                # Add the canonical name as an alias too (idempotent)
                await conn.execute(_INSERT_ALIAS, ingredient_id, c.canonical_name)

                # Add the original raw name as an alias if it differs
                if c.raw_name.lower() != c.canonical_name.lower():
                    await conn.execute(_INSERT_ALIAS, ingredient_id, c.raw_name.lower())

    print(f"  [RESOLVER] Wrote back {len(classifications)} ingredient(s) to DB.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict:
    return {
        "canonical_name": row["canonical_name"],
        "safety_level":   row["safety_level"],
        "score_penalty":  row["score_penalty"],
        "concerns":       list(row["concerns"] or []),
        "e_number":       row["e_number"],
        "eu_status":      row["eu_status"],
    }


async def resolve_ingredients(
    raw_names: list[str],
    use_claude: bool = False,
) -> dict[str, dict]:
    """
    Resolve a list of raw ingredient names to safety data.

    Steps 1-2 (DB exact/alias/E-number + FTS) always run.
    Step 3 (Claude classification + write-back) only runs when
    use_claude=True — call it explicitly from background jobs, not
    during a live scan request.

    Returns a dict mapping each raw_name that could be resolved to its
    safety data dict.  Names that remain unresolvable are absent.
    """
    if not raw_names:
        return {}

    resolved: dict[str, dict] = {}

    # ── Step 1: batch exact + alias + E-number ──────────────────────────────
    async with get_conn() as conn:
        rows = await conn.fetch(_BATCH_RESOLVE, raw_names)

    for row in rows:
        resolved[row["raw_name"]] = _row_to_dict(row)

    unresolved = [n for n in raw_names if n not in resolved]
    if not unresolved:
        return resolved

    # ── Step 2: FTS for remaining ────────────────────────────────────────────
    still_unresolved: list[str] = []

    async with get_conn() as conn:
        for name in unresolved:
            cleaned = _clean(name)
            if not cleaned:
                still_unresolved.append(name)
                continue
            try:
                row = await conn.fetchrow(_FTS_RESOLVE, cleaned)
            except Exception:
                row = None

            if row and row["rank"] >= FTS_MIN_RANK:
                resolved[name] = _row_to_dict(row)
            else:
                still_unresolved.append(name)

    # ── Step 3: Claude classification + write-back (opt-in only) ────────────
    if still_unresolved and use_claude:
        print(f"  [RESOLVER] {len(still_unresolved)} ingredient(s) → Claude "
              f"(cap={CLAUDE_CAP}).")
        classifications = await _classify_with_claude(still_unresolved)
        await _write_back(classifications)
        for c in classifications:
            resolved[c.raw_name] = {
                "canonical_name": c.canonical_name,
                "safety_level":   c.safety_level,
                "score_penalty":  max(0, min(30, c.score_penalty)),
                "concerns":       c.concerns or [],
                "e_number":       None,
                "eu_status":      c.eu_status,
            }

    return resolved
