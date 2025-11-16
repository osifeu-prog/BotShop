
# BotShop Gateway Minimal – SLHNET Onboarding

פרויקט מינימלי לשער כניסה לקהילת SLHNET:
- בוט טלגרם עם Webhook (FastAPI)
- לוגים מלאים לקבוצת אדמינים
- קבלת אישורי תשלום (תמונה) ורישום ב-Postgres
- מערכת פניות תמיכה פשוטה

## 1. מבנה הפרויקט

```text
botshop_gateway_minimal/
├── main.py          # FastAPI + Telegram Webhook
├── db.py            # SQLAlchemy + טבלאות users/payments/support
├── config.py        # קריאת משתני סביבה
├── requirements.txt
├── Procfile         # uvicorn main:app ...
├── .gitignore
└── README.md
```

## 2. משתני סביבה (Railway)

להגדיר ב-Service של הבוט:

חובה:
```env
BOT_TOKEN=xxx
BOT_USERNAME=Buy_My_Shop_bot
WEBHOOK_URL=https://webwook-production-4861.up.railway.app/webhook

DATABASE_URL=${Postgres.DATABASE_URL}
```

לוגים ותמיכה (חובה כדי שהמערכת תהיה שימושית):

```env
ADMIN_LOGS_CHAT_ID=-100xxxxxxxxxx        # הקבוצה: https://t.me/+aww1rlTDUSplODc0
SUPPORT_GROUP_CHAT_ID=-100yyyyyyyyyy     # הקבוצה: https://t.me/+1ANn25HeVBoxNmRk
```

קישורים ציבוריים (משתמשים רואים רק את ה-URLים האלו):

```env
BUSINESS_GROUP_URL=https://t.me/+HIzvM8sEgh1kNWY0
SUPPORT_GROUP_URL=https://t.me/+1ANn25HeVBoxNmRk
LANDING_URL=https://slh-nft.com
DEFAULT_LANG=he
```

תשלום (39 ש"ח):

```env
SLH_NIS=39
BIT_URL=0546671882
PAYBOX_URL=https://links.payboxapp.com/1SNfaJ6XcYb
PAYPAL_URL=https://paypal.me/osifdu
```

אפשר להשאיר את שאר המשתנים הקיימים ב-Railway – הקוד פשוט מתעלם מהם.

### איך להשיג chat_id של קבוצות (ADMIN_LOGS / SUPPORT)

1. ודא שהבוט הוא admin בקבוצה.
2. שלח הודעה בקבוצה.
3. הרץ סקריפט קצר מקומי עם bot token שמדפיס `update.effective_chat.id`,
   או השתמש בבוט כללי (כמו RawDataBot) כדי לקרוא את ה-chat_id.
4. עדכן את הערכים ב-Railway.

## 3. לוגיקת הבוט

### /start

- רושם/מעדכן את המשתמש ב-Postgres (`botshop_users`).
- שולח הודעת לוג לקבוצת האדמינים (ADMIN_LOGS_CHAT_ID):
  - ID
  - username
  - full name
  - chat_id
- שולח למשתמש הודעה עם:
  - הסבר על SLHNET וה-39 ש"ח
  - כפתור "💳 לשלם 39 ש"ח"
  - כפתור "📢 קהילת העסקים" (לינק לקבוצה)
  - כפתור "🛠 תמיכה טכנית"
  - כפתור "🌐 אתר הפרויקט"

### תשלום – כפתור "💳 לשלם 39 ש"ח"

- מציג למשתמש טקסט עם כל אפשרויות התשלום:
  - Bit (BIT_URL)
  - PayBox (PAYBOX_URL)
  - PayPal (PAYPAL_URL)
- מבקש מהמשתמש לשלוח תמונה של אישור התשלום לבוט.

### אישור תשלום (תמונה)

- כל תמונה בצ'אט פרטי:
  - נרשמת כ-`botshop_payment_proofs` ב-Postgres.
  - נשלחת לקבוצת האדמינים (ADMIN_LOGS_CHAT_ID) עם:
    - user_id
    - username
    - from chat_id
    - צילום האישור עצמו.
- למשתמש נשלחת תשובה:
  - "✅ תודה! אישור התשלום התקבל ונמצא כעת בבדיקה..."

(שלב האישור הידני והכנסת המשתמש לקבוצת העסקים ייעשו ידנית בשלב זה.)

### תמיכה – כפתור "🛠 תמיכה טכנית"

- הבוט מבקש מהמשתמש לכתוב את נושא ותוכן הפניה.
- ההודעה הראשונה שנשלחת לאחר מכן:
  - נרשמת בטבלה `botshop_support_tickets`.
  - נשלחת לקבוצת התמיכה (SUPPORT_GROUP_CHAT_ID) עם:
    - ID
    - username
    - נושא
    - טקסט מלא של ההודעה.
- לאחר השליחה:
  - למשתמש נשלחת תשובה: "✅ ההודעה נשלחה לתמיכה..."

## 4. הרצה מקומית (אופציונלי)

```bash
python -m venv .venv
source .venv/bin/activate  # ב-Windows: .venv\Scripts\activate
pip install -r requirements.txt

export BOT_TOKEN=...
export WEBHOOK_URL=http://localhost:8000/webhook
export DATABASE_URL=postgresql://...

uvicorn main:app --reload
```

(להרצת webhook לוקאלי צריך להשתמש ב-ngrok או כלי דומה – ב-Railway זה כבר מוגדר דרך WEBHOOK_URL.)

## 5. פריסה ל-Railway

1. צור ריפו GitHub חדש (למשל `botshop-gateway-minimal`).
2. העלה אליו את כל קבצי התיקייה.
3. חבר את ה-Repo ל-Railway.
4. ודא ש:
   - `Procfile` נמצא בשורש.
   - `requirements.txt` בשורש.
   - HEALTHCHECK מוגדר ל-`/health`.
5. עדכן משתני סביבה בדיוק כפי שמופיעים למעלה.
6. פרוס (Deploy) את השירות.

אם /health מחזיר:
```json
{"status": "ok", "service": "botshop-gateway-minimal", "db": "enabled"}
```
המערכת מוכנה לפרסום.

---

בשלב הבא נוכל להרחיב מכאן ל:
- חיבור למערכת החנויות / SLH Shop System
- הוספת לוגיקת "אישור תשלום" שמשנה סטטוס בבסיס הנתונים
- שליחת קישור אוטומטית לקבוצת העסקים לאחר אישור.
