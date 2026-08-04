import logging
import time


def timer(name: str):
    started = time.perf_counter()

    def finish(**fields):
        elapsed = time.perf_counter() - started
        details = " ".join(f"{key}={value}" for key, value in fields.items())
        logging.info("metric=%s duration=%.2fs %s", name, elapsed, details)

    return finish
