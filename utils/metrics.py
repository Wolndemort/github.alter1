import logging
import threading
import time


_lock = threading.Lock()
_counters: dict[str, int] = {}
_samples: dict[str, list[float]] = {}
_MAX_SAMPLES = 2000


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
        _samples.clear()


def observe(name: str, duration_ms: float, **fields) -> None:
    """Keep a bounded in-process latency sample for p50/p95 diagnostics."""
    value = max(0.0, float(duration_ms))
    with _lock:
        values = _samples.setdefault(name, [])
        values.append(value)
        del values[:-_MAX_SAMPLES]
    logging.info("metric_latency=%s duration_ms=%.1f %s", name, value, " ".join(f"{k}={v}" for k, v in fields.items()))


def latency_snapshot() -> dict[str, dict[str, float | int]]:
    with _lock:
        result = {}
        for name, values in _samples.items():
            if not values:
                continue
            ordered = sorted(values)
            result[name] = {
                "count": len(ordered),
                "p50_ms": round(ordered[(len(ordered) - 1) * 50 // 100], 1),
                "p95_ms": round(ordered[(len(ordered) - 1) * 95 // 100], 1),
                "last_ms": round(ordered[-1], 1),
            }
        return result


def timer(name: str):
    started = time.perf_counter()

    def finish(**fields):
        elapsed = time.perf_counter() - started
        details = " ".join(f"{key}={value}" for key, value in fields.items())
        logging.info("metric=%s duration=%.2fs %s", name, elapsed, details)
        increment(f"{name}.completed", **fields)

    return finish
