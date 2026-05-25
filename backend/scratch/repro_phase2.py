"""
Bisecting harness for the Phase 2 disconnect bug.

Background:
  scanner.analyze_product()'s Phase 2 call hangs ~280s then APIConnectionError
  for any scan where lookup_product returns a tool_result with non-trivial
  ingredient content (>~1KB). Previously ruled out (see CLAUDE.md "Phase 2
  disconnect bug"): parse vs create, adaptive thinking on/off (partial),
  alternation, redacted_thinking leak.

Strategy:
  6 variants, each changing ONE variable from baseline. Run all, read the
  pass/fail matrix to pin the trigger:

    baseline                exact failing payload
    no_thinking             drops thinking={"type":"adaptive"}
    sonnet                  swaps Opus -> Sonnet
    no_synthetic_preflight  removes the seeded tool_use/tool_result, inlines
                            the ingredient data into the user prompt
    tiny_tool_result        keeps the synthetic preflight structure but shrinks
                            the tool_result content to ~100 chars
    no_system_prompt        replaces the 33K system prompt with one sentence

Usage:
  cd backend
  python -m scratch.repro_phase2                 # run all variants
  python -m scratch.repro_phase2 baseline        # run one
  python -m scratch.repro_phase2 --list          # list variants
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

MODEL_HEAVY = "claude-opus-4-6"
MODEL_LIGHT = "claude-sonnet-4-6"
PER_CALL_TIMEOUT_S = 120.0

client = anthropic.AsyncAnthropic(
    max_retries=0,  # don't auto-retry — we want to see raw failures
    timeout=anthropic.Timeout(PER_CALL_TIMEOUT_S, connect=10.0),
)

INSTR = Path(__file__).parent.parent / "instructions"
FULL_SYSTEM_PROMPT = "\n\n".join([
    (INSTR / "agents/analysis_agent.md").read_text(),
    (INSTR / "data/scoring_rubric.md").read_text(),
    (INSTR / "data/eu_regulations.md").read_text(),
])
MINIMAL_SYSTEM_PROMPT = (
    "You are a product safety analyst. Return a JSON object describing the "
    "safety of the product. Use grade A/B/C/D and score 0-100."
)

BARCODE = "8809838658313"

# Captured verbatim from /tmp/scanner_phase2_dump.json — the actual failing
# payload from the body wash submission (id=7).
PREFLIGHT_RESULT = {
    "found": True,
    "source": "user_submission",
    "product_type": "cosmetic",
    "name": "R.E.D BLEMISH Clear Soothing Body Wash",
    "brand": "Dr.G",
    "image_url": None,
    "nutriscore": "",
    "nova_group": None,
    "categories": [],
    "ingredients": (
        "Water(Aqua/Eau), Glycerin, Lauryl Betaine, Potassium Cocoyl Glycinate, "
        "Lauryl Hydroxysultaine, Sodium Chloride, 1, 2-Hexanediol, "
        "Acrylates/C10-30 Alkyl Acrylate Crosspolymer, Betaine, Salicylic Acid, "
        "Panthenol, Disodium Cocoamphodiacetate, Hydroxyacetophenone, "
        "Centella Asiatica Extract, Mentha Aquatica Extract, Fragrance(Parfum), "
        "Morinda Citrifolia Fruit Extract, Mentha Rotundifolia Leaf Extract, "
        "Disodium EDTA, Ethylhexylglycerin, Lactobacillus Ferment Lysate, "
        "Olea Europaea (Olive) Fruit Oil, Hydrogenated Soybean Oil, "
        "Hexylene Glycol, Butylene Glycol, Madecassoside, Madecassic Acid, "
        "Asiaticoside, Asiatic Acid, Dimethylsilanol Hyaluronate, "
        "Hydrolyzed Sodium Hyaluronate, Hydrolyzed Hyaluronic Acid, "
        "Sodium Hyaluronate, Potassium Hyaluronate, Hyaluronic Acid, "
        "Sodium Hyaluronate Crosspolymer, Hydroxypropyltrimonium Hyaluronate, "
        "Sodium Hyaluronate Dimethylsilanol, Sodium Acetylated Hyaluronate, "
        "Gluconolactone, Capryloyl Salicylic Acid"
    ),
    "resolved_ingredients": [],
    "db_resolved_count": 0,
    "total_ingredients": 42,
}

TINY_RESULT = {"found": True, "name": "Test Product", "ingredients": "Water"}

INITIAL_USER_MSG = (
    f"Please analyze the safety of the product with barcode {BARCODE}. "
    "First look up the product information, then provide a comprehensive safety analysis. "
    "If the product data includes 'resolved_ingredients' with pre-computed safety levels "
    "from our EU ingredient database, use that data to anchor your analysis."
)

PHASE_2_PROMPT = (
    f"Based on the product information you retrieved, now provide a structured safety report. "
    f"The barcode is {BARCODE}. "
    "If the product was not found in any database, set not_found=true and provide a minimal report. "
    "Otherwise, analyze all available ingredients and data thoroughly. "
    "If resolved_ingredients were provided with pre-computed safety levels, incorporate them directly. "
    "Return a complete safety assessment following the scoring guidelines: "
    "A=75-100 (excellent), B=50-74 (good), C=25-49 (average), D=0-24 (poor). "
    "Compute an appropriate score (0-100) and corresponding grade (A/B/C/D).\n\n"
    "Reply with ONLY a JSON object — no prose, no markdown fences — matching this exact schema:\n"
    '{"product_name": "string", "brand": "string", "product_type": "food|cosmetic|unknown|drug", '
    '"barcode": "string", "image_url": "string|null", "score": 0-100, "grade": "A|B|C|D", '
    '"summary": "string", "ingredients_analysis": [{"name": "string", '
    '"safety_level": "safe|caution|avoid", "concern": "string|null"}], '
    '"positive_points": ["string"], "negative_points": ["string"], "not_found": false}'
)


def baseline_messages(tool_result_payload: dict | None = None) -> list[dict]:
    """The exact 5-message stack scanner.py sends to Phase 2."""
    payload = tool_result_payload if tool_result_payload is not None else PREFLIGHT_RESULT
    return [
        {"role": "user", "content": INITIAL_USER_MSG},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "preflight_lookup",
             "name": "lookup_product", "input": {"barcode": BARCODE}}
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "preflight_lookup",
             "content": json.dumps(payload)}
        ]},
        {"role": "assistant",
         "content": "Lookup complete. Ready to produce the structured safety report."},
        {"role": "user", "content": PHASE_2_PROMPT},
    ]


def inlined_messages() -> list[dict]:
    """No synthetic tool_use/tool_result — ingredients inlined into the user prompt."""
    return [
        {"role": "user", "content": (
            INITIAL_USER_MSG
            + "\n\nHere is the product information retrieved by the lookup:\n"
            + json.dumps(PREFLIGHT_RESULT)
            + "\n\n" + PHASE_2_PROMPT
        )},
    ]


VARIANTS: dict[str, dict[str, Any]] = {
    "baseline": {
        "model": MODEL_HEAVY,
        "thinking": {"type": "adaptive"},
        "system": FULL_SYSTEM_PROMPT,
        "messages": baseline_messages(),
    },
    "no_thinking": {
        "model": MODEL_HEAVY,
        "thinking": None,
        "system": FULL_SYSTEM_PROMPT,
        "messages": baseline_messages(),
    },
    "sonnet": {
        "model": MODEL_LIGHT,
        "thinking": {"type": "adaptive"},
        "system": FULL_SYSTEM_PROMPT,
        "messages": baseline_messages(),
    },
    "no_synthetic_preflight": {
        "model": MODEL_HEAVY,
        "thinking": {"type": "adaptive"},
        "system": FULL_SYSTEM_PROMPT,
        "messages": inlined_messages(),
    },
    "tiny_tool_result": {
        "model": MODEL_HEAVY,
        "thinking": {"type": "adaptive"},
        "system": FULL_SYSTEM_PROMPT,
        "messages": baseline_messages(tool_result_payload=TINY_RESULT),
    },
    "no_system_prompt": {
        "model": MODEL_HEAVY,
        "thinking": {"type": "adaptive"},
        "system": MINIMAL_SYSTEM_PROMPT,
        "messages": baseline_messages(),
    },
}


async def run_variant(name: str, cfg: dict) -> dict:
    sys_label = "full" if len(cfg["system"]) > 500 else "minimal"
    msg_count = len(cfg["messages"])
    print(f"\n=== {name} ===")
    print(f"  model={cfg['model']}  thinking={cfg['thinking']}  "
          f"system={sys_label}({len(cfg['system'])}c)  messages={msg_count}")

    kwargs: dict[str, Any] = {
        "model": cfg["model"],
        "max_tokens": 8192,
        "system": [{"type": "text", "text": cfg["system"],
                    "cache_control": {"type": "ephemeral"}}],
        "messages": cfg["messages"],
    }
    if cfg["thinking"]:
        kwargs["thinking"] = cfg["thinking"]

    start = time.time()
    try:
        resp = await client.messages.create(**kwargs)
        dur = time.time() - start
        text_chars = sum(
            len(b.text) for b in resp.content
            if getattr(b, "type", None) == "text"
        )
        result = {
            "ok": True,
            "duration_s": dur,
            "stop_reason": resp.stop_reason,
            "text_chars": text_chars,
            "in_tokens": resp.usage.input_tokens,
            "out_tokens": resp.usage.output_tokens,
        }
        print(f"  PASS  {dur:6.1f}s  text={text_chars}c  "
              f"in={result['in_tokens']}  out={result['out_tokens']}  "
              f"stop={result['stop_reason']}")
    except Exception as e:
        dur = time.time() - start
        result = {"ok": False, "duration_s": dur,
                  "error": f"{type(e).__name__}: {e}"}
        print(f"  FAIL  {dur:6.1f}s  {result['error']}")
    return result


async def main():
    args = [a for a in sys.argv[1:] if a]
    if "--list" in args:
        for k in VARIANTS:
            print(k)
        return
    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    targets = [a for a in args if a in VARIANTS] or list(VARIANTS.keys())
    unknown = [a for a in args if a not in VARIANTS and not a.startswith("-")]
    if unknown:
        print(f"Unknown variant(s): {unknown}. Use --list to see options.")
        sys.exit(1)

    print(f"Running {len(targets)} variant(s): {', '.join(targets)}")
    print(f"Per-call timeout: {PER_CALL_TIMEOUT_S}s")

    results = {}
    for name in targets:
        results[name] = await run_variant(name, VARIANTS[name])

    print("\n=== SUMMARY ===")
    for name, r in results.items():
        status = "PASS" if r["ok"] else "FAIL"
        detail = (
            r["error"] if not r["ok"]
            else f"in={r['in_tokens']:>5}  out={r['out_tokens']:>4}  stop={r['stop_reason']}"
        )
        print(f"  {status}  {name:<26s}  {r['duration_s']:>6.1f}s  {detail}")

    # Quick interpretation hint
    passing = [n for n, r in results.items() if r["ok"]]
    failing = [n for n, r in results.items() if not r["ok"]]
    print("\n=== INTERPRETATION ===")
    print(f"  Passed: {passing or '(none)'}")
    print(f"  Failed: {failing or '(none)'}")
    if "baseline" in failing and len(passing) == 1:
        print(f"  -> Single trigger isolated: changing '{passing[0]}' fixes it.")
    elif "baseline" in passing:
        print("  -> Baseline succeeded; bug did not reproduce. Check API status / payload drift.")
    elif not passing:
        print("  -> Nothing passed; trigger is broader than any single variable.")
    else:
        print(f"  -> Multiple passes ({passing}); fix likely requires combining changes.")


if __name__ == "__main__":
    asyncio.run(main())
