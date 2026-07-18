"""
Firebase Admin SDK bootstrap. Initialized once per process; the Firestore
client is a thin async wrapper (`google.cloud.firestore.AsyncClient` via
firebase_admin's `firestore_async` module) so repository methods can be
awaited like the rest of the async stack.
"""
import asyncio
from functools import lru_cache

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import firestore_async

from app.core.config import get_settings

settings = get_settings()


class InvalidFirebaseTokenError(Exception):
    """Raised when a Firebase ID token is missing, malformed, or expired."""


import json

@lru_cache
def get_firebase_app() -> firebase_admin.App:
    if firebase_admin._apps:
        return firebase_admin.get_app()

    if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        service_account = settings.FIREBASE_SERVICE_ACCOUNT_JSON.strip()

        # Environment variable contains JSON
        if service_account.startswith("{"):
            cred = credentials.Certificate(json.loads(service_account))
        else:
            # Environment variable contains a file path
            cred = credentials.Certificate(service_account)

        return firebase_admin.initialize_app(
            cred,
            {"projectId": settings.FIREBASE_PROJECT_ID},
        )

    # Fallback to Application Default Credentials
    return firebase_admin.initialize_app(
        options={"projectId": settings.FIREBASE_PROJECT_ID}
    )

@lru_cache
def get_firestore_client():
    get_firebase_app()
    return firestore_async.client()


async def verify_firebase_token(id_token: str) -> dict:
    """
    Verify a Firebase Authentication ID token and return its decoded claims
    (`uid`, `email`, `name`, `email_verified`, ...).

    `verify_id_token` is a synchronous, network-backed call (it fetches and
    caches Google's public signing certs) — run it off the event loop so it
    doesn't block other requests.
    """
    get_firebase_app()
    try:
        return await asyncio.to_thread(firebase_auth.verify_id_token, id_token)
    except Exception as exc:  # firebase_admin raises several distinct error types
        raise InvalidFirebaseTokenError("Invalid or expired Firebase ID token") from exc
