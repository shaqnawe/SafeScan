"""
Async PostgreSQL connection management using asyncpg.

Usage
-----
from db.connection import get_conn, close_pool

async def example():
    async with get_conn() as conn:
        row = await conn.fetchrow("SELECT 1")

Call close_pool() during application shutdown (e.g. FastAPI lifespan).
"""

import asyncpg
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# ---------------------------------------------------------------------------
# Module-level pool — created once, reused across requests
# ---------------------------------------------------------------------------
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the module-level connection pool, creating it on first call.

    Reads DATABASE_URL from the environment. Expected format:
        postgresql://user:password@host:port/dbname
    """
    global _pool
    if _pool is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set. "
                "Add it to your .env file: DATABASE_URL=postgresql://localhost:5432/safescan"
            )
        _pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
            # Automatically convert asyncpg Record objects to plain dicts for easier downstream use
            # (callers can still access by index or column name)
        )
    return _pool


@asynccontextmanager
async def get_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """Async context manager that yields a connection from the pool.

    Example
    -------
    async with get_conn() as conn:
        rows = await conn.fetch("SELECT * FROM products WHERE barcode = $1", barcode)
    """
    pool = await get_pool()
    async with pool.acquire() as connection:
        yield connection


async def close_pool() -> None:
    """Gracefully close the connection pool.

    Should be called during application shutdown so all connections are
    released cleanly before the process exits.
    """
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
