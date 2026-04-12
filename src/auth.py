"""
auth.py — JWT authentication for NetAI Agent
"""
import os
import secrets
import datetime
from typing import Optional

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from src.db import get_conn

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
ALGORITHM  = "HS256"
EXPIRE_HOURS = 8


# ── Password helpers ───────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT helpers ────────────────────────────────────────────────────────────────
def create_access_token(username: str, user_id: int, role: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=EXPIRE_HOURS)
    payload = {
        "sub":     username,
        "user_id": user_id,
        "role":    role,
        "exp":     expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return {}


# ── FastAPI dependencies ───────────────────────────────────────────────────────
def _extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("netai_token")


def get_current_user(request: Request) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired token")
    return payload


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin access required")
    return user


# ── DB helpers ─────────────────────────────────────────────────────────────────
def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Return user dict if credentials valid, else None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, password_hash, role FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def change_user_password(username: str, new_password: str) -> bool:
    hashed = hash_password(new_password)
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                 (hashed, username))
    conn.commit()
    conn.close()
    return True
