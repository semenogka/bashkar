"""Хеши паролей через bcrypt.

passlib на связке с bcrypt 4.1+ падает при инициализации, поэтому
хешируем напрямую. Формат $2b$ совместим со старыми хешами passlib.
"""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False
