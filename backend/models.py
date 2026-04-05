from pydantic import BaseModel
from typing import Optional


class IngredientAnalysis(BaseModel):
    name: str
    safety_level: str  # "safe", "caution", "avoid"
    concern: Optional[str] = None


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
    grade: str  # A, B, C, D, E
    summary: str
    ingredients_analysis: list[IngredientAnalysis]
    positive_points: list[str]
    negative_points: list[str]
    not_found: bool = False
    recalls: list[RecallAlert] = []


class ScanRequest(BaseModel):
    barcode: str
