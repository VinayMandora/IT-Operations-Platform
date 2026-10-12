"""Argon2id password hashes, 8-hour signed browser sessions, CSRF and RBAC."""
import os
import secrets
from functools import lru_cache

from argon2 import PasswordHasher, exceptions as argon_errors
from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

COOKIE_NAME = 'nc_session'
SESSION_AGE_SECONDS = 8 * 60 * 60
password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=2)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(hash_value: str, password: str) -> bool:
    try:
        return password_hasher.verify(hash_value, password)
    except (argon_errors.VerifyMismatchError, argon_errors.VerificationError, argon_errors.InvalidHashError):
        return False


def signer() -> URLSafeTimedSerializer:
    # Obtain at runtime, not import time; makes tests and configuration predictable.
    key = os.getenv('APP_SECRET_KEY', '').strip()
    if len(key) < 40:
        raise RuntimeError('APP_SECRET_KEY not configured: run python -m scripts.configure_local')
    return URLSafeTimedSerializer(key, salt='northstar-helpdesk-session-v1')


def create_session(user: User) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(32)
    token = signer().dumps({'uid': user.id, 'csrf': csrf})
    return token, csrf


def cookie_secure() -> bool:
    return os.getenv('APP_COOKIE_SECURE', 'false').lower() == 'true'


def session_data(request: Request) -> dict | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        data = signer().loads(raw, max_age=SESSION_AGE_SECONDS)
        if not isinstance(data.get('uid'), int) or not isinstance(data.get('csrf'), str):
            return None
        return data
    except (BadSignature, SignatureExpired):
        return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    data = session_data(request)
    if not data:
        raise HTTPException(401, 'Login required')
    user = db.get(User, data['uid'])
    if not user or not user.is_active:
        raise HTTPException(401, 'Account is disabled or session invalid')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), data['csrf']):
            raise HTTPException(403, 'Missing or incorrect CSRF token')
    return user


def require_roles(*roles):
    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, 'Insufficient permissions')
        return user
    return check


def html_context(request: Request, db: Session) -> dict:
    data = session_data(request)
    user = db.get(User, data['uid']) if data else None
    if user and not user.is_active:
        user = None
    return {'user': user, 'csrf': data['csrf'] if user else ''}
