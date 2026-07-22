from fastapi import APIRouter

from app.api.routes import (
    analytics,
    chat,
    diary,
    explore,
    memory,
    navigation,
    profile,
    trips,
)

api_router = APIRouter()
api_router.include_router(profile.router)
api_router.include_router(trips.router)
api_router.include_router(chat.router)
api_router.include_router(memory.router)
api_router.include_router(navigation.router)
api_router.include_router(explore.router)
api_router.include_router(diary.router)
api_router.include_router(analytics.router)
