"""Аутентификация: JWT (register / login / me) + зависимости для ролей."""
from __future__ import annotations

import time
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import get_session
from app.models import LangPair, User
from app.services.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

bearer_scheme = HTTPBearer(auto_error=False)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "student"
    school_id: Optional[int] = None
    class_id: Optional[int] = None
    lang_pair: str = "ba-ru"


class AuthLogin(BaseModel):
    username: str
    password: str


def create_access_token(subject_id: int, role: str, expires_delta: Optional[int] = None) -> str:
    now = int(time.time())
    payload = {
        "sub": str(subject_id),
        "role": role,
        "iat": now,
        "exp": now + (expires_delta if expires_delta is not None else settings.access_token_expire_minutes * 60),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(*roles: str):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


@router.post("/register", response_model=TokenOut)
async def register(payload: AuthRegister, session: AsyncSession = Depends(get_session)) -> TokenOut:
    from datetime import datetime

    user = (
        await session.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if user is None:
        pair = (
            await session.execute(select(LangPair).where(LangPair.code == payload.lang_pair))
        ).scalar_one_or_none()
        user = User(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            role=payload.role or "student",
            school_id=payload.school_id,
            class_id=payload.class_id,
            lang_pair_id=pair.id if pair else None,
            xp=0,
            level=1,
            hearts=5,
            hearts_updated_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        session.add(user)
        await session.flush()
    user.password_hash = hash_password(payload.password)
    user.email = payload.email
    user.role = payload.role or "student"
    user.school_id = payload.school_id
    user.class_id = payload.class_id
    if payload.lang_pair:
        pair = (
            await session.execute(select(LangPair).where(LangPair.code == payload.lang_pair))
        ).scalar_one_or_none()
        user.lang_pair_id = pair.id if pair else None
    await session.commit()
    token = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, token_type="bearer")


@router.post("/login", response_model=TokenOut)
async def login(payload: AuthLogin, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = (
        await session.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, token_type="bearer")


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    pair_code = None
    if user.lang_pair_id:
        pair = await session.get(LangPair, user.lang_pair_id)
        pair_code = pair.code if pair else None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "school_id": user.school_id,
        "class_id": user.class_id,
        "lang_pair": pair_code,
        "points": user.points,
        "level": user.level or 1,
        "created_at": user.created_at,
    }
