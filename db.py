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


@contextmanager
def db_cursor():
    """
    הקשר נוח לעבודה עם psycopg2.
    """
    if not DATABASE_URL:
        yield None, None
        return

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        yield conn, cur
        if conn:
            conn.commit()
    except Exception as e:
        logger.error("DB error: %s", e)
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =========================
# יצירת טבלאות (schema)
# =========================

def init_schema() -> None:
    """
    יוצר את כל הטבלאות הדרושות אם הן לא קיימות.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("init_schema called without DB.")
            return

        # users – משתמשי טלגרם
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id      BIGINT PRIMARY KEY,
                username     TEXT,
                first_name   TEXT,
                last_name    TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # payments – תשלומים / אישורים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT NOT NULL,
                username    TEXT,
                pay_method  TEXT NOT NULL,
                amount      NUMERIC DEFAULT 39.00,
                status      TEXT NOT NULL DEFAULT 'pending',
                reason      TEXT,
                approved_by BIGINT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # referrals – מי הפנה את מי
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id               SERIAL PRIMARY KEY,
                referrer_id      BIGINT NOT NULL,
                referred_user_id BIGINT NOT NULL,
                source           TEXT DEFAULT 'bot_start',
                status           TEXT DEFAULT 'active',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # promoters – בעלי נכס דיגיטלי
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS promoters (
                user_id              BIGINT PRIMARY KEY REFERENCES users(user_id),
                bank_details         TEXT,
                personal_group_link  TEXT,
                global_group_link    TEXT,
                custom_price         NUMERIC DEFAULT 39.00,
                total_earnings       NUMERIC DEFAULT 0.00,
                is_active            BOOLEAN DEFAULT TRUE,
                created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # user_assets - נכסים דיגיטליים של משתמשים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_assets (
                id                  SERIAL PRIMARY KEY,
                user_id             BIGINT NOT NULL REFERENCES users(user_id),
                asset_type          TEXT DEFAULT 'digital_gateway',
                asset_value         NUMERIC DEFAULT 39.00,
                personal_link       TEXT NOT NULL,
                referral_count      INTEGER DEFAULT 0,
                total_earnings      NUMERIC DEFAULT 0.00,
                status              TEXT DEFAULT 'active',
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # metrics – ספירות כלליות
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                key   TEXT PRIMARY KEY,
                value BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # activity_log - לוג פעילות
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT,
                action      TEXT NOT NULL,
                details     TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        logger.info("DB schema ensured (users, payments, referrals, promoters, user_assets, metrics, activity_log).")


# =========================
# users
# =========================

def store_user(user_id: int, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> None:
    """
    שומר/מעדכן משתמש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("store_user called without DB.")
            return
        cur.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET 
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                updated_at = NOW();
            """,
            (user_id, username, first_name, last_name),
        )

def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """
    מחזיר משתמש לפי ID.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        cur.execute(
            "SELECT * FROM users WHERE user_id = %s;",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# =========================
# payments
# =========================

def log_payment(user_id: int, username: Optional[str], pay_method: str, amount: float = 39.00) -> None:
    """
    רושם תשלום במצב 'pending'.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("log_payment called without DB.")
            return
        cur.execute(
            """
            INSERT INTO payments (user_id, username, pay_method, amount, status)
            VALUES (%s, %s, %s, %s, 'pending');
            """,
            (user_id, username, pay_method, amount),
        )

def update_payment_status(user_id: int, status: str, reason: Optional[str] = None, approved_by: Optional[int] = None) -> None:
    """
    מעדכן את הסטטוס של התשלום האחרון של המשתמש.
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
                approved_by = %s,
                updated_at = NOW()
            WHERE id = (
                SELECT id
                FROM payments
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            );
            """,
            (status, reason, approved_by, user_id),
        )

def get_user_payments(user_id: int) -> List[Dict[str, Any]]:
    """
    מחזיר את כל התשלומים של משתמש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT * FROM payments 
            WHERE user_id = %s 
            ORDER BY created_at DESC;
            """,
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]

def get_approval_stats() -> Dict[str, int]:
    """
    מחזיר סטטיסטיקות בסיסיות על תשלומים.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return {"total": 0, "approved": 0, "rejected": 0, "pending": 0}

        cur.execute("SELECT COUNT(*) AS total FROM payments;")
        total = int(cur.fetchone()["total"])

        def _count_status(st: str) -> int:
            cur.execute("SELECT COUNT(*) AS c FROM payments WHERE status = %s;", (st,))
            return int(cur.fetchone()["c"])

        approved = _count_status("approved")
        rejected = _count_status("rejected")
        pending = _count_status("pending")

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
        }


# =========================
# referrals & leaderboard
# =========================

def add_referral(referrer_id: int, referred_user_id: int, source: str = "bot_start") -> None:
    """
    מוסיף רשומת הפניה (referral).
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("add_referral called without DB.")
            return
        try:
            cur.execute(
                """
                INSERT INTO referrals (referrer_id, referred_user_id, source)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING;
                """,
                (referrer_id, referred_user_id, source),
            )
        except Exception as e:
            logger.error("Failed to add referral: %s", e)

def get_user_referrals(user_id: int) -> List[Dict[str, Any]]:
    """
    מחזיר את כל ההפניות של משתמש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT r.*, u.username, u.first_name, u.last_name
            FROM referrals r
            LEFT JOIN users u ON r.referred_user_id = u.user_id
            WHERE r.referrer_id = %s
            ORDER BY r.created_at DESC;
            """,
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]

def get_top_referrers(limit: int = 10) -> List[Dict[str, Any]]:
    """
    מחזיר Top referrers לפי מספר הפניות.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT
                r.referrer_id,
                u.username,
                u.first_name,
                u.last_name,
                COUNT(r.referred_user_id) AS total_referrals
            FROM referrals r
            LEFT JOIN users u ON r.referrer_id = u.user_id
            GROUP BY r.referrer_id, u.username, u.first_name, u.last_name
            ORDER BY total_referrals DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


