"""
Photo-to-product agent.

Accepts up to two images (product front, ingredient list) and optional
metadata, then uses Claude vision to extract structured product and
ingredient data. Results are stored in user_submissions and returned
to the caller for immediate use.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel

from db.connection import get_conn

_client = anthropic.AsyncAnthropic()

MODEL_LIGHT = "claude-sonnet-4-6"  # extraction and parsing tasks

# Bounded wall-clock per Anthropic call. The SDK default (~10 min) is far too
# generous for an interactive photo submission — a hung connection would stall
# the request indefinitely. 60s comfortably accommodates adaptive thinking.
_VISION_TIMEOUT_S = 60.0

INSTRUCTIONS_DIR = Path(__file__).parent.parent / "instructions"


def _load(path: str) -> str:
    return (INSTRUCTIONS_DIR / path).read_text()


_IMAGE_SYSTEM   = _load("agents/image_agent.md")
_PARSER_SYSTEM  = _load("agents/ingredient_parser.md")

_IMAGE_SYSTEM_CACHED  = [{"type": "text", "text": _IMAGE_SYSTEM,  "cache_control": {"type": "ephemeral"}}]
_PARSER_SYSTEM_CACHED = [{"type": "text", "text": _PARSER_SYSTEM, "cache_control": {"type": "ephemeral"}}]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ExtractedProduct(BaseModel):
    brand:             Optional[str] = None
    product_name:      Optional[str] = None
    barcode:           Optional[str] = None
    product_type:      str           = "unknown"
    certifications:    list[str]     = []
    confidence:        float         = 0.0
    notes:             Optional[str] = None


class ParsedIngredient(BaseModel):
    name:              str
    position:          int
    is_allergen:       bool          = False
    is_fragrance_blend: bool         = False
    concerns:          list[str]     = []


class IngredientParseResponse(BaseModel):
    """Structured output schema for the ingredient parser vision call."""
    ingredients:        list[ParsedIngredient]
    parsing_confidence: float        = 0.0
    parsing_notes:      Optional[str] = None


class SubmissionResult(BaseModel):
    submission_id:     Optional[int] = None
    product:           ExtractedProduct
    ingredients:       list[ParsedIngredient]
    parsing_confidence: float        = 0.0
    parsing_notes:     Optional[str] = None
    ready_for_analysis: bool         = False  # True when we have enough to scan


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _encode_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Build an Anthropic image content block from raw bytes."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        },
    }


# ---------------------------------------------------------------------------
# Agent calls
# ---------------------------------------------------------------------------

async def _extract_product_info(image_bytes: bytes, media_type: str) -> ExtractedProduct:
    """Call Claude vision to extract brand/name/barcode from a product photo."""
    try:
        response = await _client.messages.parse(
            model=MODEL_LIGHT,
            max_tokens=2048,
            timeout=_VISION_TIMEOUT_S,
            thinking={"type": "adaptive"},
            system=_IMAGE_SYSTEM_CACHED,
            messages=[{
                "role": "user",
                "content": [
                    _encode_image(image_bytes, media_type),
                    {
                        "type": "text",
                        "text": (
                            "Extract all product identity information from this image. "
                            "Conform to the output schema."
                        ),
                    },
                ],
            }],
            output_format=ExtractedProduct,
        )
    except anthropic.APIError as e:
        print(f"  [IMAGE AGENT] Product extraction failed: {e}")
        return ExtractedProduct()

    return response.parsed_output or ExtractedProduct()


async def _parse_ingredients(
    image_bytes: bytes,
    media_type: str,
    product_type: str,
) -> tuple[list[ParsedIngredient], float, Optional[str]]:
    """Call Claude vision to parse an ingredient list photo."""
    try:
        response = await _client.messages.parse(
            model=MODEL_LIGHT,
            max_tokens=2048,
            timeout=_VISION_TIMEOUT_S,
            thinking={"type": "adaptive"},
            system=_PARSER_SYSTEM_CACHED,
            messages=[{
                "role": "user",
                "content": [
                    _encode_image(image_bytes, media_type),
                    {
                        "type": "text",
                        "text": (
                            f"Parse the ingredient list from this image. "
                            f"product_type: {product_type}. "
                            "Conform to the output schema."
                        ),
                    },
                ],
            }],
            output_format=IngredientParseResponse,
        )
    except anthropic.APIError as e:
        print(f"  [IMAGE AGENT] Ingredient parse failed: {e}")
        return [], 0.0, "Failed to parse agent response"

    parsed = response.parsed_output
    if parsed is None:
        return [], 0.0, "Empty agent response"

    return parsed.ingredients, parsed.parsing_confidence, parsed.parsing_notes


# ---------------------------------------------------------------------------
# DB write-back
# ---------------------------------------------------------------------------

_INSERT_SUBMISSION = """
INSERT INTO user_submissions (barcode, extracted_data, status)
VALUES ($1, $2::jsonb, 'pending')
ON CONFLICT (barcode) WHERE barcode IS NOT NULL
DO UPDATE SET
    extracted_data = EXCLUDED.extracted_data,
    status         = 'pending',
    created_at   = NOW()
