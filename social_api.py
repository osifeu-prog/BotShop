from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import db_cursor

social_router = APIRouter()


class SocialProfileIn(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    display_name: Optional[str] = None
    wallet_address: str
    allow_public_profile: bool = True


class SocialProfileOut(BaseModel):
    telegram_id: int
    username: Optional[str]
    display_name: Optional[str]
    wallet_address: Optional[str]
    allow_public_profile: bool
    is_seller: bool
    seller_price: Optional[float] = None
    referral_count: int = 0
    can_sell_link: bool = False


def _compute_referral_count(cur, telegram_id: int) -> int:
    try:
        cur.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_telegram_id = %s;",
            (telegram_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _has_approved_payment(cur, telegram_id: int) -> bool:
    try:
        cur.execute(
            "SELECT COUNT(*) FROM payments WHERE telegram_id = %s AND status = 'approved';",
            (telegram_id,),
        )
        row = cur.fetchone()
        return (row[0] or 0) > 0 if row else False
    except Exception:
        return False


@social_router.post("/register", response_model=SocialProfileOut)
async def register_profile(payload: SocialProfileIn):
    """
    רישום/עדכון פרופיל רשת חברתית.
    - telegram_id + username + wallet_address = זהות המשתמש.
    - allow_public_profile = האם להציג את הפרופיל (או רק תשלומים).
    - is_seller = TRUE אם:
        * יש לפחות תשלום אחד מאושר בטבלת payments, או
        * יש לפחות 39 הפניות (referrals) כ-referrer_telegram_id.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            raise HTTPException(status_code=503, detail="DB not available")

        referral_count = _compute_referral_count(cur, payload.telegram_id)
        has_paid = _has_approved_payment(cur, payload.telegram_id)

        is_seller = bool(has_paid or referral_count >= 39)
        can_sell = is_seller

        cur.execute(
            """
            INSERT INTO social_profiles (
                telegram_id,
                username,
                display_name,
                wallet_address,
                allow_public_profile,
                is_seller
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE
            SET username = EXCLUDED.username,
                display_name = EXCLUDED.display_name,
                wallet_address = EXCLUDED.wallet_address,
                allow_public_profile = EXCLUDED.allow_public_profile,
                is_seller = EXCLUDED.is_seller;
            """,
            (
                payload.telegram_id,
                payload.username,
                payload.display_name,
                payload.wallet_address,
                payload.allow_public_profile,
                is_seller,
            ),
        )

        conn.commit()

        return SocialProfileOut(
            telegram_id=payload.telegram_id,
            username=payload.username,
            display_name=payload.display_name,
            wallet_address=payload.wallet_address,
            allow_public_profile=payload.allow_public_profile,
            is_seller=is_seller,
            seller_price=None,
            referral_count=referral_count,
            can_sell_link=can_sell,
        )


@social_router.get("/profile/{telegram_id}", response_model=SocialProfileOut)
async def get_profile(telegram_id: int):
    """
    שליפת פרופיל רשת חברתית + ספירת הפניות + האם מותר למכור לינק.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            raise HTTPException(status_code=503, detail="DB not available")

        cur.execute(
            """
            SELECT telegram_id,
                   username,
                   display_name,
                   wallet_address,
                   allow_public_profile,
                   is_seller,
                   seller_price
            FROM social_profiles
            WHERE telegram_id = %s;
            """,
            (telegram_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found")

        referral_count = _compute_referral_count(cur, telegram_id)
        has_paid = _has_approved_payment(cur, telegram_id)
        is_seller = bool(row[5] or has_paid or referral_count >= 39)
        can_sell = is_seller

        return SocialProfileOut(
            telegram_id=row[0],
            username=row[1],
            display_name=row[2],
            wallet_address=row[3],
            allow_public_profile=bool(row[4]),
            is_seller=is_seller,
            seller_price=float(row[6]) if row[6] is not None else None,
            referral_count=referral_count,
            can_sell_link=can_sell,
        )


@social_router.get("/market")
async def social_market():
    """
    זירת 'מוכרים'  מי שרשומים כ-is_seller=TRUE.
    (השלב הבא: לחבר למחירי גישה אמיתיים מתשלומי payments.)
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            raise HTTPException(status_code=503, detail="DB not available")

        cur.execute(
            """
            SELECT telegram_id,
                   username,
                   display_name,
                   wallet_address,
                   allow_public_profile,
                   is_seller,
                   seller_price
            FROM social_profiles
            WHERE is_seller = TRUE;
            """
        )
        rows = cur.fetchall() or []

        results = []
        for row in rows:
            telegram_id = row[0]
            referral_count = _compute_referral_count(cur, telegram_id)
            has_paid = _has_approved_payment(cur, telegram_id)
            is_seller = bool(row[5] or has_paid or referral_count >= 39)
            results.append(
                dict(
                    telegram_id=telegram_id,
                    username=row[1],
                    display_name=row[2],
                    wallet_address=row[3],
                    allow_public_profile=bool(row[4]),
                    is_seller=is_seller,
                    seller_price=float(row[6]) if row[6] is not None else None,
                    referral_count=referral_count,
                )
            )

        return {"sellers": results}