# =========================
# promoters – שכבת הנכס הדיגיטלי
# =========================

def ensure_promoter(user_id: int) -> None:
    """
    מוודא שקיימת רשומה ב-promoters עבור המשתמש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("ensure_promoter called without DB.")
            return
        cur.execute(
            """
            INSERT INTO promoters (user_id)
            VALUES (%s)
            ON CONFLICT (user_id) DO NOTHING;
            """,
            (user_id,),
        )

def create_user_asset(user_id: int, personal_link: str) -> None:
    """
    יוצר נכס דיגיטלי למשתמש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("create_user_asset called without DB.")
            return
        cur.execute(
            """
            INSERT INTO user_assets (user_id, personal_link)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                personal_link = EXCLUDED.personal_link,
                updated_at = NOW();
            """,
            (user_id, personal_link),
        )

def get_user_asset(user_id: int) -> Optional[Dict[str, Any]]:
    """
    מחזיר את הנכס הדיגיטלי של משתמש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        cur.execute(
            "SELECT * FROM user_assets WHERE user_id = %s;",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

def update_promoter_settings(
    user_id: int,
    bank_details: Optional[str] = None,
    personal_group_link: Optional[str] = None,
    global_group_link: Optional[str] = None,
) -> None:
    """
    עדכון פרטי promoter.
    """
    fields = []
    params: List[Any] = []
    
    if bank_details is not None:
        fields.append("bank_details = %s")
        params.append(bank_details)
    if personal_group_link is not None:
        fields.append("personal_group_link = %s")
        params.append(personal_group_link)
    if global_group_link is not None:
        fields.append("global_group_link = %s")
        params.append(global_group_link)

    if not fields:
        return

    params.append(user_id)

    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("update_promoter_settings called without DB.")
            return
        cur.execute(
            f"""
            UPDATE promoters
            SET {", ".join(fields)},
                updated_at = NOW()
            WHERE user_id = %s;
            """,
            params,
        )

def get_promoter_summary(user_id: int) -> Optional[Dict[str, Any]]:
    """
    מחזיר פרטי promoter + כמה הפניות ותשלומים אושרו.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None

        # פרטי promoter
        cur.execute(
            """
            SELECT
                p.user_id,
                p.bank_details,
                p.personal_group_link,
                p.global_group_link,
                p.custom_price,
                p.total_earnings,
                p.created_at,
                p.updated_at
            FROM promoters p
            WHERE p.user_id = %s;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        promoter = dict(row)

        # נכס דיגיטלי
        asset = get_user_asset(user_id)
        promoter["asset"] = asset

        # כמה הפניות רשומות לו
        cur.execute(
            "SELECT COUNT(*) AS c FROM referrals WHERE referrer_id = %s;",
            (user_id,),
        )
        promoter["total_referrals"] = int(cur.fetchone()["c"])

        # כמה תשלומים אושרו למופנים שלו
        cur.execute(
            """
            SELECT COUNT(*) AS c
            FROM payments pay
            JOIN referrals ref ON ref.referred_user_id = pay.user_id
            WHERE ref.referrer_id = %s AND pay.status = 'approved';
            """,
            (user_id,),
        )
        promoter["approved_referrals"] = int(cur.fetchone()["c"])

        return promoter


# =========================
# metrics
# =========================

def incr_metric(key: str, delta: int = 1) -> None:
    """
    מגדיל מונה.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO metrics (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = metrics.value + EXCLUDED.value,
                         updated_at = NOW();
            """,
            (key, delta),
        )

def get_metric(key: str) -> int:
    """
    מחזיר את ערך המונה.
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


# =========================
# activity_log
# =========================

def log_activity(user_id: Optional[int], action: str, details: Optional[str] = None) -> None:
    """
    רושם פעילות למערכת.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO activity_log (user_id, action, details)
            VALUES (%s, %s, %s);
            """,
            (user_id, action, details),
        )

def get_recent_activity(limit: int = 50) -> List[Dict[str, Any]]:
    """
    מחזיר פעילות אחרונה.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT al.*, u.username, u.first_name, u.last_name
            FROM activity_log al
            LEFT JOIN users u ON al.user_id = u.user_id
            ORDER BY al.created_at DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


# =========================
# פונקציות אגרגציה
# =========================

def get_system_stats() -> Dict[str, Any]:
    """
    מחזיר סטטיסטיקות מערכת כוללות.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return {}
        
        stats = {}
        
        # ספירת משתמשים
        cur.execute("SELECT COUNT(*) FROM users;")
        stats["total_users"] = cur.fetchone()[0]
        
        # ספירת promoters
        cur.execute("SELECT COUNT(*) FROM promoters;")
        stats["total_promoters"] = cur.fetchone()[0]
        
        # ספירת תשלומים
        cur.execute("SELECT COUNT(*), SUM(amount) FROM payments WHERE status = 'approved';")
        row = cur.fetchone()
        stats["total_payments"] = row[0]
        stats["total_revenue"] = float(row[1]) if row[1] else 0.0
        
        # ספירת הפניות
        cur.execute("SELECT COUNT(*) FROM referrals;")
        stats["total_referrals"] = cur.fetchone()[0]
        
        # מונים
        stats["metrics"] = {
            "total_starts": get_metric("total_starts"),
            "approved_payments": get_metric("approved_payments"),
        }
        
        return stats
