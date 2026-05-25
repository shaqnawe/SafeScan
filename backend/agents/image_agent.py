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
import io
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional, TypeVar

import anthropic
from PIL import Image
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


CallStatus = Literal['ok', 'failed', 'not_attempted']


class SubmissionResult(BaseModel):
    submission_id:      Optional[int] = None
    product:            ExtractedProduct
    # 'not_attempted' when the user didn't upload a product photo; 'failed' when
    # the Anthropic call errored or returned nothing usable after a retry.
    product_status:     CallStatus     = 'not_attempted'
    ingredients:        list[ParsedIngredient]
    # 'ok' covers both image-parsed and manual-text-parsed ingredients;
    # 'failed' only happens on the image path.
    ingredients_status: CallStatus     = 'not_attempted'
    parsing_confidence: float          = 0.0
    parsing_notes:      Optional[str]  = None
    ready_for_analysis: bool           = False  # True when we have enough to scan


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


# Anthropic's vision API rejects images whose base64-encoded form exceeds 5MB.
# Base64 inflates raw bytes by ~33%, so 3.5MB raw is the safe ceiling.
_MAX_RAW_BYTES = 3_500_000
_MAX_DIMENSION = 2048  # longest side; preserves OCR-readable text


def _sniff_media_type(image_bytes: bytes) -> Optional[str]:
    """Detect image format from magic bytes. Returns None if unrecognized."""
    if image_bytes.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if image_bytes.startswith(b'GIF87a') or image_bytes.startswith(b'GIF89a'):
        return 'image/gif'
    if image_bytes[0:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return 'image/webp'
    return None


def validate_and_normalize_image(image_bytes: bytes) -> tuple[bytes, str]:
    """
    Validate image bytes and downsize if they would exceed Anthropic's 5MB
    base64 limit. Returns (possibly-resized bytes, magic-byte-verified MIME).

    Raises ValueError if the input is not a recognized image format
    (JPEG / PNG / GIF / WEBP) — the four formats Anthropic vision accepts.
    """
    if not image_bytes:
        raise ValueError("empty image")
    detected = _sniff_media_type(image_bytes)
    if detected is None:
        raise ValueError("unrecognized image format (expected JPEG/PNG/GIF/WEBP)")

    if len(image_bytes) <= _MAX_RAW_BYTES:
        return image_bytes, detected

    # Downscale via Pillow. Always re-encode as JPEG quality 85 — best
    # compression for photographs while preserving text readability.
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.Resampling.LANCZOS)

    out: bytes = b''
    for quality in (85, 75, 65, 55):
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        out = buf.getvalue()
        if len(out) <= _MAX_RAW_BYTES:
            return out, 'image/jpeg'
    # Even quality 55 was too large — return it anyway; Anthropic will reject
    # but the caller learns from the API error rather than a silent oversize.
    return out, 'image/jpeg'


# ---------------------------------------------------------------------------
# Agent calls
# ---------------------------------------------------------------------------

_T = TypeVar("_T")


async def _call_anthropic_with_retry(
    call_factory: Callable[[], Awaitable[_T]],
    label: str,
) -> Optional[_T]:
    """
    Execute an Anthropic call (provided as a zero-arg async factory). Retries
    once with a 1s backoff on transient errors (rate limit, timeout). Returns
    None on any permanent failure or after the retry is exhausted.

    The factory pattern (rather than passing a coroutine directly) lets us
    rebuild the request on each attempt, which is required because awaiting
    a coroutine twice raises RuntimeError.
    """
    for attempt in (1, 2):
        try:
            return await call_factory()
        except (anthropic.RateLimitError, anthropic.APITimeoutError) as e:
            if attempt == 1:
                print(f"  [IMAGE AGENT] {label} transient error, retrying in 1s: {e}")
                await asyncio.sleep(1.0)
                continue
            print(f"  [IMAGE AGENT] {label} failed after retry: {e}")
            return None
        except anthropic.APIError as e:
            print(f"  [IMAGE AGENT] {label} failed: {e}")
            return None
    return None  # unreachable; satisfies the type checker


async def _extract_product_info(image_bytes: bytes, media_type: str) -> Optional[ExtractedProduct]:
    """
    Call Claude vision to extract brand/name/barcode from a product photo.
    Returns None on permanent failure (logged by the retry helper); the
    orchestrator translates None into product_status='failed'.
    """
    response = await _call_anthropic_with_retry(
        lambda: _client.messages.parse(
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
        ),
        label="Product extraction",
    )
    if response is None:
        return None
    return response.parsed_output


async def _parse_ingredients(
    image_bytes: bytes,
    media_type: str,
    product_type: str,
) -> Optional[IngredientParseResponse]:
    """
    Call Claude vision to parse an ingredient list photo.
    Returns None on permanent failure (logged by the retry helper); the
    orchestrator translates None into ingredients_status='failed'.
    """
    response = await _call_anthropic_with_retry(
        lambda: _client.messages.parse(
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
        ),
        label="Ingredient parse",
    )
    if response is None:
        return None
    return response.parsed_output


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
    # 1) Glue '1, 2-Hexanediol' back to '1,2-Hexanediol' — pasted text sometimes
    #    introduces a stray space inside the chemical name.
    text = re.sub(r"(\d),\s+(\d)", r"\1,\2", text)
    # 2) Split on comma EXCEPT when the comma is followed by a digit (INCI
    #    chemicals like '1,2-Hexanediol', '1,3-Butylene Glycol' use a bare comma
    #    inside the name and a comma+space between ingredients). Newlines and
    #    semicolons are unconditional separators.
    tokens = re.split(r",(?!\d)|[\n;]+", text)
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
    product_status:     CallStatus = 'not_attempted'
    ingredients_status: CallStatus = 'not_attempted'

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
        extract_result = await extract_task
        if extract_result is not None:
            extracted = extract_result
            product_status = 'ok'
        else:
            product_status = 'failed'
        if barcode_hint:
            extracted.barcode = barcode_hint

    if parse_task is not None:
        parse_result = await parse_task
        if parse_result is not None:
            ingredients = parse_result.ingredients
            parsing_confidence = parse_result.parsing_confidence
            parsing_notes = parse_result.parsing_notes
            ingredients_status = 'ok'
        else:
            ingredients_status = 'failed'

    if manual_text:
        pt = extracted.product_type if extracted.product_type != "unknown" else product_type_hint
        ingredients, parsing_confidence, parsing_notes = _parse_manual_ingredients(manual_text, pt)
        ingredients_status = 'ok'

    # We can offer analysis if we have a barcode (extracted or hinted) + some ingredients
    barcode = extracted.barcode or barcode_hint
    ready = bool(barcode and (ingredients or extracted.product_name))

    result = SubmissionResult(
        product=extracted,
        product_status=product_status,
        ingredients=ingredients,
        ingredients_status=ingredients_status,
        parsing_confidence=parsing_confidence,
        parsing_notes=parsing_notes,
        ready_for_analysis=ready,
    )

    # Persist to user_submissions
    submission_id = await _save_submission(barcode, result)
    result.submission_id = submission_id

    return result