RETURNING id
"""


async def _save_submission(barcode: Optional[str], result: SubmissionResult) -> int | None:
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                _INSERT_SUBMISSION,
                barcode,
                result.model_dump_json(),
            )
        return row["id"] if row else None
    except Exception as e:
        print(f"  [IMAGE AGENT] Failed to save submission: {e}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _parse_manual_ingredients(text: str, product_type: str) -> tuple[list[ParsedIngredient], float, str]:
    """Parse a comma/newline-separated ingredient string into ParsedIngredient objects."""
    import re
    tokens = re.split(r"[,\n;]+", text)
    ingredients = []
    for i, token in enumerate(tokens):
        name = token.strip().strip("*•-").strip()
        if not name:
            continue
        ingredients.append(ParsedIngredient(
            name=name,
            position=i + 1,
            is_allergen=False,
            is_fragrance_blend=False,
            concerns=[],
        ))
    confidence = 0.95 if ingredients else 0.0
    notes = f"{len(ingredients)} ingredients entered manually"
    return ingredients, confidence, notes


async def process_product_photos(
    product_image:           Optional[bytes],
    product_media_type:      str,
    ingredients_image:       Optional[bytes],
    ingredients_media_type:  str,
    barcode_hint:            Optional[str] = None,
    product_type_hint:       str = "unknown",
    manual_ingredients_text: Optional[str] = None,
) -> SubmissionResult:
    """
    Extract product data from one or two photos.

    product_image      — front of the product (optional but recommended)
    ingredients_image  — back/ingredient panel (optional but recommended)
    barcode_hint       — barcode entered manually by the user (if known)
    product_type_hint  — 'food' | 'cosmetic' | 'unknown'
    """
    extracted = ExtractedProduct(product_type=product_type_hint)
    ingredients: list[ParsedIngredient] = []
    parsing_confidence = 0.0
    parsing_notes: Optional[str] = None

    # Manual ingredient text overrides the photo if both are provided.
    manual_text = manual_ingredients_text.strip() if manual_ingredients_text else ""

    # Launch the two Claude vision calls concurrently. They're independent —
    # the parser receives the caller-provided product_type_hint rather than
    # waiting for the extractor's output. The common "both photos uploaded"
    # case now runs in max(extract, parse) wall-clock time instead of sum.
    extract_task = (
        asyncio.create_task(_extract_product_info(product_image, product_media_type))
        if product_image else None
    )
    parse_task = (
        asyncio.create_task(_parse_ingredients(ingredients_image, ingredients_media_type, product_type_hint))
        if ingredients_image and not manual_text else None
    )

    if extract_task is not None:
        extracted = await extract_task
        if barcode_hint:
            extracted.barcode = barcode_hint

    if parse_task is not None:
        ingredients, parsing_confidence, parsing_notes = await parse_task

    if manual_text:
        pt = extracted.product_type if extracted.product_type != "unknown" else product_type_hint
        ingredients, parsing_confidence, parsing_notes = _parse_manual_ingredients(manual_text, pt)

    # We can offer analysis if we have a barcode (extracted or hinted) + some ingredients
    barcode = extracted.barcode or barcode_hint
    ready = bool(barcode and (ingredients or extracted.product_name))

    result = SubmissionResult(
        product=extracted,
        ingredients=ingredients,
        parsing_confidence=parsing_confidence,
        parsing_notes=parsing_notes,
        ready_for_analysis=ready,
    )

    # Persist to user_submissions
    submission_id = await _save_submission(barcode, result)
    result.submission_id = submission_id

    return result
