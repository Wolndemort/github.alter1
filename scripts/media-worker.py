"""Standalone production consumer for Redis media jobs."""
import asyncio
import logging

from services.media_jobs import media_job_worker


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(media_job_worker())
