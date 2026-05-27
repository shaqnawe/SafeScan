import json
import httpx
import anthropic
from pathlib import Path
from typing import Any, Optional
from models import SafetyReport
from db.queries import (
    get_product_from_db, get_cached_report, cache_report, get_user_submission,
    set_submission_analyzing, set_submission_complete, set_submission_failed,
)
from db.connection import get_conn
from db.recall_store import check_product_recalls
from agents.local_analyzer import build_report
from agents.fetchers import upcitemdb as _upcitemdb

from models import RecallAlert

client = anthropic.AsyncAnthropic(
    max_retries=3,
    timeout=anthropic.Timeout(600.0, connect=10.0),
)

MODEL_HEAVY = "claude-opus-4-6"    # deep safety analysis (Phase 2)
MODEL_LIGHT = "claude-sonnet-4-6"  # lookup, extraction, classification

INSTRUCTIONS_DIR = Path(__file__).parent.parent / "instructions"


async def _attach_recalls(report: SafetyReport) -> list[RecallAlert]:
    """Check the recall DB and return any matching alerts for this product."""
    try:
        raw = await check_product_recalls(
            product_name=report.product_name,
            brand=report.brand,
            barcode=report.barcode,
        )
        alerts = []
        for r in raw:
            pub = r.get("published_at")
            alerts.append(RecallAlert(
                title=r["title"],
                description=r.get("description"),
                risk_level=r.get("risk_level"),
                category=r.get("category"),
                link=r.get("link"),
                published_at=pub.isoformat() if pub else None,
            ))
        if alerts:
            print(f"  [RECALLS] {len(alerts)} recall(s) found for '{report.product_name}'")
        return alerts
    except Exception as e:
        print(f"  [RECALLS] Check failed (non-fatal): {e}")
        return []


def load_instruction(path: str) -> str:
    return (INSTRUCTIONS_DIR / path).read_text()


SYSTEM_PROMPT = "\n\n".join([
    load_instruction("agents/analysis_agent.md"),
    load_instruction("data/scoring_rubric.md"),
    load_instruction("data/eu_regulations.md"),
])

LOOKUP_TOOL = {
    "name": "lookup_product",
    "description": (
        "Look up product information by barcode. "
        "Checks the local database first (faster, includes pre-resolved ingredient safety data), "
        "then falls back to Open Food Facts, Open Beauty Facts, and UPCitemdb APIs. "
        "Returns product name, brand, ingredients list, resolved safety data where available, and category."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "barcode": {
                "type": "string",
                "description": "Product barcode (EAN-13, UPC-A, etc.)"
            }
        },
        "required": ["barcode"]
    }
}


_UPSERT_UPCITEMDB_PRODUCT = """
INSERT INTO products (barcode, name, brand, product_type, image_url, categories, source, last_synced_at)
VALUES ($1, $2, $3, $4, $5, $6, 'upcitemdb', NOW())
ON CONFLICT (barcode) DO UPDATE SET
    name           = EXCLUDED.name,
    brand          = EXCLUDED.brand,
    product_type   = EXCLUDED.product_type,
    image_url      = COALESCE(EXCLUDED.image_url, products.image_url),
    categories     = EXCLUDED.categories,
    last_synced_at = NOW()
"""


async def _upsert_upcitemdb_product(barcode: str, data: dict) -> None:
    """Persist a UPCitemdb hit to the local products table for future cache hits."""
    raw_cats = data.get("categories") or ""
    cats = [c.strip() for c in raw_cats.split(">") if c.strip()] if raw_cats else []
    async with get_conn() as conn:
        await conn.execute(
            _UPSERT_UPCITEMDB_PRODUCT,
            barcode,
            data["name"],
            data["brand"],
            data["product_type"],
            data["image_url"],
            cats,
        )


