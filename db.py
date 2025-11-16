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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # payments – תשלומים / אישורים
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                pay_method TEXT NOT NULL,
                amount DECIMAL DEFAULT 39.00,
                status TEXT DEFAULT 'pending',
                reason TEXT,
                approved_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # referrals – מי הפנה את מי
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                referred_user_id BIGINT NOT NULL,
                source TEXT DEFAULT 'bot_start',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # promoters – בעלי נכס דיגיטלי
        cur.execute("""
            CREATE TABLE IF NOT EXISTS promoters (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                bank_details TEXT,
                personal_group_link TEXT,
                global_group_link TEXT,
                custom_price DECIMAL DEFAULT 39.00,
                total_earnings DECIMAL DEFAULT 0.00,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # user_assets - נכסים דיגיטליים
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_assets (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id),
                asset_type TEXT DEFAULT 'digital_gateway',
                asset_value DECIMAL DEFAULT 39.00,
                personal_link TEXT NOT NULL,
                referral_count INTEGER DEFAULT 0,
                total_earnings DECIMAL DEFAULT 0.00,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # metrics – ספירות כלליות
        cur.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                value BIGINT DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # activity_log - לוג פעילות
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # social_posts - פוסטים חברתיים
        cur.execute("""
            CREATE TABLE IF NOT EXISTS social_posts (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                title TEXT,
                content TEXT,
                link_url TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # token_sales - מכירות טוקנים
        cur.execute("""
            CREATE TABLE IF NOT EXISTS token_sales (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                wallet_address TEXT,
                amount_slh DECIMAL,
                price_nis DECIMAL,
                tx_hash TEXT,
                tx_status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        logger.info("DB schema created successfully!")


# =========================
# users
# =========================

def store_user(user_id: int, username: Optional[str] = None) -> None:
    """
    שומר/מעדכן משתמש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("store_user called without DB.")
            return
        cur.execute(
            """
            INSERT INTO users (user_id, username)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET 
                username = EXCLUDED.username,
                updated_at = NOW();
            """,
            (user_id, username),
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
            WHERE user_id = %s 
            AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (status, reason, approved_by, user_id),
        )


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
                COUNT(r.referred_user_id) AS total_referrals
            FROM referrals r
            LEFT JOIN users u ON r.referrer_id = u.user_id
            GROUP BY r.referrer_id, u.username
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


def update_promoter_settings(
    user_id: int,
    bank_details: Optional[str] = None,
    personal_group_link: Optional[str] = None,
    global_group_link: Optional[str] = None,
) -> None:
    """
    עדכון פרטי promoter.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("update_promoter_settings called without DB.")
            return
            
        # First ensure promoter exists
        ensure_promoter(user_id)
        
        # Build update query dynamically
        updates = []
        params = []
        
        if bank_details is not None:
            updates.append("bank_details = %s")
            params.append(bank_details)
        if personal_group_link is not None:
            updates.append("personal_group_link = %s")
            params.append(personal_group_link)
        if global_group_link is not None:
            updates.append("global_group_link = %s")
            params.append(global_group_link)
            
        if updates:
            params.append(user_id)
            cur.execute(
                f"""
                UPDATE promoters 
                SET {', '.join(updates)}, updated_at = NOW()
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
            SELECT * FROM promoters WHERE user_id = %s;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        promoter = dict(row)

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
# API functions for website
# =========================

def get_social_posts(limit: int = 20) -> List[Dict[str, Any]]:
    """
    מחזיר פוסטים חברתיים לאתר.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT * FROM social_posts 
            WHERE status = 'active'
            ORDER BY created_at DESC 
            LIMIT %s;
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_token_sales(limit: int = 50) -> List[Dict[str, Any]]:
    """
    מחזיר מכירות טוקנים לאתר.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT * FROM token_sales 
            ORDER BY created_at DESC 
            LIMIT %s;
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def create_social_post(user_id: int, username: str, title: str, content: str, link_url: Optional[str] = None) -> None:
    """
    יוצר פוסט חברתי חדש.
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("create_social_post called without DB.")
            return
        cur.execute(
            """
            INSERT INTO social_posts (user_id, username, title, content, link_url)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (user_id, username, title, content, link_url),
        )


# =========================
# system stats
# =========================

def get_system_stats() -> Dict[str, Any]:
    """
    מחזיר סטטיסטיקות מערכת.
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
        cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved';")
        row = cur.fetchone()
        stats["total_payments"] = row[0]
        stats["total_revenue"] = float(row[1])
        
        # ספירת הפניות
        cur.execute("SELECT COUNT(*) FROM referrals;")
        stats["total_referrals"] = cur.fetchone()[0]
        
        return stats
