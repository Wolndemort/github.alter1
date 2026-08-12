import pytest

from utils.url_safety import validate_public_url


def test_url_safety_rejects_private_and_credential_urls(monkeypatch):
    with pytest.raises(ValueError): validate_public_url("http://localhost/admin")
    with pytest.raises(ValueError): validate_public_url("http://user:pass@example.com")


def test_url_safety_accepts_public_host(monkeypatch):
    monkeypatch.setattr("utils.url_safety.socket.getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))])
    assert validate_public_url("https://example.com/path") == "https://example.com/path"
