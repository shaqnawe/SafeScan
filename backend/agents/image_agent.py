"""
Photo-to-product agent.

Accepts up to two images (product front, ingredient list) and optional
metadata, then uses Claude vision to extract structured product and
ingredient data. Results are stored in user_submissions and returned
to the caller for immediate use.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import BaseModel

from db.connection import get_conn

_client = anthropic.AsyncAnthropic()

INSTRUCTIONS_DIR = Path(__file__).parent.parent.parent / "instructions"


def _load(path: str) -> str:
    return (INSTRUCTIONS_DIR / path).read_text()


_IMAGE_SYSTEM   = _load("agents/image_agent.md")
_PARSER_SYSTEM  = _load("agents/ingredient_parser.md")


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
    response = await _client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=_IMAGE_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                _encode_image(image_bytes, media_type),
                {
                    "type": "text",
                    "text": (
                        "Extract all product identity information from this image. "
                        "Return a JSON object matching the output format specified in your instructions."
                    ),
                },
            ],
        }],
    )

    # Pull the JSON out of the response text
    text = next(
        (b.text for b in response.content if hasattr(b, 'text') and b.text.strip()),
        "{}"
    )
    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]

    try:
        data = json.loads(text)
    except Exception:
        return ExtractedProduct()

    return ExtractedProduct(
        brand=data.get("brand"),
        product_name=data.get("product_name"),
        barcode=data.get("barcode"),
        product_type=data.get("product_type", "unknown"),
        certifications=data.get("certifications", []),
        confidence=float(data.get("confidence", 0.0)),
        notes=data.get("notes"),
    )


async def _parse_ingredients(
    image_bytes: bytes,
    media_type: str,
    product_type: str,
) -> tuple[list[ParsedIngredient], float, Optional[str]]:
    """Call Claude vision to parse an ingredient list photo."""
    response = await _client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=_PARSER_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                _encode_image(image_bytes, media_type),
                {
                    "type": "text",
                    "text": (
                        f"Parse the ingredient list from this image. "
                        f"product_type: {product_type}. "
                        "Return a JSON object matching the output format in your instructions."
                    ),
                },
            ],
        }],
    )

    text = next(
        (b.text for b in response.content if hasattr(b, 'text') and b.text.strip()),
        "{}"
    )
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]

    try:
        data = json.loads(text)
    except Exception:
        return [], 0.0, "Failed to parse agent response"

    ingredients = []
    for item in data.get("ingredients", []):
        ingredients.append(ParsedIngredient(
            name=item.get("name", ""),
            position=int(item.get("position", len(ingredients) + 1)),
            is_allergen=bool(item.get("is_allergen", False)),
            is_fragrance_blend=bool(item.get("is_fragrance_blend", False)),
            concerns=[],
        ))

    confidence = float(data.get("parsing_confidence", 0.0))
    notes = data.get("parsing_notes")
    return ingredients, confidence, notes


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

    # Extract product identity from front photo
    if product_image:
        extracted = await _extract_product_info(product_image, product_media_type)
        # Manual barcode overrides extracted one
        if barcode_hint:
            extracted.barcode = barcode_hint

    # Parse ingredient list — manual text takes priority over photo
    pt = extracted.product_type if extracted.product_type != "unknown" else product_type_hint
    if manual_ingredients_text and manual_ingredients_text.strip():
        ingredients, parsing_confidence, parsing_notes = _parse_manual_ingredients(
            manual_ingredients_text, pt
        )
    elif ingredients_image:
        ingredients, parsing_confidence, parsing_notes = await _parse_ingredients(
            ingredients_image, ingredients_media_type, pt
        )

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
