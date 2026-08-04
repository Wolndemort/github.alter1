import asyncio
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from config import config as app_config
from data.database import Base
import data.models

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=app_config.DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = async_engine_from_config(
        {"sqlalchemy.url": app_config.DATABASE_URL}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
