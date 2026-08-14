"""Durable, aggregate-only metrics snapshots for owner diagnostics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from data.database import async_session
from data.models import MetricSnapshot
from utils.metrics import latency_snapshot, snapshot


async def persist_metrics_snapshot() -> None:
    """Persist the current process metrics and retain a bounded history."""
    async with async_session() as session:
        session.add(MetricSnapshot(counters=snapshot(), latency=latency_snapshot()))
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        await session.execute(delete(MetricSnapshot).where(MetricSnapshot.created_at < cutoff))
        await session.commit()


async def recent_metrics_snapshots(limit: int = 48) -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(MetricSnapshot).order_by(MetricSnapshot.created_at.desc()).limit(max(1, min(limit, 168)))
        )
        return [
            {"created_at": item.created_at.isoformat() if item.created_at else None, "counters": item.counters or {}, "latency": item.latency or {}}
            for item in result.scalars().all()
        ]
