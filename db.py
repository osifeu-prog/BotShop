# db.py - גרסה מתוקנת ומלאה
import os
import logging
from contextlib import contextmanager
from typing import Optional, Any, List, Dict
from datetime import datetime

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

def init_schema() -> None:
    """
    יוצר את כל הטבלאות הדרושות
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            logger.warning("init_schema called without DB.")
            return

        # users – משתמשי טלגרם (מתוקן)
        cur.execute(
            """
            
            CREATE TABLE IF NOT EXISTS users (
                user_id      BIGINT PRIMARY KEY,
                username     TEXT,
                first_name   TEXT,
                last_name    TEXT,
                phone        TEXT,
                email        TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            -- ensure new columns exist on older schemas
            ALTER TABLE users ADD COLUMN IF NOT EXISTS username   TEXT;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name  TEXT;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS phone      TEXT;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS email      TEXT;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
            ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
                        """
        )

        # referrals – מי הפנה את מי
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id               SERIAL PRIMARY KEY,
                referrer_id      BIGINT NOT NULL,
                referred_user_id BIGINT NOT NULL,
                source           TEXT,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # user_bots - בוטים אישיים למשתמשים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_bots (
                id           SERIAL PRIMARY KEY,
                user_id      BIGINT NOT NULL,
                bot_token    TEXT NOT NULL,
                bot_username TEXT NOT NULL,
                bot_name     TEXT NOT NULL,
                webhook_url  TEXT,
                price        NUMERIC NOT NULL DEFAULT 39.00,
                status       TEXT NOT NULL DEFAULT 'active',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(bot_token),
                UNIQUE(bot_username)
            );
            """
        )

        # bot_sales - מכירות בוטים בין משתמשים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_sales (
                id           SERIAL PRIMARY KEY,
                seller_id    BIGINT NOT NULL,
                buyer_id     BIGINT NOT NULL,
                bot_id       INTEGER NOT NULL,
                sale_price   NUMERIC NOT NULL,
                commission   NUMERIC NOT NULL DEFAULT 0,
                status       TEXT NOT NULL DEFAULT 'completed',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                FOREIGN KEY (bot_id) REFERENCES user_bots(id)
            );
            """
        )

        # pricing - הגדרות מחירים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing (
                id           SERIAL PRIMARY KEY,
                item_type    TEXT NOT NULL UNIQUE,
                base_price   NUMERIC NOT NULL,
                commission   NUMERIC NOT NULL DEFAULT 0,
                is_active    BOOLEAN NOT NULL DEFAULT TRUE,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        # metrics – ספירות כלליות
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                key   TEXT PRIMARY KEY,
                value BIGINT NOT NULL DEFAULT 0
            );
            """
        )

        # הוספת נתוני מחירים התחלתיים
        cur.execute(
            """
            INSERT INTO pricing (item_type, base_price, commission) 
            VALUES 
                ('personal_bot', 39.00, 5.00),
                ('premium_bot', 99.00, 10.00),
                ('business_bot', 199.00, 15.00)
            ON CONFLICT (item_type) DO NOTHING;
            """
        )


        -- promoters – הגדרות מקדמים (owners)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS promoters (
                user_id             BIGINT PRIMARY KEY,
                bank_details        TEXT,
                personal_group_link TEXT,
                global_group_link   TEXT,
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        -- rewards – תגמולים למקדמים / משתמשים
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rewards (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT NOT NULL,
                reward_type TEXT NOT NULL,
                amount      NUMERIC NOT NULL DEFAULT 0,
                details     TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        -- support_tickets – כרטיסי תמיכה
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT NOT NULL,
                subject     TEXT NOT NULL,
                message     TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'open',
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        logger.info("DB schema initialized successfully")

# =========================
# פונקציות משתמשים מתוקנות
# =========================

def store_user(user_id: int, username: Optional[str] = None, 
               first_name: Optional[str] = None, last_name: Optional[str] = None,
               phone: Optional[str] = None, email: Optional[str] = None) -> None:
    """
    שומר/מעדכן משתמש עם כל השדות
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, phone, email)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET 
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                phone = EXCLUDED.phone,
                email = EXCLUDED.email,
                updated_at = NOW();
            """,
            (user_id, username, first_name, last_name, phone, email),
        )

def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """
    מחזיר פרטי משתמש
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        cur.execute("SELECT * FROM users WHERE user_id = %s;", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

# =========================
# פונקציות בוטים אישיים
# =========================

def create_user_bot(user_id: int, bot_token: str, bot_username: str, 
                   bot_name: str, price: float = 39.00) -> int:
    """
    יוצר בוט חדש למשתמש
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return -1
        
        cur.execute(
            """
            INSERT INTO user_bots (user_id, bot_token, bot_username, bot_name, price)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (user_id, bot_token, bot_username, bot_name, price),
        )
        result = cur.fetchone()
        return result["id"] if result else -1

def get_user_bot(user_id: int) -> Optional[Dict[str, Any]]:
    """
    מחזיר את הבוט של משתמש
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        
        cur.execute(
            "SELECT * FROM user_bots WHERE user_id = %s AND status = 'active';",
            (user_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def get_bot_by_token(bot_token: str) -> Optional[Dict[str, Any]]:
    """
    מחזיר בוט לפי טוקן
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        
        cur.execute(
            "SELECT * FROM user_bots WHERE bot_token = %s;",
            (bot_token,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def get_all_user_bots() -> List[Dict[str, Any]]:
    """
    מחזיר את כל הבוטים הפעילים
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        
        cur.execute(
            """
            SELECT ub.*, u.username, u.first_name 
            FROM user_bots ub
            LEFT JOIN users u ON ub.user_id = u.user_id
            WHERE ub.status = 'active'
            ORDER BY ub.created_at DESC;
            """
        )
        return [dict(row) for row in cur.fetchall()]

def update_bot_price(bot_id: int, new_price: float) -> bool:
    """
    מעדכן מחיר של בוט
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return False
        
        cur.execute(
            "UPDATE user_bots SET price = %s, updated_at = NOW() WHERE id = %s;",
            (new_price, bot_id)
        )
        return cur.rowcount > 0

# =========================
# פונקציות מכירות ומחירים
# =========================

def record_bot_sale(seller_id: int, buyer_id: int, bot_id: int, 
                   sale_price: float, commission: float = 0) -> int:
    """
    רושם מכירת בוט
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return -1
        
        cur.execute(
            """
            INSERT INTO bot_sales (seller_id, buyer_id, bot_id, sale_price, commission)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (seller_id, buyer_id, bot_id, sale_price, commission),
        )
        result = cur.fetchone()
        return result["id"] if result else -1

def get_bot_sales_stats(user_id: int) -> Dict[str, Any]:
    """
    מחזיר סטטיסטיקות מכירות למשתמש
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return {}
        
        # סך מכירות
        cur.execute(
            "SELECT COUNT(*) as total_sales, COALESCE(SUM(sale_price), 0) as total_revenue FROM bot_sales WHERE seller_id = %s;",
            (user_id,)
        )
        sales_stats = cur.fetchone()
        
        # סך עמלות
        cur.execute(
            "SELECT COALESCE(SUM(commission), 0) as total_commissions FROM bot_sales WHERE seller_id = %s;",
            (user_id,)
        )
        commission_stats = cur.fetchone()
        
        return {
            "total_sales": sales_stats["total_sales"] if sales_stats else 0,
            "total_revenue": float(sales_stats["total_revenue"]) if sales_stats else 0.0,
            "total_commissions": float(commission_stats["total_commissions"]) if commission_stats else 0.0
        }

def get_pricing(item_type: str) -> Optional[Dict[str, Any]]:
    """
    מחזיר מחיר לפריט
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        
        cur.execute(
            "SELECT * FROM pricing WHERE item_type = %s AND is_active = TRUE;",
            (item_type,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def update_pricing(item_type: str, base_price: float, commission: float) -> bool:
    """
    מעדכן מחיר
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return False
        
        cur.execute(
            """
            INSERT INTO pricing (item_type, base_price, commission)
            VALUES (%s, %s, %s)
            ON CONFLICT (item_type)
            DO UPDATE SET base_price = EXCLUDED.base_price, commission = EXCLUDED.commission;
            """,
            (item_type, base_price, commission),
        )
        return True

# =========================
# פונקציות תשלומים
# =========================

def log_payment(user_id: int, username: Optional[str], pay_method: str, amount: float = 39.00) -> int:
    """
    רושם תשלום חדש
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return -1
        
        cur.execute(
            """
            INSERT INTO payments (user_id, username, pay_method, amount)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (user_id, username, pay_method, amount),
        )
        result = cur.fetchone()
        return result["id"] if result else -1

def update_payment_status(payment_id: int, status: str, reason: Optional[str] = None) -> bool:
    """
    מעדכן סטטוס תשלום
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return False
        
        cur.execute(
            "UPDATE payments SET status = %s, reason = %s, updated_at = NOW() WHERE id = %s;",
            (status, reason, payment_id)
        )
        return cur.rowcount > 0

# =========================
# פונקציות מטריקות
# =========================

def incr_metric(key: str, delta: int = 1) -> None:
    """
    מעדכן מונה
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        
        cur.execute(
            """
            INSERT INTO metrics (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = metrics.value + EXCLUDED.value;
            """,
            (key, delta),
        )

def get_metric(key: str) -> int:
    """
    מחזיר ערך מטריקה
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return 0
        
        cur.execute("SELECT value FROM metrics WHERE key = %s;", (key,))
        row = cur.fetchone()
        return row["value"] if row else 0


# =========================
# פונקציות רפרל/מקדמים/דוחות/תמיכה
# =========================

def add_referral(referrer_id: int, referred_user_id: int, source: Optional[str] = None) -> None:
    """
    רושם הפנייה חדשה לטובת referrer_id
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            INSERT INTO referrals (referrer_id, referred_user_id, source)
            VALUES (%s, %s, %s);
            """,
            (referrer_id, referred_user_id, source),
        )

def get_top_referrers(limit: int = 10) -> List[Dict[str, Any]]:
    """
    מחזיר טבלת מובילים לפי כמות הפניות שאושרו
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT r.referrer_id AS user_id,
                   u.username,
                   COUNT(*) AS total_referrals
            FROM referrals r
            LEFT JOIN users u ON u.user_id = r.referrer_id
            GROUP BY r.referrer_id, u.username
            ORDER BY total_referrals DESC
            LIMIT %s;
            """,
            (limit,),
        )
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]

def get_monthly_payments(months_back: int = 6) -> List[Dict[str, Any]]:
    """
    מחזיר סכומי תשלומים לפי חודשים אחרונים
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT date_trunc('month', created_at) AS month,
                   COUNT(*) AS total_payments,
                   SUM(amount) AS total_amount
            FROM payments
            WHERE created_at >= NOW() - INTERVAL '%s months'
            GROUP BY month
            ORDER BY month DESC;
            """,
            (months_back,),
        )
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]

def get_approval_stats() -> Dict[str, Any]:
    """
    מחזיר סטטוס אישורים (approved / rejected / pending)
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return {"approved": 0, "rejected": 0, "pending": 0}
        cur.execute(
            """
            SELECT status, COUNT(*) AS c
            FROM payments
            GROUP BY status;
            """
        )
        rows = cur.fetchall() or []
        stats = {"approved": 0, "rejected": 0, "pending": 0}
        for r in rows:
            stats[r["status"]] = r["c"]
        return stats

def create_reward(user_id: int, reward_type: str, amount: float = 0, details: Optional[str] = None) -> int:
    """
    רושם תגמול חדש למשתמש (למשל בונוס על הפניות)
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return -1
        cur.execute(
            """
            INSERT INTO rewards (user_id, reward_type, amount, details)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (user_id, reward_type, amount, details),
        )
        row = cur.fetchone()
        return row["id"] if row else -1

# ===== מקדמים =====

def ensure_promoter(user_id: int) -> None:
    """
    יוצר רשומת מקדם אם לא קיימת
    """
    with db_cursor() as (conn, cur):
        if cur is None:
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
    עדכון הגדרות מקדם
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return

        ensure_promoter(user_id)

        sets = []
        params: List[Any] = []
        if bank_details is not None:
            sets.append("bank_details = %s")
            params.append(bank_details)
        if personal_group_link is not None:
            sets.append("personal_group_link = %s")
            params.append(personal_group_link)
        if global_group_link is not None:
            sets.append("global_group_link = %s")
            params.append(global_group_link)

        if not sets:
            return

        params.append(user_id)
        sql = f"""
            UPDATE promoters
            SET {", ".join(sets)}, updated_at = NOW()
            WHERE user_id = %s;
        """
        cur.execute(sql, tuple(params))

def get_promoter_summary(user_id: int) -> Optional[Dict[str, Any]]:
    """
    מחזיר סיכום למקדם – כולל הגדרות בסיסיות ומספר הפניות
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return None
        cur.execute(
            """
            SELECT p.user_id,
                   p.bank_details,
                   p.personal_group_link,
                   p.global_group_link,
                   COALESCE(ref.cnt, 0) AS total_referrals
            FROM promoters p
            LEFT JOIN (
                SELECT referrer_id, COUNT(*) AS cnt
                FROM referrals
                GROUP BY referrer_id
            ) ref ON ref.referrer_id = p.user_id
            WHERE p.user_id = %s;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

# ===== תמיכה =====

def create_support_ticket(user_id: int, subject: str, message: str) -> int:
    """
    יוצר טיקט תמיכה חדש
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return -1
        cur.execute(
            """
            INSERT INTO support_tickets (user_id, subject, message)
            VALUES (%s, %s, %s)
            RETURNING id;
            """,
            (user_id, subject, message),
        )
        row = cur.fetchone()
        return row["id"] if row else -1

def get_support_tickets(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    מחזיר רשימת טיקטים, לפי סטטוס (ברירת מחדל: כולם)
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        if status:
            cur.execute(
                """
                SELECT * FROM support_tickets
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (status, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM support_tickets
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]

def update_ticket_status(ticket_id: int, status: str) -> None:
    """
    מעדכן סטטוס טיקט
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            UPDATE support_tickets
            SET status = %s, updated_at = NOW()
            WHERE id = %s;
            """,
            (status, ticket_id),
        )

# ===== עדכוני בוטים =====

def update_user_bot_status(bot_id: int, status: str) -> None:
    """
    עדכון סטטוס של בוט משתמש
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        cur.execute(
            """
            UPDATE user_bots
            SET status = %s
            WHERE id = %s;
            """,
            (status, bot_id),
        )

def get_all_active_bots() -> List[Dict[str, Any]]:
    """
    מחזיר את כל הבוטים הפעילים
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return []
        cur.execute(
            """
            SELECT * FROM user_bots
            WHERE status = 'active';
            """
        )
        rows = cur.fetchall() or []
        return [dict(r) for r in rows]

def update_bot_webhook(bot_id: int, new_webhook_url: str) -> None:
    """
    עדכון כתובת webhook של בוט משתמש
    (כרגע נשמרת בעמודת description / הרחבה בעתיד)
    """
    with db_cursor() as (conn, cur):
        if cur is None:
            return
        # לפשט – נשמור את ה-webhook כתיאור בבוט
        cur.execute(
            """
            UPDATE user_bots
            SET description = CONCAT(COALESCE(description, ''), '\nWebhook: ', %s)
            WHERE id = %s;
            """,
            (new_webhook_url, bot_id),
        )
