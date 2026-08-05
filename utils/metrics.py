import logging
import threading
import time


_lock = threading.Lock()
_counters: dict[str, int] = {}


def increment(name: str, amount: int = 1, **fields) -> int:
    """Increment an in-process counter and emit a grep-friendly log line."""
    with _lock:
        _counters[name] = _counters.get(name, 0) + amount
        value = _counters[name]
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    logging.info("metric_count=%s value=%d %s", name, value, details)
    return value


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)


def reset() -> None:
    with _lock:
        _counters.clear()


def timer(name: str):
    started = time.perf_counter()

    def finish(**fields):
        elapsed = time.perf_counter() - started
        details = " ".join(f"{key}={value}" for key, value in fields.items())
        logging.info("metric=%s duration=%.2fs %s", name, elapsed, details)
        increment(f"{name}.completed", **fields)

    return finish
