from fastapi import APIRouter

from app.api.routes import chat, profile, trips

api_router = APIRouter()
api_router.include_router(profile.router)
api_router.include_router(trips.router)
api_router.include_router(chat.router)
# Future feature routers get included here, e.g.:
# api_router.include_router(maps.router)
