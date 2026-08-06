import time

import pytest

from services.auth_service import hash_password, issue_token, verify_password, verify_token


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
    with pytest.raises(ValueError):
        verify_token(token[:-1] + ("a" if token[-1] != "a" else "b"), "test-secret")
