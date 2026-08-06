import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from data.models import User, WebAccount
from services import auth_service
from services.auth_service import authenticate, code_matches, generate_verification_code, hash_password, hash_verification_code, issue_token, normalize_email, register, resend_verification, verify_email, verify_password, verify_token


@pytest.fixture(autouse=True)
def auth_secret(monkeypatch):
    monkeypatch.setattr(auth_service.config, "APP_AUTH_SECRET", SimpleNamespace(get_secret_value=lambda: "secret"))


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)


def test_token_round_trip_and_expiry():
    token = issue_token(42, "test-secret", now=100)
    assert verify_token(token, "test-secret", now=100) == 42
    with pytest.raises(ValueError):
        verify_token(token, "test-secret", now=100 + 60 * 60 * 24 * 7)


def test_token_rejects_tampering():
    token = issue_token(42, "test-secret")
    body, signature = token.split(".", 1)
    with pytest.raises(ValueError):
        verify_token(("A" if body[0] != "A" else "B") + body[1:] + "." + signature, "test-secret")


def test_verification_code_is_six_digits_and_hashed(monkeypatch):
    monkeypatch.setattr(auth_service.config, "APP_AUTH_SECRET", type("Secret", (), {"get_secret_value": lambda self: "test-secret"})())
    code = generate_verification_code()
    encoded = hash_verification_code("user@example.com", code)
    assert len(code) == 6 and code.isdigit()
    assert code_matches("user@example.com", code, encoded)
    assert not code_matches("user@example.com", "000000", encoded)


@pytest.mark.parametrize("value", ["", "bad", "a@b", "a b@example.com"])
def test_email_normalization_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="invalid email"):
        normalize_email(value)


def test_email_normalization_is_case_insensitive():
    assert normalize_email("  User@Example.COM ") == "user@example.com"


def test_password_and_secret_error_boundaries(monkeypatch):
    with pytest.raises(ValueError, match="8 characters"):
        hash_password("short")
    assert not verify_password("password", "not-a-hash")
    monkeypatch.setattr(auth_service.config, "APP_AUTH_SECRET", None)
    with pytest.raises(RuntimeError, match="APP_AUTH_SECRET"):
        hash_verification_code("a@b.com", "123456")
    with pytest.raises(RuntimeError, match="APP_AUTH_SECRET"):
        issue_token(1, "")


@pytest.mark.parametrize("token", ["", "broken", "a.b.c", "!.!"])
def test_token_parser_rejects_malformed_tokens(token):
    with pytest.raises(ValueError, match="invalid token"):
        verify_token(token, "secret", now=100)


class Result:
    def __init__(self, value=None): self.value = value
    def scalar_one_or_none(self): return self.value


class Db:
    def __init__(self, account=None): self.account, self.added, self.flushed = account, [], 0
    async def execute(self, statement): return Result(self.account)
    def add(self, value): self.added.append(value)
    async def flush(self): self.flushed += 1


def account(email="user@example.com", verified=False):
    user = User(first_name="user", memory={}, tech_stack={})
    return WebAccount(id="id", email=email, password_hash=hash_password("password123"), user=user,
                      email_verified_at=datetime.now(timezone.utc) if verified else None,
                      verification_code_hash=auth_service.hash_verification_code(email, "123456"),
                      verification_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), verification_attempts=0)


@pytest.mark.asyncio
async def test_register_sends_code_and_creates_account(monkeypatch):
    monkeypatch.setattr(auth_service.config, "APP_AUTH_SECRET", SimpleNamespace(get_secret_value=lambda: "secret"))
    sent = []
    async def send(email, code): sent.append((email, code))
    monkeypatch.setattr(auth_service, "send_verification_code", send)
    db = Db()
    result = await register(db, "USER@example.com", "password123")
    assert result.email == "user@example.com" and db.added and db.flushed == 1
    assert sent[0][0] == "user@example.com" and len(sent[0][1]) == 6


@pytest.mark.asyncio
async def test_register_rejects_duplicate_account():
    with pytest.raises(ValueError, match="already exists"):
        await register(Db(account()), "user@example.com", "password123")


@pytest.mark.asyncio
async def test_verify_email_success_and_all_failure_branches(monkeypatch):
    monkeypatch.setattr(auth_service.config, "APP_AUTH_SECRET", SimpleNamespace(get_secret_value=lambda: "secret"))
    good = account()
    verified = account(verified=True)
    assert await verify_email(Db(verified), "user@example.com", "wrong") is verified
    with pytest.raises(ValueError, match="invalid verification code"):
        await verify_email(Db(None), "user@example.com", "123456")
    exhausted = account(); exhausted.verification_attempts = 5
    with pytest.raises(ValueError, match="too many"):
        await verify_email(Db(exhausted), "user@example.com", "123456")
    expired = account(); expired.verification_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(ValueError, match="expired"):
        await verify_email(Db(expired), "user@example.com", "123456")
    with pytest.raises(ValueError, match="invalid verification code"):
        await verify_email(Db(good), "user@example.com", "000000")
    assert good.verification_attempts == 1
    success = account(); result = await verify_email(Db(success), "user@example.com", "123456")
    assert result is success and success.email_verified_at and success.verification_code_hash is None and success.verification_expires_at is None


@pytest.mark.asyncio
async def test_resend_verification_resets_attempts_and_sends_new_code(monkeypatch):
    monkeypatch.setattr(auth_service.config, "APP_AUTH_SECRET", SimpleNamespace(get_secret_value=lambda: "secret"))
    sent = []
    async def send(email, code): sent.append((email, code))
    monkeypatch.setattr(auth_service, "send_verification_code", send)
    current = account(); current.verification_attempts = 4
    await resend_verification(Db(current), "user@example.com")
    assert current.verification_attempts == 0 and sent[0][0] == "user@example.com"
    await resend_verification(Db(None), "missing@example.com")
    await resend_verification(Db(account(verified=True)), "user@example.com")
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_authenticate_requires_verified_account_and_correct_password():
    verified = account(verified=True)
    assert await authenticate(Db(verified), "USER@example.com", "password123") is verified
    assert await authenticate(Db(verified), "user@example.com", "wrongpass") is None
    assert await authenticate(Db(account()), "user@example.com", "password123") is None
    assert await authenticate(Db(None), "missing@example.com", "password123") is None
