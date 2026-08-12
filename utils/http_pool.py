"""Lifecycle-managed async HTTP clients with connection reuse."""
from __future__ import annotations

import httpx

_clients: dict[float, httpx.AsyncClient] = {}
_factory = None


async def client(timeout: float) -> httpx.AsyncClient:
    global _factory
    factory = httpx.AsyncClient
    # Tests replace the factory with a fake client; never leak a fake client
    # between tests or reuse one created by a previous patched factory.
    if _factory is not factory:
        await close()
        _factory = factory
    key = float(timeout)
    if key not in _clients:
        _clients[key] = factory(timeout=timeout)
    return _clients[key]


async def close() -> None:
    clients = list(_clients.values())
    _clients.clear()
    for item in clients:
        close_method = getattr(item, "aclose", None)
        if close_method is not None:
            result = close_method()
            if result is not None:
                await result
