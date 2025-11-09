from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.types.activity import Preferences, Context, ActivityItem


class RecommendRequest(BaseModel):
    """추천 요청 스키마"""
    preferences: Preferences
    context_override: Optional[Dict[str, Any]] = None


class RecommendResponse(BaseModel):
    """추천 응답 스키마"""
    session_id: str
    context: Context
    items: List[ActivityItem]
    meta: Dict[str, Any]  # latencyMs, sourceStats, fallbackUsed


class HealthResponse(BaseModel):
    """헬스체크 응답 스키마"""
    status: str
    time: str
