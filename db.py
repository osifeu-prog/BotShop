# db.py
import os
import logging
from contextlib import contextmanager
from typing import Optional, Any, List, Dict

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    logger.warning("DATABASE_URL is not set. DB functions will be no-op.")


def get_conn():
    """מחזיר חיבור ל-Postgres או None אם אין DATABASE_URL"""
    if not DATABASE_URL:
        return None
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
    return conn


@contextmanager
def db_cursor():
    conn = get_conn()
    if conn is None:
        yield None, None
        return
    try:
        cur = conn.cursor()
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def init_schema() -> None:
    """
    מריץ CREATE TABLE IF NOT EXISTS לכל הטבלאות.
    לא מוחק ולא שובר כלום, רק מוסיף אם חסר.
    """
    if not DATABASE_URL:
        logger.warning("init_schema called but DATABASE_URL not set.")
        return

    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("No DB cursor available in init_schema.")
            return

        # payments – כבר קיימת אצלך, כאן רק לוודא
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                pay_method TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # users – רשימת משתמשים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,      -- Telegram user id
                username TEXT,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # referrals – הפניות
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                referred_id BIGINT NOT NULL,
                source TEXT,
                points INT NOT NULL DEFAULT 1,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # rewards – פרסים/נקודות (SLH, NFT, SHARE וכו')
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rewards (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                reward_type TEXT NOT NULL,      -- "SLH", "NFT", "SHARE", ...
                reason TEXT,
                points INT NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',   -- pending/sent/failed
                tx_hash TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # metrics – מונים גלובליים (למשל start_image_views)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                value BIGINT NOT NULL DEFAULT 0
            );
            """
        )

        logger.info("DB schema ensured (payments, users, referrals, rewards, metrics).")


# =========================
# payments
# =========================

def log_payment(user_id: int, username: Optional[str], pay_method: str) -> None:
    """
    רושם תשלום במצב 'pending' (כשהמשתמש שולח צילום אישור).
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("log_payment called without DB.")
            return
        cur.execute(
            """
            INSERT INTO payments (user_id, username, pay_method, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'pending', NOW(), NOW());
            """,
            (user_id, username, pay_method),
        )


