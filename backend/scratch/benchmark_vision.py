"""
Vision-OCR benchmark: Claude vs OpenAI on the same image, same prompt.

Runs the production ingredient-parser system prompt + Pydantic schema through
three providers in parallel and reports ingredient count, parsing_confidence,
wall time, token usage, and USD cost per call. If a truth list is provided,
also runs the diff_extraction comparison and reports recall + precision per
provider.

Providers compared (configurable via --providers):
  - claude       Claude Sonnet 4.6 (current production model)
  - gpt4o-mini   GPT-4o-mini (cheap candidate)
  - gpt4o        GPT-4o (premium candidate)

Usage:
  cd backend

  # Benchmark all three providers on an image:
  python -m scratch.benchmark_vision /path/to/ingredients.jpg

  # With ground-truth list for recall/precision comparison:
  python -m scratch.benchmark_vision /path/to/ingredients.jpg \\
      --truth-file truth.txt --product-type cosmetic

  # Just Claude vs gpt-4o-mini (cheapest comparison):
  python -m scratch.benchmark_vision img.jpg --providers claude,gpt4o-mini
"""

import argparse
import asyncio
import base64
import sys
import time
from pathlib import Path
from typing import Any, Optional

import anthropic
import openai
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Reuse the production schema + prompt verbatim so results are apples-to-apples.
# Done after load_dotenv so the agents module sees the env on import.
sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.image_agent import IngredientParseResponse  # noqa: E402
from scratch.diff_extraction import diff, split_list    # noqa: E402

INSTRUCTIONS_DIR = Path(__file__).parent.parent / "instructions"
PARSER_PROMPT = (INSTRUCTIONS_DIR / "agents/ingredient_parser.md").read_text()

ANTHROPIC_MODEL = "claude-sonnet-4-6"

# Pricing per 1M tokens (USD), as of 2026-Q2.
# Sources: anthropic.com/pricing, openai.com/api/pricing
PRICING = {
    "claude-sonnet-4-6": {"in": 3.00,  "out": 15.00},
    "gpt-4o-mini":       {"in": 0.15,  "out": 0.60},
    "gpt-4o":            {"in": 2.50,  "out": 10.00},
}

_TIMEOUT_S = 60.0
_MAX_TOKENS = 4096


def _sniff_media_type(image_bytes: bytes) -> str:
    """Identify the image's MIME type from its magic bytes."""
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _user_prompt(product_type: str) -> str:
    return (
        f"Parse the ingredient list from this image. "
        f"product_type: {product_type}. "
        "Conform to the output schema."
    )


async def call_anthropic(
    image_bytes: bytes, media_type: str, product_type: str
) -> dict[str, Any]:
    client = anthropic.AsyncAnthropic()
    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
    t0 = time.time()
    try:
        response = await client.messages.parse(
            model=ANTHROPIC_MODEL,
            max_tokens=_MAX_TOKENS,
            timeout=_TIMEOUT_S,
            system=[{"type": "text", "text": PARSER_PROMPT}],
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": encoded},
                    },
                    {"type": "text", "text": _user_prompt(product_type)},
                ],
            }],
            output_format=IngredientParseResponse,
        )
    except Exception as e:
        return {
            "ok": False, "provider": "anthropic", "model": ANTHROPIC_MODEL,
            "duration_s": time.time() - t0, "error": f"{type(e).__name__}: {e}",
        }
    dur = time.time() - t0
    parsed = response.parsed_output
    if parsed is None:
        return {
            "ok": False, "provider": "anthropic", "model": ANTHROPIC_MODEL,
            "duration_s": dur, "error": "parsed_output=None",
        }
    in_tok = response.usage.input_tokens
    out_tok = response.usage.output_tokens
    cost = (
        (in_tok / 1_000_000) * PRICING[ANTHROPIC_MODEL]["in"]
        + (out_tok / 1_000_000) * PRICING[ANTHROPIC_MODEL]["out"]
    )
    return {
        "ok": True,
        "provider": "anthropic",
        "model": ANTHROPIC_MODEL,
        "duration_s": dur,
        "ingredients": [i.name for i in parsed.ingredients],
        "parsing_confidence": parsed.parsing_confidence,
        "parsing_notes": parsed.parsing_notes,
        "in_tokens": in_tok,
        "out_tokens": out_tok,
        "cost_usd": cost,
    }