async def lookup_product(barcode: str) -> dict[str, Any]:
    """
    Look up product data. Priority order (highest-fidelity first):
    1. Local PostgreSQL database from a rich source (off / obf / usda / openfda
       / dailymed) — curated ingredient data already resolved against the
       ingredients table. UPCitemdb-cached local rows do NOT count here —
       they're name+brand only and get held for the last-resort fallback.
    2. User submission with parsed ingredients — a photo upload that produced
       a real ingredient list beats UPCitemdb's name-only data and is worth
       checking before hitting the live external APIs.
    3. Open Food Facts API.
    4. Open Beauty Facts API.
    5. UPCitemdb live fetch (writes to local with db_source='upcitemdb').
    6. User submission name+brand only (extraction may have failed on the
       ingredient list but the product identity is still useful).
    7. UPCitemdb-cached local row (held from step 1; name+brand only).
    """
    # UPC-A (12-digit) is EAN-13 with the leading 0 stripped.
    # The OFF/OBF imports store everything as 13-digit EAN-13, so we try both.
    ean13 = barcode.zfill(13) if len(barcode) == 12 else None

    # --- Step 1: rich local DB ---
    local = await get_product_from_db(barcode) or (await get_product_from_db(ean13) if ean13 else None)
    if local and local.get("db_source") != "upcitemdb":
        resolved = local["db_resolved_count"]
        total = local["total_ingredients"]
        print(f"  [DB] Found '{local['name']}' locally. "
              f"Ingredients: {total} total, {resolved} matched in safety DB.")
        return local
    # If `local` is set here, it's a UPCitemdb-cached row — held for step 7.

    # --- Step 2: user submission with ingredients ---
    submission = await get_user_submission(barcode)
    if submission and submission.get("total_ingredients", 0) > 0:
        print(f"  [SUBMISSION] Using user submission for '{submission['name']}' "
              f"with {submission['total_ingredients']} ingredients (preferred over UPCitemdb name-only data)")
        return submission

    # --- Step 3: Open Food Facts ---
    print(f"  [API] Barcode {barcode} not in local DB, querying external APIs...")
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        try:
            food_url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
            food_response = await http_client.get(food_url)
            food_data = food_response.json()

            if food_data.get("status") == 1:
                product = food_data.get("product", {})
                ingredients_text = (
                    product.get("ingredients_text_en", "")
                    or product.get("ingredients_text", "")
                )
                name = (
                    product.get("product_name_en")
                    or product.get("product_name")
                    or ""
                )
                brand = product.get("brands", "")
                image_url = product.get("image_url") or product.get("image_front_url")

                if name or ingredients_text:
                    return {
                        "found":          True,
                        "source":         "off_api",
                        "product_type":   "food",
                        "name":           name,
                        "brand":          brand,
                        "ingredients":    ingredients_text,
                        "image_url":      image_url,
                        "nutriscore":     product.get("nutriscore_grade", ""),
                        "nova_group":     product.get("nova_group", ""),
                        "additives_tags": product.get("additives_tags", []),
                        "allergens":      product.get("allergens", ""),
                        "categories":     product.get("categories", ""),
                        "nutrition_grades": product.get("nutrition_grades", ""),
                    }
        except Exception as e:
            print(f"Food Facts API error: {e}")

        # --- Step 4: Open Beauty Facts ---
        try:
            beauty_url = f"https://world.openbeautyfacts.org/api/v0/product/{barcode}.json"
            beauty_response = await http_client.get(beauty_url)
            beauty_data = beauty_response.json()

            if beauty_data.get("status") == 1:
                product = beauty_data.get("product", {})
                ingredients_text = (
                    product.get("ingredients_text", "")
                    or product.get("ingredients_text_en", "")
                )
                name = (
                    product.get("product_name_en")
                    or product.get("product_name")
                    or ""
                )
                brand = product.get("brands", "")
                image_url = product.get("image_url") or product.get("image_front_url")

                if name or ingredients_text:
                    return {
                        "found":        True,
                        "source":       "obf_api",
                        "product_type": "cosmetic",
                        "name":         name,
                        "brand":        brand,
                        "ingredients":  ingredients_text,
                        "image_url":    image_url,
                        "categories":   product.get("categories", ""),
                    }
        except Exception as e:
            print(f"Beauty Facts API error: {e}")

    # --- Step 5: UPCitemdb live fetch ---
    upc_result = await _upcitemdb.fetch(barcode)
    if upc_result is None and ean13:
        upc_result = await _upcitemdb.fetch(ean13)
    if upc_result:
        print(f"  [UPCITEMDB] fallback fired for barcode {barcode}")
        await _upsert_upcitemdb_product(barcode, upc_result)
        print(f"  [UPCITEMDB] hit — '{upc_result['name']}' upserted to local DB")
        return upc_result
    print(f"  [UPCITEMDB] miss — proceeding to user_submissions / local cache fallbacks")

    # --- Step 6: user submission with name+brand only (no ingredients) ---
    # Already fetched in step 2; reuse it.
    if submission:
        print(f"  [SUBMISSION] Using user submission for '{submission['name']}' (name+brand only)")
        return submission

    # --- Step 7: UPCitemdb-cached local row (held from step 1) ---
    # Last resort before "not found" — name+brand only, no ingredients.
    if local:
        print(f"  [DB] Falling back to UPCitemdb-cached local row for '{local['name']}'")
        return local

    return {
        "found":        False,
        "source":       "none",
        "product_type": "unknown",
        "name":         "",
        "brand":        "",
        "ingredients":  "",
        "image_url":    None,
    }


