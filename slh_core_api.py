import os
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import get_conn

logger = logging.getLogger("slhnet.core")

router = APIRouter()


class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    display_name: Optional[str] = None
    referral_code: Optional[str] = None


class Shop(BaseModel):
    id: str
    owner_user_id: str
    title: str
    description: Optional[str] = None
    slug: str
    shop_type: str
    status: str
    referral_code: str
    created_at: str
    updated_at: str


def ensure_uuid() -> str:
    return str(uuid.uuid4())


@router.post("/core/users/telegram-sync")
async def telegram_sync_user(payload: UserCreate) -> Dict[str, Any]:
    """
    מוודא שהמשתמש קיים בטבלת users, יוצר אם צריך.
    """
    conn = get_conn()
    with conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, telegram_id, telegram_username, display_name, bnb_address, ton_address, referrer_id, created_at, updated_at
            FROM public.users
            WHERE telegram_id = %s
            """,
            (payload.telegram_id,),
        )
        row = cur.fetchone()
        if row:
            user = {
                "id": row[0],
                "telegram_id": row[1],
                "telegram_username": row[2],
                "display_name": row[3],
                "bnb_address": row[4],
                "ton_address": row[5],
                "referrer_id": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
                "updated_at": row[8].isoformat() if row[8] else None,
            }
            return user

        user_id = ensure_uuid()
        now = datetime.utcnow()
        cur.execute(
            """
            INSERT INTO public.users (id, telegram_id, telegram_username, display_name, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                payload.telegram_id,
                payload.username,
                payload.display_name,
                now,
                now,
            ),
        )

        return {
            "id": user_id,
            "telegram_id": payload.telegram_id,
            "telegram_username": payload.username,
            "display_name": payload.display_name,
            "bnb_address": None,
            "ton_address": None,
            "referrer_id": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }


@router.get("/core/users/{user_id}/shops", response_model=List[Shop])
async def get_user_shops(user_id: str):
    conn = get_conn()
    with conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, owner_user_id, title, description, slug, shop_type, status, referral_code, created_at, updated_at
            FROM public.shops
            WHERE owner_user_id = %s
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        result: List[Shop] = []
        for row in rows:
            result.append(
                Shop(
                    id=row[0],
                    owner_user_id=row[1],
                    title=row[2],
                    description=row[3],
                    slug=row[4],
                    shop_type=row[5],
                    status=row[6],
                    referral_code=row[7],
                    created_at=row[8].isoformat() if row[8] else None,
                    updated_at=row[9].isoformat() if row[9] else None,
                )
            )
        return result

