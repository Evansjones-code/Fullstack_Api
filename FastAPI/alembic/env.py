import asyncio
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Import your project settings
import models
from config import settings
from database import Base

# 1. WINDOWS ASYNC FIX
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 2. ALLEMBC CONFIG
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using create_async_engine."""
    
    # Priority: Uses settings.database_url from your .env 
    # Fallback: Uses the URL from alembic.ini
    url = settings.database_url or config.get_main_option("sqlalchemy.url")
    
    # Ensure the URL uses the async driver
    if url and not url.startswith("postgresql+psycopg"):
        url = url.replace("postgresql://", "postgresql+psycopg://")

    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.database_url or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
