"""
UPCitemdb barcode fallback fetcher.

Runtime API call — NOT a bulk importer. Called from lookup_product() in scanner.py
when a barcode is not found in the local DB, OFF, or OBF.

Uses the UPCitemdb trial endpoint — no API key required. Rate limited to
100 lookups/day per IP address.

API docs: https://www.upcitemdb.com/api/explorer#!/lookup/get_trial_lookup
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://api.upcitemdb.com/prod/trial/lookup"
_TIMEOUT = 8.0
_BACKOFF = 3.0


def _infer_product_type(category: str) -> str:
    """Best-effort product type from the UPCitemdb category string."""
    cat = category.lower()
    if any(kw in cat for kw in ("food", "beverage", "grocery", "snack", "drink")):
        return "food"
    if any(kw in cat for kw in ("beauty", "personal care", "cosmetic", "skin", "hair", "fragrance")):
        return "cosmetic"
    return "unknown"


async def fetch(barcode: str) -> dict[str, Any] | None:
    """
    Look up a barcode on UPCitemdb (trial endpoint, no auth required).

    Returns a normalized product dict on hit, None on miss or error.
    The returned dict matches the shape expected by lookup_product() in scanner.py:
      found, source, product_type, name, brand, ingredients, image_url, categories

    Note: UPCitemdb does not return ingredient data. ingredients is always "".

    Rate limit: 100 lookups/day per IP. On 429, logs a warning and returns None
    without retrying.
    """
    params = {"upc": barcode}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # One retry with backoff on transient errors; never retry a 429.
        for attempt in (1, 2):
            try:
                response = await client.get(_API_URL, params=params)
            except httpx.TimeoutException:
                if attempt == 1:
                    logger.warning("[UPCITEMDB] timeout on attempt %d for barcode=%s, retrying in %.0fs",
                                   attempt, barcode, _BACKOFF)
                    await asyncio.sleep(_BACKOFF)
                    continue
                logger.warning("[UPCITEMDB] timeout on attempt %d for barcode=%s, giving up", attempt, barcode)
                return None
            except httpx.RequestError as exc:
                if attempt == 1:
                    logger.warning("[UPCITEMDB] request error for barcode=%s: %s, retrying in %.0fs",
                                   barcode, exc, _BACKOFF)
                    await asyncio.sleep(_BACKOFF)
                    continue
                logger.warning("[UPCITEMDB] request error for barcode=%s: %s, giving up", barcode, exc)
                return None

            if response.status_code == 429:
                logger.warning("[UPCITEMDB] rate limit hit (429) for barcode=%s — daily quota exhausted", barcode)
                return None

            if response.status_code != 200:
                logger.warning("[UPCITEMDB] unexpected status %d for barcode=%s", response.status_code, barcode)
                return None

            # Success on first valid response
            break

        try:
            data = response.json()
        except Exception as exc:
            logger.warning("[UPCITEMDB] failed to parse JSON for barcode=%s: %s", barcode, exc)
            return None

    items = data.get("items") or []
    if not items:
        logger.info("[UPCITEMDB] miss — barcode=%s not found", barcode)
        return None

    item = items[0]
    name = item.get("title", "").strip()
    brand = item.get("brand", "").strip()
    category = item.get("category", "")
    images = item.get("images") or []
    image_url = images[0] if images else None

    if not name:
        logger.info("[UPCITEMDB] miss — barcode=%s returned empty title", barcode)
        return None

    product_type = _infer_product_type(category)
    logger.info("[UPCITEMDB] hit — barcode=%s name='%s' brand='%s' type=%s",
                barcode, name, brand, product_type)

    return {
        "found":        True,
        "source":       "upcitemdb",
        "product_type": product_type,
        "name":         name,
        "brand":        brand,
        "ingredients":  "",   # UPCitemdb does not provide ingredient data
        "image_url":    image_url,
        "categories":   category,
    }
