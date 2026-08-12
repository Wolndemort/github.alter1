"""SSRF-safe URL policy for user-controlled fetches."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


def validate_public_url(value: str, *, schemes: set[str] | None = None) -> str:
    parsed = urlsplit(str(value or "").strip())
    allowed = schemes or {"http", "https"}
    if parsed.scheme.casefold() not in allowed or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only public http(s) URLs are allowed")
    host = parsed.hostname.casefold().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("private host is not allowed")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        for item in addresses:
            address = ipaddress.ip_address(item[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                raise ValueError("private host is not allowed")
    except socket.gaierror:
        raise ValueError("host cannot be resolved")
    return parsed.geturl()
