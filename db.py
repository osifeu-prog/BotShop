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
    if not DATABASE_URL:
        return None
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.DictCursor,
    )
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
    יוצר את הטבלאות אם הן לא קיימות.
    לא מוחק נתונים קיימים.
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

        # users – לזיהוי משתמשים/מפנים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # referrals – הפניות בין משתמשים
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

        # rewards – פרסים / נקודות (כולל SHARE_POINTS)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rewards (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                reward_type TEXT NOT NULL,
                reason TEXT,
                points INT NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                tx_hash TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # promoters – מי שרכש והפך למפיץ עם פרטי בנק משלו
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS promoters (
                user_id BIGINT PRIMARY KEY,
                bank_details TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # metrics – מונים כלליים (למשל start_image_views)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                value BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        logger.info(
            "DB schema ensured (payments, users, referrals, rewards, promoters, metrics)."
        )


# =========================
# payments
# =========================

def log_payment(user_id: int, username: Optional[str], pay_method: str) -> None:
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
# users / referrals
# =========================

def store_user(user_id: int, username: Optional[str]) -> None:
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
# דוחות תשלומים
# =========================

def get_monthly_payments(year: int, month: int) -> List[Dict[str, Any]]:
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
# rewards / נקודות
# =========================

def create_reward(user_id: int, reward_type: str, reason: str, points: int = 0) -> None:
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


def get_share_points(user_id: int) -> int:
    with db_cursor() as (conn, cur):
        if cur is None:
            return 0
        cur.execute(
            """
            SELECT COALESCE(SUM(points), 0) AS pts
            FROM rewards
            WHERE user_id = %s
              AND reward_type = 'SHARE_POINTS';
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return 0
        return int(row["pts"])


def get_top_sharers(limit: int = 10) -> List[Dict[str, Any]]:
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT r.user_id,
                   u.username,
                   COALESCE(SUM(r.points), 0) AS total_points
            FROM rewards r
            LEFT JOIN users u ON u.id = r.user_id
            WHERE r.reward_type = 'SHARE_POINTS'
            GROUP BY r.user_id, u.username
            ORDER BY total_points DESC
            LIMIT %s;
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


# =========================
# promoters – בנק אישי למפיצים
# =========================

def set_promoter_bank(user_id: int, bank_details: str) -> None:
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO promoters (user_id, bank_details, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET bank_details = EXCLUDED.bank_details;
            """,
            (user_id, bank_details),
        )


def get_promoter_bank(user_id: int) -> Optional[str]:
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        cur.execute(
            """
            SELECT bank_details
            FROM promoters
            WHERE user_id = %s;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return row["bank_details"]


# =========================
# metrics – counters
# =========================

def increment_metric(key: str, delta: int = 1) -> int:
    with db_cursor() as (conn, cur):
        if cur is None:
            return 0
        cur.execute(
            """
            INSERT INTO metrics (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
              SET value = metrics.value + EXCLUDED.value,
                  updated_at = NOW()
            RETURNING value;
            """,
            (key, delta),
        )
        row = cur.fetchone()
        return int(row["value"]) if row else 0


def get_metric(key: str) -> int:
    with db_cursor() as (conn, cur):
        if cur is None:
            return 0
        cur.execute(
            """
            SELECT value
            FROM metrics
            WHERE key = %s;
            """,
            (key,),
        )
        row = cur.fetchone()
        if not row:
            return 0
        return int(row["value"])