def update_payment_status(user_id: int, status: str, reason: Optional[str]) -> None:
    """
    מעדכן את הסטטוס של התשלום האחרון של משתמש מסוים.
    status: 'approved' / 'rejected' / 'pending'
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("update_payment_status called without DB.")
            return
        cur.execute(
            """
            UPDATE payments
            SET status = %s,
                reason = %s,
                updated_at = NOW()
            WHERE id = (
                SELECT id
                FROM payments
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            );
            """,
            (status, reason, user_id),
        )


# =========================
# users / referrals – למערכת ניקוד ו-Leaderboard
# =========================

def store_user(user_id: int, username: Optional[str]) -> None:
    """
    שומר/מעדכן משתמש בטבלת users.
    אם קיים – מעדכן username.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO users (id, username, first_seen_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (id) DO UPDATE
              SET username = EXCLUDED.username;
            """,
            (user_id, username),
        )


def add_referral(referrer_id: int, referred_id: int, source: str) -> None:
    """
    מוסיף רשומת הפנייה.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO referrals (referrer_id, referred_id, source, points)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT DO NOTHING;
            """,
            (referrer_id, referred_id, source),
        )


def get_top_referrers(limit: int = 10) -> List[Dict[str, Any]]:
    """
    מחזיר את המפנים הטופ לפי סך נקודות / מספר הפניות.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT r.referrer_id,
                   u.username,
                   COUNT(*) AS total_referrals,
                   SUM(r.points) AS total_points
            FROM referrals r
            LEFT JOIN users u ON u.id = r.referrer_id
            GROUP BY r.referrer_id, u.username
            ORDER BY total_points DESC, total_referrals DESC
            LIMIT %s;
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


# =========================
# דוחות על תשלומים
# =========================

def get_monthly_payments(year: int, month: int) -> List[Dict[str, Any]]:
    """
    מחזיר פילוח לפי שיטת תשלום וסטטוס לחודש נתון.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT pay_method,
                   status,
                   COUNT(*) AS count
            FROM payments
            WHERE EXTRACT(YEAR FROM created_at) = %s
              AND EXTRACT(MONTH FROM created_at) = %s
            GROUP BY pay_method, status
            ORDER BY pay_method, status;
            """,
            (year, month),
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def get_approval_stats() -> Optional[Dict[str, Any]]:
    """
    מחזיר סטטיסטיקה כללית על statuses מהמכלול.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE status = 'pending') AS pending,
              COUNT(*) FILTER (WHERE status = 'approved') AS approved,
              COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
              COUNT(*) AS total
            FROM payments;
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


# =========================
# rewards – בסיס ל-NFT / SLH / SHARE
# =========================

def create_reward(user_id: int, reward_type: str, reason: str, points: int = 0) -> None:
    """
    יוצר רשומת Reward במצב 'pending'.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO rewards (user_id, reward_type, reason, points, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'pending', NOW(), NOW());
            """,
            (user_id, reward_type, reason, points),
        )


def get_user_total_points(user_id: int, reward_type: Optional[str] = None) -> int:
    """
    מחזיר סך נקודות למשתמש מתוך rewards.
    אם reward_type לא None – מסנן לפי סוג (למשל 'SHARE').
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return 0

        if reward_type:
            cur.execute(
                """
                SELECT COALESCE(SUM(points), 0) AS total_points
                FROM rewards
                WHERE user_id = %s
                  AND reward_type = %s;
                """,
                (user_id, reward_type),
            )
        else:
            cur.execute(
                """
                SELECT COALESCE(SUM(points), 0) AS total_points
                FROM rewards
                WHERE user_id = %s;
                """,
                (user_id,),
            )

        row = cur.fetchone()
        return int(row["total_points"]) if row else 0


# =========================
# metrics – מונים גלובליים
# =========================

def increment_metric(key: str, amount: int = 1) -> int:
    """
    מעלה מונה גלובלי ומחזיר את הערך החדש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return 0
        cur.execute(
            """
            INSERT INTO metrics (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = metrics.value + EXCLUDED.value
            RETURNING value;
            """,
            (key, amount),
        )
        row = cur.fetchone()
        return int(row["value"]) if row else 0


def get_metric(key: str) -> int:
    """
    מחזיר את ערך המונה או 0 אם לא קיים.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return 0
        cur.execute(
            "SELECT value FROM metrics WHERE key = %s;",
            (key,),
        )
        row = cur.fetchone()
        return int(row["value"]) if row else 0

def get_users_stats() -> Dict[str, int]:
    """Aggregate basic user/referral stats for admin dashboard."""
    with db_cursor() as (conn, cur):
        if cur is None:
            return {
                "total_users": 0,
                "total_referrals": 0,
                "total_referred_users": 0,
                "total_referrers": 0,
            }

        # Total registered users
        cur.execute("SELECT COUNT(*) FROM users;")
        total_users = cur.fetchone()[0] or 0

        # Total referral rows
        cur.execute("SELECT COUNT(*) FROM referrals;")
        total_referrals = cur.fetchone()[0] or 0

        # Distinct referred users (joined through any referral link)
        cur.execute("SELECT COUNT(DISTINCT referred_id) FROM referrals;")
        total_referred_users = cur.fetchone()[0] or 0

        # Distinct referrers (users who brought at least one friend)
        cur.execute("SELECT COUNT(DISTINCT referrer_id) FROM referrals;")
        total_referrers = cur.fetchone()[0] or 0

        return {
            "total_users": int(total_users),
            "total_referrals": int(total_referrals),
            "total_referred_users": int(total_referred_users),
            "total_referrers": int(total_referrers),
        }
