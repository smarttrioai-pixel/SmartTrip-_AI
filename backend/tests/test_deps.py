"""
Run with: pytest tests/test_deps.py

Verifies the core of the Phase 0 migration: get_current_user trusts a
verified Firebase ID token's claims and lazily creates the Firestore
profile doc on first sight of a uid, without ever touching a database.
"""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import app.api.deps as deps
from app.core.firebase import InvalidFirebaseTokenError

pytestmark = pytest.mark.asyncio


class FakeUser:
    def __init__(self, id, email, full_name, is_email_verified=False):
        self.id = id
        self.email = email
        self.full_name = full_name
        self.is_email_verified = is_email_verified


class FakeUserRepository:
    def __init__(self):
        self.created_with: dict | None = None
        self._users: dict[str, FakeUser] = {}

    async def get_by_id(self, user_id):
        return self._users.get(user_id)

    async def create(self, *, uid, email, full_name, is_email_verified=False):
        self.created_with = {"uid": uid, "email": email, "full_name": full_name}
        user = FakeUser(uid, email, full_name, is_email_verified)
        self._users[uid] = user
        return user


async def test_get_current_user_rejects_missing_credentials():
    repo = FakeUserRepository()
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(credentials=None, user_repository=repo)
    assert exc_info.value.status_code == 401


async def test_get_current_user_rejects_invalid_token(monkeypatch):
    async def fake_verify(token):
        raise InvalidFirebaseTokenError("bad token")

    monkeypatch.setattr(deps, "verify_firebase_token", fake_verify)
    repo = FakeUserRepository()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="garbage")

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(credentials=creds, user_repository=repo)
    assert exc_info.value.status_code == 401


async def test_get_current_user_lazily_creates_profile_on_first_login(monkeypatch):
    async def fake_verify(token):
        return {"uid": "uid-123", "email": "alex@example.com", "name": "Alex Rivera", "email_verified": True}

    monkeypatch.setattr(deps, "verify_firebase_token", fake_verify)
    repo = FakeUserRepository()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    user = await deps.get_current_user(credentials=creds, user_repository=repo)

    assert user.id == "uid-123"
    assert repo.created_with == {"uid": "uid-123", "email": "alex@example.com", "full_name": "Alex Rivera"}


async def test_get_current_user_reuses_existing_profile(monkeypatch):
    async def fake_verify(token):
        return {"uid": "uid-123", "email": "alex@example.com", "name": "Alex Rivera"}

    monkeypatch.setattr(deps, "verify_firebase_token", fake_verify)
    repo = FakeUserRepository()
    repo._users["uid-123"] = FakeUser("uid-123", "alex@example.com", "Alex Rivera")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    await deps.get_current_user(credentials=creds, user_repository=repo)

    assert repo.created_with is None  # existing profile was reused, not recreated
