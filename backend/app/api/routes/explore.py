"""
Explore & AR API Router for SmartTrip AI.
Endpoints for landmark image recognition (Gemini Vision), Wikipedia background enrichment,
AR overlay annotations, and historical audio narration scripts.

Phase 3B: the Vision fallback (hardcoded "Eiffel Tower") and the Q&A
endpoint's canned response — both present since Phase 3A only added auth
here — are now replaced with real Gemini calls (see gemini_vision_service.py
and this file's /qa endpoint below).
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.gemini import generate_text
from app.integrations.gemini_vision_service import GeminiVisionService, get_gemini_vision_service
from app.integrations.wikipedia_service import WikipediaService, get_wikipedia_service

router = APIRouter(prefix="/explore", tags=["Explore & AR"])

class LandmarkAnalysisRequest(BaseModel):
    prompt_hint: str = ""
    image_b64: str | None = None

class LandmarkQARequest(BaseModel):
    landmark_name: str
    question: str

QA_SYSTEM_PROMPT = """You are a knowledgeable tour guide. Answer the visitor's \
question about the given landmark concisely and accurately, in 2-3 sentences. \
If you don't have reliable information to answer, say so rather than guessing."""

@router.post("/analyze-landmark", summary="Analyze landmark image using Gemini Vision")
async def analyze_landmark(
    request: LandmarkAnalysisRequest,
    current_user: CurrentUser,
    vision_service: GeminiVisionService = Depends(get_gemini_vision_service),
) -> dict[str, Any]:
    if not request.image_b64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="image_b64 is required")
    try:
        return await vision_service.analyze_landmark_image(
            image_b64=request.image_b64, prompt_hint=request.prompt_hint
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

@router.get("/landmark-info", summary="Fetch detailed Wikipedia landmark information")
async def get_landmark_info(
    name: str,
    current_user: CurrentUser,
    wiki_service: WikipediaService = Depends(get_wikipedia_service),
) -> dict[str, Any]:
    result = await wiki_service.get_landmark_info(name)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No Wikipedia info found for '{name}'")
    return result

@router.post("/qa", summary="Ask a question about a landmark")
async def landmark_qa(request: LandmarkQARequest, current_user: CurrentUser) -> dict[str, str]:
    try:
        answer = await generate_text(
            system_prompt=QA_SYSTEM_PROMPT,
            history=[],
            user_prompt=f"Landmark: {request.landmark_name}\nQuestion: {request.question}",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return {"landmark_name": request.landmark_name, "question": request.question, "answer": answer}
