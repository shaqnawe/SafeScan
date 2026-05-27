from pydantic import BaseModel
from typing import Optional


class IngredientAnalysis(BaseModel):
    name: str
    safety_level: str  # "safe", "caution", "avoid"
    concern: Optional[str] = None       # free-text human-readable explanation
    concerns: list[str] = []            # structured tags from Concern Tag Vocabulary
    sources: list[str] = []             # e.g. ["IARC", "Prop 65", "ECHA", "EU CosIng"]
    score_impact: Optional[int] = None  # per-ingredient score delta (e.g. -25)


class Alternative(BaseModel):
    barcode:      str
    product_name: str
    brand:        Optional[str] = None
    image_url:    Optional[str] = None
    product_type: str
    grade:        str  # "A", "B", "C", "D"
    score:        int


class RecallAlert(BaseModel):
    title: str
    description: Optional[str] = None
    risk_level: Optional[str] = None   # "serious", "high", "medium", "low"
    category: Optional[str] = None
    link: Optional[str] = None
    published_at: Optional[str] = None  # ISO string


class SafetyReport(BaseModel):
    product_name: str
    brand: str
    product_type: str  # "food" or "cosmetic"
    barcode: str
    image_url: Optional[str] = None
    score: int  # 0-100
    grade: str  # A, B, C, D — no E grade per scoring_rubric.md
    summary: str
    ingredients_analysis: list[IngredientAnalysis]
    positive_points: list[str]
    negative_points: list[str]
    not_found: bool = False
    recalls: list[RecallAlert] = []
    alternatives: list[Alternative] = []
    # Use-case slug ("hand_soap", "body_lotion", "soda", ...). Used to match
    # alternatives by actual product use case rather than broad category
    # parents like "Health & Beauty". Null when no confident classification.
    category_slug: Optional[str] = None


class ScanRequest(BaseModel):
    barcode: str


class SearchResult(BaseModel):
    barcode:      str
    name:         str
    brand:        Optional[str] = None
    image_url:    Optional[str] = None
    product_type: str
