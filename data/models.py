from datetime import datetime
from typing import List, Optional
from sqlalchemy import BigInteger, String, func, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data.database import Base


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(64))

    memory: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')
    tech_stack: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sessions: Mapped[List["Session"]] = relationship(back_populates='user', cascade='all, delete-orphan')


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