async def analyze_product(barcode: str) -> SafetyReport:
    """
    Full analysis pipeline:
    1. Check safety_reports cache → return immediately if hit
    2. Multi-turn Claude loop: lookup_product tool → analysis
    3. Cache the result for 7 days
    """
    # --- Cache check ---
    cached = await get_cached_report(barcode)
    if cached:
        print(f"  [CACHE] Returning cached report for {barcode}")
        report = SafetyReport(**cached)
        report.recalls = await _attach_recalls(report)
        # Backfill category_slug on cache reads from pre-slug reports
        if not report.category_slug:
            from agents.category import derive_category_slug
            report.category_slug = derive_category_slug(
                report.product_name, report.product_type, None,
            )
        return report

    # --- Local fast path (no Claude) ---
    ean13 = barcode.zfill(13) if len(barcode) == 12 else None
    product_data = await get_product_from_db(barcode) or (await get_product_from_db(ean13) if ean13 else None)
    if product_data and product_data.get("db_source") != "upcitemdb":
        local_report = build_report(product_data, barcode)
        if local_report:
            print(f"  [LOCAL] Built report for '{local_report.product_name}' "
                  f"grade={local_report.grade} score={local_report.score}")
            local_report.recalls = await _attach_recalls(local_report)
            await cache_report(barcode, local_report.model_dump_json(), claude_used=False)
            return local_report
        print(f"  [LOCAL] Not enough resolved ingredients, falling back to Claude.")

    # Pre-flight lookup — if no source finds the product, skip Claude entirely
    preflight = await lookup_product(barcode)
    if not preflight.get("found"):
        print(f"  [LOOKUP] Product {barcode} not found in any source, skipping Claude.")
        return SafetyReport(
            product_name="Unknown Product",
            brand="Unknown",
            product_type="unknown",
            barcode=barcode,
            score=0,
            grade="D",
            summary="This product could not be found in any database.",
            ingredients_analysis=[],
            positive_points=[],
            negative_points=["Product not found in any database"],
            not_found=True,
        )

    # Seed the conversation with the preflight result so Claude skips a redundant lookup
    messages = [
        {
            "role": "user",
            "content": (
                f"Please analyze the safety of the product with barcode {barcode}. "
                "First look up the product information, then provide a comprehensive safety analysis. "
                "If the product data includes 'resolved_ingredients' with pre-computed safety levels "
                "from our EU ingredient database, use that data to anchor your analysis."
            )
        },
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "preflight_lookup", "name": "lookup_product", "input": {"barcode": barcode}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "preflight_lookup", "content": json.dumps(preflight)}],
        },
    ]

    # --- Phase 1: tool use loop ---
    while True:
        response = await client.messages.create(
            model=MODEL_LIGHT,
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=[LOOKUP_TOOL],
            messages=messages,
            thinking={"type": "adaptive", "display": "omitted"},
        )

        # Strip thinking blocks before storing: display="omitted" removes the
        # content but leaves the ThinkingBlock wrapper, which the API rejects
        # if passed back in a subsequent call (causes APIConnectionError).
        # Also strip redacted_thinking blocks — these slip through the type=="thinking"
        # check, and when re-serialized for Phase 2 they're missing the `data` field
        # the API expects, which makes the upstream silently close the connection
        # (httpx.RemoteProtocolError: Server disconnected without sending a response).
        # Also skip empty assistant messages (can occur when max_tokens is hit
        # during adaptive thinking, leaving no visible blocks) — the Anthropic
        # API rejects content:[] at the protocol level.
        content_for_history = [
            b for b in response.content
            if getattr(b, "type", None) not in ("thinking", "redacted_thinking")
        ]
        if content_for_history:
            messages.append({"role": "assistant", "content": content_for_history})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use" and block.name == "lookup_product":
                barcode_input = block.input.get("barcode", barcode)
                product_data = await lookup_product(barcode_input)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps(product_data),
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    # --- Phase 2: structured output ---
    # Serialize any SDK ContentBlock objects to plain dicts so messages.parse()
    # handles them consistently (SDK objects from Phase 1 can cause serialization
    # mismatch that results in RemoteProtocolError on certain payloads).
    def _to_dict(block) -> dict:
        if isinstance(block, dict):
            return block
        t = getattr(block, "type", None)
        if t == "text":
            return {"type": "text", "text": block.text}
        if t == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)}
        if t == "tool_result":
            return {"type": "tool_result", "tool_use_id": block.tool_use_id, "content": block.content}
        return {"type": t}

    serialized_messages = []
    for m in messages:
        content = m["content"]
        if isinstance(content, list):
            content = [_to_dict(b) for b in content]
        serialized_messages.append({"role": m["role"], "content": content})

    # Ensure user/assistant alternation before appending the Phase 2 prompt.
    # Phase 1 can legitimately end on a user message (the seeded preflight tool_result)
    # when adaptive thinking with display="omitted" produces a response made up
    # entirely of thinking blocks that the filter strips out. In that case Phase 2's
    # user prompt would create two consecutive user messages, which the Anthropic
    # API silently rejects with a TCP disconnect (httpx.RemoteProtocolError:
    # "Server disconnected without sending a response"). A minimal synthetic
    # assistant turn fixes the alternation without affecting the analysis.
    if serialized_messages and serialized_messages[-1]["role"] == "user":
        serialized_messages.append({
            "role": "assistant",
            "content": "Lookup complete. Ready to produce the structured safety report.",
        })

    serialized_messages.append({
        "role": "user",
        "content": (
            f"Based on the product information you retrieved, now provide a structured safety report. "
            f"The barcode is {barcode}. "
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
            '"safety_level": "safe|caution|avoid", "concern": "string|null", '
            '"concerns": ["string"], "sources": ["string"], "score_impact": int|null}], '
            '"positive_points": ["string"], "negative_points": ["string"], "not_found": false, '
            '"scoring_breakdown": {"base_score": 100, '
            '"penalties": [{"reason": "string", "points": negative_int}], '
            '"bonuses":   [{"reason": "string", "points": positive_int}], '
            '"eu_banned_floor_applied": false, "final_score": 0-100}}\n\n'
            "scoring_breakdown should aggregate per-ingredient deductions by category "
            "(e.g. \"Endocrine disruptors (3)\" with summed points, not 3 separate lines). "
            "Meta penalties (NOVA, Nutri-Score, EU-banned floor) get their own lines. "
            "Each bonus also gets a line. final_score must equal the top-level `score`.\n\n"
            "For each ingredient in ingredients_analysis:\n"
            "- `concern` is a short human-readable phrase (e.g. \"Endocrine disruptor — restricted in EU\").\n"
            "- `concerns` is a list of canonical tags from the Concern Tag Vocabulary "
            "(iarc_group_1/2a/2b, ghs_carcinogen_cat1/cat2, ghs_reproductive_toxin, ghs_mutagen, "
            "prop65_carcinogen, prop65_developmental_toxin, prop65_reproductive_toxin, "
            "allergen, endocrine_disruptor, paraben, sulfate, sls, sles, preservative, "
            "artificial_color, artificial_flavor, formaldehyde_releaser, microplastic, "
            "nitrite, high_sugar, high_sodium, trans_fat, neurotoxin). Empty list if safe.\n"
            "- `sources` is a list of authorities cited (e.g. [\"IARC\", \"Prop 65\", \"ECHA Annex VI\", "
            "\"EU CosIng\", \"EFSA\"]). Empty list if none.\n"
            "- `score_impact` is the negative integer this ingredient deducts from the score "
            "(e.g. -25 for an IARC Group 1 carcinogen). Use null for safe ingredients with no impact.\n"
            "When resolved_ingredients were pre-computed, copy their `concerns` and `sources` arrays "
            "rather than inventing new ones."
        )
    })

    # Phase 2 uses messages.stream() rather than messages.create(). Non-streaming Opus calls
    # whose combined input (system prompt + messages) is non-trivial get killed by an upstream
    # ~60s load-balancer timeout, surfacing as APIConnectionError. Bisected with
    # scratch/repro_phase2.py: with the full 33K-char system prompt, any non-tiny tool_result
    # payload triggers it; with a minimal system prompt the same payload succeeds. Streaming
    # keeps the connection alive via continuous token flow, so the LB never closes it. We still
    # validate the assembled response against the SafetyReport Pydantic model post-hoc.
    report: Optional[SafetyReport] = None
    text = ""
    try:
        text_chunks: list[str] = []
        async with client.messages.stream(
            model=MODEL_HEAVY,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=serialized_messages,
        ) as stream:
            async for chunk in stream.text_stream:
                text_chunks.append(chunk)
        text = "".join(text_chunks).strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        data = json.loads(text)
        report = SafetyReport(**data)
    except anthropic.APIError as e:
        print(f"  [CLAUDE] Phase 2 API failed: {type(e).__name__}: {e}")
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"  [CLAUDE] Phase 2 JSON/validation failed: {type(e).__name__}: {e}")
        # Log a preview so we can diagnose without re-running the call
        try:
            print(f"  [CLAUDE]   response preview: {text[:300]!r}")
        except Exception:
            pass

    if report is None:
        return SafetyReport(
            product_name="Unknown Product",
            brand="Unknown",
            product_type="unknown",
            barcode=barcode,
            score=0,
            grade="D",
            summary="Product could not be found or analyzed.",
            ingredients_analysis=[],
            positive_points=[],
            negative_points=["Product not found in any database"],
            not_found=True,
        )

    report.barcode = barcode
    report.recalls = await _attach_recalls(report)

    # Use-case slug — derived from name + product_type so cached and fresh
    # reports agree (deterministic heuristic). Phase 2 doesn't currently
    # emit a slug, so this is always populated here for the Claude path.
    if not report.category_slug:
        from agents.category import derive_category_slug
        report.category_slug = derive_category_slug(
            report.product_name, report.product_type, None,
        )

    # --- Cache the result ---
    try:
        await cache_report(barcode, report.model_dump_json(), claude_used=True)
    except Exception as e:
        print(f"  [CACHE] Failed to cache report for {barcode}: {e}")

    return report


async def analyze_submission_bg(submission_id: int, barcode: str) -> None:
    """
    Background task: run safety analysis for a user submission and
    write the result back to user_submissions.report.
    """
    print(f"  [BG] Starting analysis for submission {submission_id} barcode={barcode}")
    await set_submission_analyzing(submission_id)
    try:
        report = await analyze_product(barcode)
        await set_submission_complete(submission_id, report.model_dump_json())
        print(f"  [BG] Submission {submission_id} complete — grade={report.grade}")
    except Exception as e:
        print(f"  [BG] Submission {submission_id} failed: {e}")
        await set_submission_failed(submission_id, str(e))
