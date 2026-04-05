from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from models import ScanRequest, SafetyReport
from agents.scanner import analyze_product, analyze_submission_bg
from agents.image_agent import process_product_photos, SubmissionResult
from db.connection import get_pool, close_pool
from db.recall_store import ensure_recalls_table, fetch_and_store_recalls
from db.queries import list_user_submissions, get_submission


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm up the connection pool so the first request isn't slow
    await get_pool()
    print("Database pool initialized.")
    await ensure_recalls_table()
    print("Recalls table ready.")
    yield
    # Shutdown: release all connections cleanly
    await close_pool()
    print("Database pool closed.")


app = FastAPI(title="Barcode Safety Scanner API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/recalls/refresh")
async def refresh_recalls():
    """Manually trigger a recall feed refresh."""
    try:
        stats = await fetch_and_store_recalls()
        return {"status": "ok", **stats}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch recall feed: {e}")


@app.get("/api/submissions")
async def get_submissions():
    """List all user submissions ordered by newest first."""
    rows = await list_user_submissions()
    result = []
    for r in rows:
        import json
        extracted = r["extracted_data"]
        if isinstance(extracted, str):
            extracted = json.loads(extracted)
        product = extracted.get("product", {}) if extracted else {}
        report_raw = r["report"]
        report = None
        if report_raw:
            report = json.loads(report_raw) if isinstance(report_raw, str) else report_raw
        result.append({
            "id":           r["id"],
            "barcode":      r["barcode"],
            "status":       r["status"],
            "product_name": product.get("product_name"),
            "brand":        product.get("brand"),
            "submitted_at": r["created_at"].isoformat() if r["created_at"] else None,
            "analyzed_at":  r["analyzed_at"].isoformat() if r["analyzed_at"] else None,
            "error":        r["error"],
            "report":       report,
        })
    return result


@app.post("/api/submit-product", response_model=SubmissionResult)
async def submit_product(
    background_tasks:    BackgroundTasks,
    product_image:       Optional[UploadFile] = File(None),
    ingredients_image:   Optional[UploadFile] = File(None),
    barcode:             Optional[str]        = Form(None),
    product_type:        Optional[str]        = Form("unknown"),
    manual_ingredients:  Optional[str]        = Form(None),
) -> SubmissionResult:
    """
    Accept product and/or ingredient photos and extract structured data.
    At least one image or a barcode must be provided.
    """
    if not product_image and not ingredients_image and not barcode and not manual_ingredients:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one image, a barcode, or a manual ingredient list."
        )

    prod_bytes  = await product_image.read()     if product_image     else None
    ingr_bytes  = await ingredients_image.read() if ingredients_image else None
    prod_mime   = product_image.content_type     if product_image     else "image/jpeg"
    ingr_mime   = ingredients_image.content_type if ingredients_image else "image/jpeg"

    try:
        result = await process_product_photos(
            product_image=prod_bytes,
            product_media_type=prod_mime or "image/jpeg",
            ingredients_image=ingr_bytes,
            ingredients_media_type=ingr_mime or "image/jpeg",
            barcode_hint=barcode,
            product_type_hint=product_type or "unknown",
            manual_ingredients_text=manual_ingredients or None,
        )

        # Auto-trigger background safety analysis if we have a barcode
        final_barcode = result.product.barcode or (barcode.strip() if barcode else None)
        if final_barcode and result.submission_id:
            background_tasks.add_task(analyze_submission_bg, result.submission_id, final_barcode)

        return result
    except Exception as e:
        print(f"Error processing product photos: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process images: {str(e)}")


@app.post("/api/scan", response_model=SafetyReport)
async def scan_product(request: ScanRequest) -> SafetyReport:
    if not request.barcode or not request.barcode.strip():
        raise HTTPException(status_code=400, detail="Barcode is required")

    barcode = request.barcode.strip()

    try:
        report = await analyze_product(barcode)
        return report
    except Exception as e:
        print(f"Error analyzing product {barcode}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to analyze product: {str(e)}"
        )
