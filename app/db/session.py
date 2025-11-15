import asyncpg
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.pool.Pool] = None

async def get_pool() -> asyncpg.pool.Pool:
    global _pool
    if _pool is None:
        settings = get_settings()
        logger.info("Creating Postgres connection pool")
        _pool = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=5)
    return _pool

async def init_db() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # These tables are minimal versions; if they already exist in your DB,
        # Postgres will keep the existing structure.
        await conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            '''
        )
        await conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS payments (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                amount_numeric NUMERIC(18,2),
                currency TEXT,
                status TEXT DEFAULT 'pending',
                proof_type TEXT,
                proof_file_id TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                approved_at TIMESTAMPTZ
            );
            '''
        )
        await conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS referrals (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                inviter_telegram_id BIGINT NOT NULL,
                invited_telegram_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            '''
        )
        await conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS metrics (
                id BIGSERIAL PRIMARY KEY,
                event_name TEXT NOT NULL,
                telegram_id BIGINT,
                payload JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            '''
        )
    logger.info("DB schema ensured")
