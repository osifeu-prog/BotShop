# BotShop Fixed – 2025-11-19

זהו עדכון ממוקד לפרויקט **botshop** שלך כדי שירוץ חלק על Railway.

הזיפ כולל:

- `main.py` מתוקן:
  - ייבוא מודולים נכון:
    - `from slh.slh_public_api import router as public_router`
    - `from social_api import router as social_router`
    - `from SLH.slh_core_api import router as core_router`
    - `from slh.slhnet_extra import router as slhnet_extra_router`
  - פקודה חדשה `/chatinfo` למציאת `chat_id` של כל צ׳אט שבו הבוט חבר.
- `db.py` מתוקן:
  - הוסר בלוק קוד שבור בסוף הקובץ שגרם ל־`SyntaxError: unexpected character after line continuation character`.

## איך להשתמש בזיפ

1. חלץ את התיקייה:

   - מחק או גבה את התוכן הקיים של הפרויקט על המחשב.
   - חלץ את `botshop_fixed_20251119.zip` לאותה תיקייה שבה הפרויקט שלך היה קודם.

   התוצאה צריכה להיות מבנה בסגנון:

   ```text
   botshop-main/
     main.py
     db.py
     SLH/
     slh/
     social_api.py
     docs/
     templates/
     Procfile
     requirements.txt
     ...
   ```

2. עדכן ל-Git (אם אתה עובד דרך Git):

   ```bash
   git add main.py db.py README.md
   git commit -m "fix: main imports, db syntax, add /chatinfo"
   git push
   ```

   אם אתה מעלה זיפ ידנית ל-Railway – פשוט העלה את הזיפ החדש במקום הפרויקט הישן.

## בדיקות בסיסיות מקומית

אם אתה מריץ מקומית:

1. צור וירטואלית והתקן חבילות:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # ב-Windows
   pip install -r requirements.txt
   ```

2. הגדר משתני סביבה מינימליים (לבדיקה):

   ```bash
   set BOT_TOKEN=...        # טוקן הבוט שלך
   set WEBHOOK_URL=https://example.com/webhook
   ```

3. הרץ את השרת:

   ```bash
   uvicorn main:app --reload --port 8080
   ```

4. בדוק שהאפליקציה חיה:

   - היכנס בדפדפן ל:
     - `http://127.0.0.1:8080/healthz`
     - `http://127.0.0.1:8080/meta`

### מה אתה אמור לראות

- `GET /healthz`:

  ```json
  {
    "status": "ok",
    "telegram_ready": true או false,
    "db_connected": true או false
  }
  ```

- `GET /meta`:

  ```json
  {
    "bot_username": "Buy_My_Shop_bot",
    "webhook_url": "https://botshop-production.up.railway.app/webhook",
    "community_group_link": "...",
    "support_group_link": "..."
  }
  ```

אם הגענו לכאן בלי שגיאות – זה אומר שהקוד נטען בלי קריסות ו-Uvicorn הצליח להרים את FastAPI.

## בדיקה על Railway

אחרי שהעלית את הקוד המתוקן:

1. ודא שהמשתנים הבאים מוגדרים:

   - `BOT_TOKEN`
   - `WEBHOOK_URL` = `https://botshop-production.up.railway.app/webhook`
   - `ADMIN_ALERT_CHAT_ID` (אפשר להשאיר ריק בהתחלה)
   - `PAYBOX_URL` / `BIT_URL` / `PAYPAL_URL` לפי הצורך
   - `LANDING_URL` (אם יש דף נחיתה חיצוני)
   - `DATABASE_URL` (אם אתה משתמש ב-PostgreSQL)

2. עשה **Redeploy** לשירות.

3. פתח את ה-URL הציבורי של השירות ובדוק:

   - `https://botshop-production.up.railway.app/healthz`
   - `https://botshop-production.up.railway.app/meta`

אם יש שגיאה, היא תופיע בלוגים של Railway, אבל ה-SyntaxError של `db.py` כבר לא אמור להופיע.

## פקודת /chatinfo למציאת chat_id

אחרי שהבוט באוויר:

1. הוסף את הבוט לקבוצה/ערוץ שאתה רוצה להשתמש בו כלוג/אדמינים.
2. בקבוצה הזו, שלח:

   ```text
   /chatinfo
   ```

3. הבוט יחזיר לך משהו בסגנון:

   ```text
   chat_id: -1001234567890
   סוג: supergroup
   כותרת: SLH Business Logs
   ```

4. קח את המספר `chat_id` (כולל `-100` אם יש) והגדר אותו ב-Railway כ:

   - `ADMIN_ALERT_CHAT_ID = -1001234567890`

5. Redeploy פעם נוספת.

מהרגע הזה, כל הודעות הלוג (למשל על `/start` או תשלומים) יישלחו לקבוצה הזו.

---

אם תרצה סיבוב נוסף, אפשר בשלב הבא:

- ליישר את תיקיית `docs`/`templates` כך שהאתר ישמש כדף נחיתה חד ל-39₪,
- להוסיף סטטיסטיקות מתקדמות יותר ל-/stats,
- או לחבר את ה-API ל-SLH Token / SLHNET המלא.
