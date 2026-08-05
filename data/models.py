from datetime import datetime
from typing import List, Optional
from sqlalchemy import BigInteger, String, func, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from data.database import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(64))

    memory: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    tech_stack: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    pending_reminder: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    checkins_enabled: Mapped[bool] = mapped_column(default=True, server_default='true')
    last_checkin_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    payment_method_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(default=False, server_default='false')
    next_charge_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sessions: Mapped[List["Session"]] = relationship(back_populates='user', cascade='all, delete-orphan')
    important_events: Mapped[List["ImportantEvent"]] = relationship(
        back_populates='user', cascade='all, delete-orphan'
    )


class Session(Base):
    __tablename__ = 'session'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    summary: Mapped[Optional[str]] = mapped_column(String)
    raw_messages: Mapped[list] = mapped_column(JSONB, default=list, server_default='[]')
    is_processed: Mapped[bool] = mapped_column(default=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped['User'] = relationship(back_populates='sessions')


class ImportantEvent(Base):
    """Structured long-term events used by future reminders and planners."""

    __tablename__ = 'important_events'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    importance: Mapped[str] = mapped_column(String(16), server_default='normal')
    source: Mapped[str] = mapped_column(String(32), server_default='session_summary')
    confidence: Mapped[float] = mapped_column(default=0.8)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped['User'] = relationship(back_populates='important_events')


class Reminder(Base):
    __tablename__ = 'reminders'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    text: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16), server_default='reminder')
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_sent: Mapped[bool] = mapped_column(default=False, server_default='false', index=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_sent: Mapped[bool] = mapped_column(default=False, server_default='false', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryChunk(Base):
    __tablename__ = 'memory_chunks'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    content: Mapped[str] = mapped_column(String)
    embedding: Mapped[list] = mapped_column(Vector(1536))
    source: Mapped[str] = mapped_column(String(32), server_default='conversation')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = 'payments'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    idempotence_key: Mapped[str] = mapped_column(String(64), unique=True)
    amount_rub: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), server_default='pending', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
