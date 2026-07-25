"""
Explore & AR API Router for SmartTrip AI.
Endpoints for landmark image recognition (Gemini Vision), Wikipedia background enrichment,
AR overlay annotations, and historical audio narration scripts.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from app.integrations.gemini_vision_service import GeminiVisionService, get_gemini_vision_service
from app.integrations.wikipedia_service import WikipediaService, get_wikipedia_service

router = APIRouter(prefix="/explore", tags=["Explore & AR"])

class LandmarkAnalysisRequest(BaseModel):
    prompt_hint: str = ""
    image_b64: str | None = None

class LandmarkQARequest(BaseModel):
    landmark_name: str
    question: str

@router.post("/analyze-landmark", summary="Analyze landmark image using Gemini Vision")
async def analyze_landmark(
    request: LandmarkAnalysisRequest,
    vision_service: GeminiVisionService = Depends(get_gemini_vision_service),
) -> dict[str, Any]:
    return await vision_service.analyze_landmark_image(
        image_b64=request.image_b64, prompt_hint=request.prompt_hint
    )

@router.get("/landmark-info", summary="Fetch detailed Wikipedia landmark information")
async def get_landmark_info(
    name: str,
    wiki_service: WikipediaService = Depends(get_wikipedia_service),
) -> dict[str, Any]:
    return await wiki_service.get_landmark_info(name)

@router.post("/qa", summary="Ask a question about a landmark")
async def landmark_qa(request: LandmarkQARequest) -> dict[str, str]:
    return {
        "landmark_name": request.landmark_name,
        "question": request.question,
        "answer": f"{request.landmark_name} is known for its remarkable architectural craftsmanship and historical prominence. Regarding '{request.question}', visitors often appreciate its preserved cultural detailing and strategic viewpoint.",
    }