async def call_openai(
    image_bytes: bytes, media_type: str, product_type: str, model: str
) -> dict[str, Any]:
    client = openai.AsyncOpenAI()
    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{media_type};base64,{encoded}"
    t0 = time.time()
    try:
        response = await client.beta.chat.completions.parse(
            model=model,
            max_tokens=_MAX_TOKENS,
            timeout=_TIMEOUT_S,
            messages=[
                {"role": "system", "content": PARSER_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": _user_prompt(product_type)},
                ]},
            ],
            response_format=IngredientParseResponse,
        )
    except Exception as e:
        return {
            "ok": False, "provider": "openai", "model": model,
            "duration_s": time.time() - t0, "error": f"{type(e).__name__}: {e}",
        }
    dur = time.time() - t0
    msg = response.choices[0].message
    if getattr(msg, "refusal", None):
        return {
            "ok": False, "provider": "openai", "model": model,
            "duration_s": dur, "error": f"refusal: {msg.refusal}",
        }
    parsed = msg.parsed
    if parsed is None:
        return {
            "ok": False, "provider": "openai", "model": model,
            "duration_s": dur, "error": "parsed=None",
        }
    in_tok = response.usage.prompt_tokens
    out_tok = response.usage.completion_tokens
    cost = (
        (in_tok / 1_000_000) * PRICING[model]["in"]
        + (out_tok / 1_000_000) * PRICING[model]["out"]
    )
    return {
        "ok": True,
        "provider": "openai",
        "model": model,
        "duration_s": dur,
        "ingredients": [i.name for i in parsed.ingredients],
        "parsing_confidence": parsed.parsing_confidence,
        "parsing_notes": parsed.parsing_notes,
        "in_tokens": in_tok,
        "out_tokens": out_tok,
        "cost_usd": cost,
    }


def print_result(r: dict[str, Any], truth: Optional[list[str]] = None) -> None:
    label = f"{r.get('provider', '?')}/{r.get('model', '?')}"
    print(f"\n=== {label} ===")
    if not r["ok"]:
        print(f"  duration:  {r['duration_s']:.1f}s")
        print(f"  error:     {r['error']}")
        return
    print(f"  duration:    {r['duration_s']:.1f}s")
    print(f"  in_tokens:   {r['in_tokens']:>5}")
    print(f"  out_tokens:  {r['out_tokens']:>5}")
    print(f"  cost:        ${r['cost_usd']:.5f}")
    print(f"  confidence:  {r['parsing_confidence']:.2f}")
    print(f"  ingredients: {len(r['ingredients'])}")
    notes = r.get("parsing_notes")
    if notes:
        snippet = notes[:200]
        suffix = "..." if len(notes) > 200 else ""
        print(f"  notes:       {snippet}{suffix}")
    print(f"  list:")
    for i, ing in enumerate(r["ingredients"], 1):
        print(f"    {i:2d}. {ing}")
    if truth is not None:
        d = diff(r["ingredients"], truth)
        captured = len(d["matched"]) + len(d["fuzzy"])
        recall = captured / max(len(truth), 1)
        precision = captured / max(len(r["ingredients"]), 1)
        print(
            f"  vs truth:    recall {recall:.1%}  precision {precision:.1%}  "
            f"matched={len(d['matched'])}  fuzzy={len(d['fuzzy'])}  "
            f"missed={len(d['missed'])}  extra={len(d['extra'])}"
        )


