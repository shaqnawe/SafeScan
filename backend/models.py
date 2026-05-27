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


class ScoreLineItem(BaseModel):
    reason: str
    points: int  # negative for penalties, positive for bonuses


class ScoringBreakdown(BaseModel):
    base_score:              int = 100
    penalties:               list[ScoreLineItem] = []
    bonuses:                 list[ScoreLineItem] = []
    eu_banned_floor_applied: bool = False
    final_score:             int   # base + sum, post-clamp


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
    # Nutrition lens (food only). Sourced from products.nutriscore / nova_group.
    # nutriscore: single letter "A"–"E" (best → worst).
    # nova_group:  1=unprocessed, 2=culinary ingredient, 3=processed,
    #              4=ultra-processed.
    nutriscore: Optional[str] = None
    nova_group: Optional[int] = None
    # Vegan classification from ingredient-keyword scan (food only).
    # True = confident vegan, False = confident not vegan, None = uncertain
    # (e.g. lecithin / mono-and-diglycerides without a plant source qualifier).
    is_vegan:   Optional[bool] = None
    # Per-line explanation of how the score was reached. Populated by
    # local_analyzer or by Claude's Phase 2 emit. Null on legacy cached
    # reports — UI hides the breakdown panel in that case.
    scoring_breakdown: Optional[ScoringBreakdown] = None


class ScanRequest(BaseModel):
    barcode: str


class SearchResult(BaseModel):
    barcode:      str
    name:         str
    brand:        Optional[str] = None
    image_url:    Optional[str] = None
    product_type: str
