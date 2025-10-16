from pydantic import BaseModel
from typing import List, Optional

class DetectionOut(BaseModel):
    detector: str
    value: str
    extra: Optional[str] = None

class RiskOut(BaseModel):
    score: float
    band: str
    why: List[str]

class RecommendationOut(BaseModel):
    text: str

class PostOut(BaseModel):
    id: int
    caption: str
    image_path: Optional[str]
    detections: List[DetectionOut]
    risk: RiskOut
    recommendations: List[RecommendationOut]
    class Config:
        from_attributes = True