def print_summary(results: list[dict[str, Any]], truth: Optional[list[str]]) -> None:
    print("\n=== SUMMARY ===")
    if truth is not None:
        header = f"  {'provider/model':<28s}  {'time':>6s}  {'cost':>9s}  {'count':>5s}  {'conf':>5s}  {'recall':>7s}  {'prec':>7s}"
    else:
        header = f"  {'provider/model':<28s}  {'time':>6s}  {'cost':>9s}  {'count':>5s}  {'conf':>5s}"
    print(header)
    for r in results:
        label = f"{r.get('provider', '?')}/{r.get('model', '?')}"
        if not r["ok"]:
            print(f"  {label:<28s}  {r['duration_s']:>5.1f}s  --        FAIL: {r['error'][:50]}")
            continue
        base = (
            f"  {label:<28s}  {r['duration_s']:>5.1f}s  ${r['cost_usd']:>8.5f}  "
            f"{len(r['ingredients']):>5d}  {r['parsing_confidence']:>5.2f}"
        )
        if truth is not None:
            d = diff(r["ingredients"], truth)
            captured = len(d["matched"]) + len(d["fuzzy"])
            recall = captured / max(len(truth), 1)
            precision = captured / max(len(r["ingredients"]), 1)
            base += f"  {recall:>6.1%}  {precision:>6.1%}"
        print(base)

    # Cost comparison summary
    ok_results = [r for r in results if r["ok"]]
    if len(ok_results) >= 2:
        cheapest = min(ok_results, key=lambda r: r["cost_usd"])
        priciest = max(ok_results, key=lambda r: r["cost_usd"])
        if cheapest["cost_usd"] > 0:
            ratio = priciest["cost_usd"] / cheapest["cost_usd"]
            print(
                f"\n  Cost spread: {cheapest['model']} (${cheapest['cost_usd']:.5f}) → "
                f"{priciest['model']} (${priciest['cost_usd']:.5f}) = {ratio:.1f}× difference"
            )


async def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("image", help="Path to the image file to OCR")
    p.add_argument("--truth-file", help="Ground-truth ingredient list file")
    p.add_argument("--truth-text", help="Inline ground-truth ingredients")
    p.add_argument(
        "--product-type",
        default="unknown",
        choices=["food", "cosmetic", "drug", "unknown"],
    )
    p.add_argument(
        "--providers",
        default="claude,gpt4o-mini,gpt4o",
        help="Comma-separated subset of: claude,gpt4o-mini,gpt4o",
    )
    args = p.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")
    image_bytes = image_path.read_bytes()
    media_type = _sniff_media_type(image_bytes)
    print(f"Image:        {image_path}")
    print(f"  size:       {len(image_bytes):,} bytes")
    print(f"  media_type: {media_type}")
    print(f"  product_type hint: {args.product_type}")

    truth: Optional[list[str]] = None
    if args.truth_text:
        truth = split_list(args.truth_text)
    elif args.truth_file:
        truth = split_list(Path(args.truth_file).read_text())
    if truth is not None:
        print(f"  truth list: {len(truth)} ingredients")

    requested = {s.strip() for s in args.providers.split(",") if s.strip()}
    tasks = []
    if "claude" in requested:
        tasks.append(call_anthropic(image_bytes, media_type, args.product_type))
    if "gpt4o-mini" in requested:
        tasks.append(call_openai(image_bytes, media_type, args.product_type, "gpt-4o-mini"))
    if "gpt4o" in requested:
        tasks.append(call_openai(image_bytes, media_type, args.product_type, "gpt-4o"))

    if not tasks:
        raise SystemExit(f"No valid providers in --providers={args.providers}")

    print(f"\nRunning {len(tasks)} provider(s) in parallel...")
    results = await asyncio.gather(*tasks)
    for r in results:
        print_result(r, truth)
    print_summary(results, truth)


if __name__ == "__main__":
    asyncio.run(main())
