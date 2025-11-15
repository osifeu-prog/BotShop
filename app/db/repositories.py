import logging
from typing import Any, Dict, Optional, List

from app.db.session import get_pool

logger = logging.getLogger(__name__)


async def upsert_user(telegram_id: int, username: Optional[str], first_name: str, last_name: Optional[str], is_admin: bool = False) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO users (telegram_id, username, first_name, last_name, is_admin)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (telegram_id)
            DO UPDATE SET username = EXCLUDED.username,
                          first_name = EXCLUDED.first_name,
                          last_name = EXCLUDED.last_name;
            ''',
            telegram_id,
            username,
            first_name,
            last_name,
            is_admin,
        )


async def create_payment(telegram_id: int, amount: float, currency: str, proof_type: str, proof_file_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO payments (telegram_id, amount_numeric, currency, proof_type, proof_file_id)
            VALUES ($1, $2, $3, $4, $5);
            ''',
            telegram_id,
            amount,
            currency,
            proof_type,
            proof_file_id,
        )


async def list_pending_payments(limit: int = 20) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT id, telegram_id, amount_numeric, currency, status, created_at
            FROM payments
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT $1;
            ''',
            limit,
        )
    return [dict(r) for r in rows]


async def approve_payment(payment_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            UPDATE payments
            SET status = 'approved', approved_at = NOW()
            WHERE id::text = $1;
            ''',
            payment_id,
        )


async def reject_payment(payment_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            UPDATE payments
            SET status = 'rejected'
            WHERE id::text = $1;
            ''',
            payment_id,
        )


async def insert_metric(event_name: str, telegram_id: Optional[int], payload: Dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO metrics (event_name, telegram_id, payload)
            VALUES ($1, $2, $3);
            ''',
            event_name,
            telegram_id,
            payload,
        )
