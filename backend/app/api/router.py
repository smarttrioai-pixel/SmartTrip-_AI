from fastapi import APIRouter

from app.api.routes import chat, memory, profile, trips

api_router = APIRouter()
api_router.include_router(profile.router)
api_router.include_router(trips.router)
api_router.include_router(chat.router)
api_router.include_router(memory.router)
# Future feature routers get included here, e.g.:
# api_router.include_router(maps.router)
