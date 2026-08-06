"""Application authentication primitives, independent from Telegram."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import User, WebAccount
from config import config
from services.email_service import send_verification_code

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
VERIFICATION_TTL = timedelta(minutes=10)
MAX_VERIFICATION_ATTEMPTS = 5


def normalize_email(email: str) -> str:
    value = email.strip().casefold()
    if not EMAIL_RE.fullmatch(value):
        raise ValueError("invalid email")
    return value


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 8:
        raise ValueError("password must contain at least 8 characters")
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_raw, digest_raw = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_raw.encode())
        expected = base64.urlsafe_b64decode(digest_raw.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def generate_verification_code() -> str:
    return f"{int.from_bytes(os.urandom(4), 'big') % 1_000_000:06d}"


def hash_verification_code(email: str, code: str) -> str:
    return hmac.new(_secret(config.APP_AUTH_SECRET.get_secret_value() if config.APP_AUTH_SECRET else ""), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def code_matches(email: str, code: str, encoded: str) -> bool:
    return hmac.compare_digest(hash_verification_code(email, code), encoded)


def _secret(secret: str) -> bytes:
    if not secret:
        raise RuntimeError("APP_AUTH_SECRET is not configured")
    return secret.encode()


def issue_token(user_id: int, secret: str, *, now: int | None = None) -> str:
    payload = {"sub": str(user_id), "exp": (now or int(time.time())) + TOKEN_TTL_SECONDS}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(_secret(secret), body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def verify_token(token: str, secret: str, *, now: int | None = None) -> int:
    try:
        body, encoded_signature = token.split(".", 1)
        actual = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
        expected = hmac.new(_secret(secret), body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(actual, expected):
            raise ValueError("invalid token")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) <= (now or int(time.time())):
            raise ValueError("expired token")
        return int(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid token") from exc


async def register(session: AsyncSession, email: str, password: str) -> WebAccount:
    email = normalize_email(email)
    existing = (await session.execute(select(WebAccount).where(WebAccount.email == email))).scalar_one_or_none()
    if existing:
        raise ValueError("account already exists")
    user = User(first_name=email.split("@", 1)[0][:64], memory={}, tech_stack={})
    code = generate_verification_code()
    account = WebAccount(
        id=str(uuid.uuid4()), email=email, password_hash=hash_password(password), user=user,
        verification_code_hash=hash_verification_code(email, code),
        verification_expires_at=datetime.now(timezone.utc) + VERIFICATION_TTL,
        verification_attempts=0,
    )
    session.add(account)
    await session.flush()
    await send_verification_code(email, code)
    return account


async def verify_email(session: AsyncSession, email: str, code: str) -> WebAccount:
    email = normalize_email(email)
    account = (await session.execute(select(WebAccount).where(WebAccount.email == email))).scalar_one_or_none()
    if account is None:
        raise ValueError("invalid verification code")
    if account.email_verified_at is not None:
        return account
    if account.verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
        raise ValueError("too many verification attempts")
    account.verification_attempts += 1
    if not account.verification_expires_at or account.verification_expires_at <= datetime.now(timezone.utc):
        raise ValueError("verification code expired")
    if not account.verification_code_hash or not code_matches(email, code.strip(), account.verification_code_hash):
        raise ValueError("invalid verification code")
    account.email_verified_at = datetime.now(timezone.utc)
    account.verification_code_hash = None
    account.verification_expires_at = None
    await session.flush()
    return account


async def resend_verification(session: AsyncSession, email: str) -> None:
    email = normalize_email(email)
    account = (await session.execute(select(WebAccount).where(WebAccount.email == email))).scalar_one_or_none()
    if account is None or account.email_verified_at is not None:
        return
    code = generate_verification_code()
    account.verification_code_hash = hash_verification_code(email, code)
    account.verification_expires_at = datetime.now(timezone.utc) + VERIFICATION_TTL
    account.verification_attempts = 0
    await send_verification_code(email, code)
    await session.flush()


async def authenticate(session: AsyncSession, email: str, password: str) -> WebAccount | None:
    email = normalize_email(email)
    account = (await session.execute(select(WebAccount).where(WebAccount.email == email))).scalar_one_or_none()
    return account if account and account.email_verified_at and verify_password(password, account.password_hash) else None
