"""Standalone production consumer for Redis media jobs."""
import asyncio
import logging
import sys
from pathlib import Path

# When executed as ``python scripts/media-worker.py``, Python puts only
# ``scripts/`` on sys.path. Add the project root so application packages load.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.media_jobs import media_job_worker


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(media_job_worker())
