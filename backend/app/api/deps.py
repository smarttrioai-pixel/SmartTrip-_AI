from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.cloud.firestore import AsyncClient

from app.core.firebase import InvalidFirebaseTokenError, get_firestore_client, verify_firebase_token
from app.cognitive.adaptive_learning_engine import AdaptiveLearningEngine
from app.cognitive.context_engine import ContextEngine
from app.cognitive.explainability_engine import ExplainabilityEngine
from app.cognitive.memory_engine import MemoryEngine
from app.cognitive.planning_engine import PlanningEngine
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.risk_assessment_engine import RiskAssessmentEngine
from app.cognitive.user_profile_engine import UserProfileEngine
from app.models.user import User
from app.repositories.chat_repository import ChatRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.trip_repository import TripRepository
from app.repositories.user_repository import UserRepository
from app.services.chat_service import ChatService
from app.services.trip_service import TripPlannerService

# `auto_error=False` so a missing header falls through to our own 401 with a
# consistent shape, instead of FastAPI's default HTTPBearer error body.
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> AsyncClient:
    return get_firestore_client()


def get_user_repository(db: Annotated[AsyncClient, Depends(get_db)]) -> UserRepository:
    return UserRepository(db)


def get_trip_repository(db: Annotated[AsyncClient, Depends(get_db)]) -> TripRepository:
    return TripRepository(db)


def get_chat_repository(db: Annotated[AsyncClient, Depends(get_db)]) -> ChatRepository:
    return ChatRepository(db)


def get_memory_repository(db: Annotated[AsyncClient, Depends(get_db)]) -> MemoryRepository:
    return MemoryRepository(db)


def get_memory_engine(
    memory_repo: Annotated[MemoryRepository, Depends(get_memory_repository)],
    chat_repo: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> MemoryEngine:
    return MemoryEngine(memory_repo, chat_repo)


def get_user_profile_engine(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserProfileEngine:
    return UserProfileEngine(user_repo)


def get_context_engine() -> ContextEngine:
    return ContextEngine()


def get_recommendation_engine(
    context_engine: Annotated[ContextEngine, Depends(get_context_engine)],
) -> RecommendationEngine:
    return RecommendationEngine(context_engine)


def get_explainability_engine() -> ExplainabilityEngine:
    return ExplainabilityEngine()


def get_risk_assessment_engine() -> RiskAssessmentEngine:
    return RiskAssessmentEngine()


def get_adaptive_learning_engine(
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
) -> AdaptiveLearningEngine:
    return AdaptiveLearningEngine(memory_engine)


def get_planning_engine(
    user_profile_engine: Annotated[UserProfileEngine, Depends(get_user_profile_engine)],
    memory_engine: Annotated[MemoryEngine, Depends(get_memory_engine)],
    recommendation_engine: Annotated[RecommendationEngine, Depends(get_recommendation_engine)],
    explainability_engine: Annotated[ExplainabilityEngine, Depends(get_explainability_engine)],
    risk_engine: Annotated[RiskAssessmentEngine, Depends(get_risk_assessment_engine)],
    context_engine: Annotated[ContextEngine, Depends(get_context_engine)],
) -> PlanningEngine:
    return PlanningEngine(
        user_profile_engine, memory_engine, recommendation_engine, explainability_engine, risk_engine, context_engine
    )


def get_trip_planner_service(
    repo: Annotated[TripRepository, Depends(get_trip_repository)],
    planning_engine: Annotated[PlanningEngine, Depends(get_planning_engine)],
    adaptive_learning_engine: Annotated[AdaptiveLearningEngine, Depends(get_adaptive_learning_engine)],
) -> TripPlannerService:
    return TripPlannerService(repo, planning_engine, adaptive_learning_engine)


def get_chat_service(repo: Annotated[ChatRepository, Depends(get_chat_repository)]) -> ChatService:
    return ChatService(repo)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    """
    Verifies the Firebase ID token on every protected request and resolves
    the Firestore profile document for that uid.

    If no profile doc exists yet (e.g. the client skipped the explicit
    `POST /profile/sync` call right after signup, or this is a Google-login
    user's very first authenticated request), it's lazily created here from
    the token's claims so no request ever 404s on a "missing profile".
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exception

    try:
        claims = await verify_firebase_token(credentials.credentials)
    except InvalidFirebaseTokenError as exc:
        raise credentials_exception from exc

    uid = claims["uid"]
    user = await user_repository.get_by_id(uid)
    if user is None:
        email = claims.get("email", "")
        user = await user_repository.create(
            uid=uid,
            email=email,
            full_name=claims.get("name") or (email.split("@")[0] if email else "Traveler"),
            is_email_verified=claims.get("email_verified", False),
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
