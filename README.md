# BotShop – Telegram Payment & Access Bot (Railway + Postgres)

פרויקט זה הוא בוט טלגרם שמקבל אישורי תשלום, שומר אותם ב-Postgres (Railway),
ומאפשר לאדמינים לאשר/לדחות עסקאות. הבוט רץ על Railway בתצורת Webhook עם FastAPI.

## מבנה הפרויקט

```text
.
├─ app/
│  ├─ main.py              # FastAPI + Webhook ל-Telegram
│  ├─ core/
│  │  ├─ config.py         # קריאת משתני סביבה והגדרות
│  │  └─ logging.py        # הגדרת לוגים
│  ├─ db/
│  │  ├─ session.py        # חיבור ל-Postgres (asyncpg)
│  │  └─ repositories.py   # פעולות CRUD בסיסיות
│  └─ bot/
│     ├─ application.py    # בניית Application של python-telegram-bot
│     ├─ keyboards.py      # כפתורים ותפריטים
│     ├─ handlers_start.py # /start
│     └─ handlers_payment.py # שליחת אישורי תשלום + אדמין
├─ requirements.txt
├─ Procfile
├─ start.sh
└─ .env.example
```

## מה הבוט יודע לעשות

### צד משתמש

- `/start` – ברוך הבא, יצירת משתמש בטבלה `users` ושמירת metric.
- כפתור "📥 שליחת אישור תשלום":
  - הבוט יבקש סכום (מספר, לדוגמה: 39).
  - לאחר מכן יבקש תמונה / צילום מסך של האישור.
  - הוא ישמור שורה בטבלת `payments` (משויך ל-telegram_id).
- כפתור "ℹ️ סטטוס תשלום" – כרגע תשובה טקסטואלית כללית, ניתן להרחבה.

### צד אדמין

- אדמין מזוהה לפי `TELEGRAM_ADMIN_IDS` (רשימת user_id במספרים).
- כפתור "📄 תשלומים ממתינים":
  - מציג רשימה של עד 20 תשלומים במצב `pending`.
  - מוסיף כפתורי Inline:
    - ✅ `admin_approve:<payment_id>` – מאשר תשלום (status='approved').
    - ❌ `admin_reject:<payment_id>` – דוחה תשלום (status='rejected').

### טבלאות

הקובץ `app/db/session.py` דואג לבצע `CREATE TABLE IF NOT EXISTS` עבור:

- `users`
- `payments`
- `referrals`
- `metrics`

אם כבר קיימות טבלאות באותו שם, Postgres ישאיר את המבנה הקיים, אבל ייתכן שצריך להתאים
את השדות לקוד במידת הצורך.

## התקנה מקומית

1. צור תיקייה על המחשב והוצא לתוכה את ה-ZIP.
2. צור וירטואלית (מומלץ):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # ב-Windows: .venv\Scripts\activate
   ```
3. התקן תלויות:
   ```bash
   pip install -r requirements.txt
   ```
4. צור קובץ `.env` לפי `.env.example` והגדר:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ADMIN_IDS`
   - `DATABASE_URL` (אפשר גם על Railway אם נוח לך).
   - `WEBHOOK_BASE_URL` (אם תרצה לבדוק Webhook חיצוני) או השאר ריק לפיתוח.
5. הפעל לוקלית:
   ```bash
   uvicorn app.main:app --reload --port 8080
   ```
6. בדיקה:
   - GET http://127.0.0.1:8080/health → אמור להחזיר `{ "status": "ok" }`.

> שים לב: במצב לוקלי ללא Webhook, נוח יותר להשתמש ב-long-polling. כרגע
> הפרויקט בנוי ל-Webhook. אם תרצה, אפשר להוסיף בקרוב קובץ נפרד `polling_main.py`
> שמריץ `telegram_app.run_polling()` במקום FastAPI.

## פריסה על Railway

### 1. שירות Postgres

כבר יש לך שירות Postgres פעיל עם טבלאות `users`, `payments`, `referrals`, `metrics`, וכו'.
שמור את ה-`DATABASE_URL` של השירות (בכרטיסייה Connect).

### 2. הכנת ריפו GitHub

1. צור ריפו חדש (לדוגמה: `botshop`).
2. העתק את כל הקבצים של הפרויקט לתיקייה מקומית.
3. הרץ:
   ```bash
   git init
   git add .
   git commit -m "BotShop: Telegram + FastAPI + Postgres (Deploy Pack)"
   git branch -M main
   git remote add origin https://github.com/<USERNAME>/botshop.git
   git push -u origin main
   ```

### 3. יצירת שירות Railway

1. ב-Railway: New → Deploy from GitHub → בחר את הריפו.
2. Root Directory: השאר ריק (הקבצים בשורש).
3. Railways יזהה את `Procfile` ויריץ:
   ```
   web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
   ```

### 4. משתני סביבה ב-Railway

תחת Settings → Variables, הוסף:

- `TELEGRAM_BOT_TOKEN` – הטוקן של הבוט.
- `TELEGRAM_ADMIN_IDS` – לדוגמה: `5010371391`.
- `DATABASE_URL` – העתיק מהשירות Postgres.
- `SERVICE_NAME` – לדוגמה: `botshop`.
- `LOG_LEVEL` – לדוגמה: `INFO`.
- `WEBHOOK_BASE_URL` – לדוגמה: `https://botshop-production.up.railway.app`
- `WEBHOOK_PATH` – לדוגמה: `telegram/webhook`.

אחרי שמירה Railway יבנה ויפעיל את השירות.

### 5. בדיקת בריאות

1. פתח את הדומיין של השירות, לדוגמה:
   `https://botshop-production.up.railway.app/health`
2. אתה אמור לקבל:
   ```json
   { "status": "ok" }
   ```
3. בדוק גם:
   `https://botshop-production.up.railway.app/meta`.

### 6. בדיקת הבוט

1. פתח את טלגרם, שלח `/start` לבוט.
2. אמור להופיע תפריט:
   - "📥 שליחת אישור תשלום"
   - "ℹ️ סטטוס תשלום"
   - ואם אתה אדמין – גם אפשרות לניהול.

## התאמה למסד הנתונים הקיים שלך

אם כבר יש לך טבלאות:

- `users`
- `payments`
- `referrals`
- `metrics`
- `rewards`
- `promoters`

והן מכילות שדות אחרים, תוכל לבצע אחת מהפעולות:

1. **להתאים את הקוד**:
   - ערוך את `app/db/session.py` ואת `app/db/repositories.py`
   - עדכן את השמות והשדות לפי הטבלאות הקיימות.

2. **ליצור טבלאות חדשות ייעודיות לבוט** (למשל בשם `botshop_users`, `botshop_payments`):
   - שנה את שמות הטבלאות בקובץ `session.py` + `repositories.py`.

זה נותן לך שליטה מלאה על החיבור למבנה הנתונים הקיים ב-Postgres של Railway.

---

אם תרצה, אפשר בשלב הבא:

- להוסיף API חיצוני (REST) להצגת סטטוסים/משתמשים/תשלומים.
- להרחיב את מנגנון referrals + rewards.
- לחבר את זה לשאר האקו-סיסטם של SLH / Sela / NIFTII.
