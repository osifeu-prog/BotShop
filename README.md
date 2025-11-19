
# SLHNET Botshop – מדריך פריסה מלא (שכבה ראשונה + שכבת רזרבות ומדדים)

מסמך זה מסביר בדיוק איך לפרוס את הפרויקט לשרת (למשל Railway) כך שהבוט, האתר וה-API יעבדו יחד,
וגם איך לוודא שמנגנון הרזרבות (49% מכל תשלום) נרשם ונמדד בצורה תקינה.

---

## 1. מה יש בפרויקט הזה?

הפרויקט כולל:

- בוט טלגרם Buy_My_Shop_bot מחובר ל-WebHook
- אתר נחיתה בכתובת https://slh-nft.com/ דרך תיקיית `docs/`
- FastAPI כשרת HTTP:
  - `/webhook` – לניהול עדכוני טלגרם
  - `/healthz` – בדיקת חיים
  - `/api/metrics/finance` – סטטוס כספי כולל (הכנסות, רזרבות, אישורים)
  - `/` – דף לנדינג בסיסי (אם יש templates)
- שכבת DB (Postgres) עם טבלאות:
  - `payments` – רישום תשלומים כולל סכום ורזרבות
  - `users`, `referrals`, `rewards`, `metrics` וכו'

---

## 2. שלב א' – הכנה לפני פריסה

### 2.1. דרישות

- חשבון Railway (או שרת דומה)
- Postgres מחובר (Railway מספק אוטומטית DATABASE_URL)
- טוקן לבוט טלגרם (BOT_TOKEN)
- כתובת Webhook תקפה (לדוגמה: `https://botshop-production.up.railway.app/webhook`)

### 2.2. קבלת הקוד

1. הורד את קובץ ה-ZIP מהצ'אט (`botshop_first_layer_20251119.zip` או חדש יותר).
2. חלץ אותו לתיקייה במחשב.
3. בתוך ה-ZIP יש תיקייה `botshop-main` – זו תיקיית הפרויקט.

אם אתה עובד מול GitHub:

```bash
# בתיקיית העבודה שלך
rm -rf botshop
mv botshop-main botshop
cd botshop

git init   # אם אין עדיין
git remote add origin https://github.com/osifeu-prog/botshop.git   # אם עדיין לא קיים
git add .
git commit -m "full-layer: bot + site + reserves + metrics"
git push -u origin main
```

---

## 3. שלב ב' – משתני סביבה (Env)

בשרת (Railway), ודא שמשתני הסביבה הבאים קיימים:

```env
BOT_TOKEN=******                # טוקן טלגרם
BOT_USERNAME="Buy_My_Shop_bot"  # שם הבוט המדויק

WEBHOOK_URL="https://botshop-production.up.railway.app/webhook"

ADMIN_DASH_TOKEN=******         # טוקן פנימי לדשבורד / future admin

DATABASE_URL=...                # מגיע מ-Postgres ב-Railway
DATABASE_PUBLIC_URL=...         # אם מוגדר

SUPPORT_GROUP_LINK="https://t.me/+1ANn25HeVBoxNmRk"

PAYBOX_URL="https://links.payboxapp.com/1SNfaJ6XcYb"
BIT_URL="https://www.bitpay.co.il/app/share-info?i=190693822888_19l4oyvE"
PAYPAL_URL="https://paypal.me/osifdu"

LANDING_URL="https://slh-nft.com/"
START_IMAGE_PATH="assets/start_banner.jpg"

PYTHONIOENCODING="UTF-8"
PYTHONPATH="/app"

TON_WALLET_ADDRESS="UQCr743gEr_nqV_0SBkSp3CtYS_15R_..."

ADMIN_ALERT_CHAT_ID="-1001748319682"
ADMIN_OWNER_IDS="224223270"

BUSINESS_GROUP_URL="https://t.me/+HIzvM8sEgh1kNWY0"
```

> חשוב: ב-Railway ודא שה-Service שמריץ את הבוט מקושר ל-Postgres דרך VARIABLE של DATABASE_URL.

---

## 4. שלב ג' – פריסה ב-Railway (או שרת דומה)

### 4.1. יצירת Service חדש (אם צריך)

1. ב-Railway: New Project → Deploy from GitHub → בחר את `osifeu-prog/botshop`.
2. ודא:
   - Build: `pip install -r requirements.txt`
   - Run: `python main.py` או `uvicorn main:app --host 0.0.0.0 --port $PORT`

### 4.2. חיבור Postgres

1. הוסף Postgres דרך Railway (אם עדיין לא קיים).
2. קישור: במסך Variables → לחץ על Postgres → Attach to service.
3. יווצר עבורך `DATABASE_URL` אוטומטית.

---

## 5. שלב ד' – מה קורה באתחול (init_schema + רזרבות)

באתחול השרת:

- `init_schema()` רץ פעם אחת:
  - יוצר טבלת `payments` אם לא קיימת.
  - מוסיף (עם `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) את השדות:
    - `amount`
    - `reserve_ratio`
    - `reserve_amount`
    - `net_amount`

אין צורך לעשות migration ידני – המערכת דואגת לעצמה.

כל קריאה ל-`log_payment(...)` כאשר משתמש שולח אישור תשלום:

- יוצרת שורה חדשה ב-`payments` עם:
  - `amount = 39.00`
  - `reserve_ratio = 0.49`
  - `reserve_amount = 39 * 0.49`
  - `net_amount = 39 - reserve_amount`
  - `status = 'pending'` עד לאישור אדמין.

---

## 6. שלב ה' – בדיקות אחרי פריסה

אחרי שהשרת עלה בהצלחה:

### 6.1. בדיקת בריאות

דפדפן / curl ל:

- `https://botshop-production.up.railway.app/healthz`

צפוי:

```json
{
  "status": "ok",
  "service": "slhnet-telegram-gateway",
  "timestamp": "...",
  "version": "2.0.0"
}
```

### 6.2. בדיקת מדדי כספים / רזרבות

- `https://botshop-production.up.railway.app/api/metrics/finance`

דוגמה לתגובה אפשרית:

```json
{
  "timestamp": "2025-11-19T13:00:00Z",
  "reserve": {
    "total_payments": 10,
    "total_amount": 390,
    "total_reserve": 191.1,
    "total_net": 198.9
  },
  "approvals": {
    "pending": 4,
    "approved": 6,
    "rejected": 0
  }
}
```

> המדדים תלויים בנתונים שמופיעים כבר ב-DB בפועל.

### 6.3. בדיקת אתר

- `https://slh-nft.com/` צריך לעלות דרך GitHub Pages / docs.
- בניווט פנימי ודא:
  - כפתור "תשלום 39 ₪" מצביע ל-Paybox.
  - אחרי קטע "מה קורה אחרי שאתה משלים תשלום 39 ?" תראה את המשפט:
    - "49% מכל תשלום נכנס אוטומטית לרזרבות המערכת..."

### 6.4. בדיקת בוט טלגרם

בצ'אט עם הבוט `@Buy_My_Shop_bot`:

1. שלח `/start` – אמור להופיע מסך פתיחה עם כפתור תשלום ופרטים.
2. שלח צילום אישור תשלום (או הודעה כפי שהבוט מצפה) – בדוק:
   - האם הודעת לוג מגיעה לקבוצת האדמין (`ADMIN_ALERT_CHAT_ID`).
   - האם נרשמת שורה חדשה בטבלת `payments` (אם יש לך גישה ל-Postgres, אפשר לבדוק ב-SQL).

---

## 7. מה לעדכן אחרי הפריסה

### 7.1. שינוי מחיר בעתיד (אם תרצה)

כרגע מוגדר 39₪ בקוד – גם באתר וגם בחישוב ה-DB.  
אם תרצה לשנות מחיר:

1. בקובץ `docs/index.html`:
   - חפש "תשלום 39" ועדכן לטקסט החדש (למשל 49, 59 וכו').

2. בקובץ `db.py` בפונקציה `log_payment`:
   - עדכן את הערך `39.00` ואת הפורמולה בהתאם:

   ```sql
   amount NUMERIC(12,2) -- זה הערך הממשי
   reserve_amount = amount * 0.49
   net_amount = amount - reserve_amount
   ```

   (אפשר לשדרג בעתיד שזה יהיה פרמטר מה-ENV, אבל כרגע קשיח כדי לשמור את השכבה יציבה.)

### 7.2. שינוי יחס רזרבה (49%)

אם בעתיד תרצה 40% / 60% וכו' – תעדכן:

- ב-DB (`reserve_ratio`, `reserve_amount`, `net_amount`)
- בטקסט השיווקי ב-`docs/index.html`.

---

## 8. עבודה בהמשך – שכבות מתקדמות

אחרי שהשכבה הראשונה יציבה ורצה (בוט + אתר + תשלום 39 + רזרבה 49%):

- אפשר להוסיף:
  - דשבורד Admin (HTML ב-`templates` + JS ב-`static/js/admin.js`) שמדבר עם `/api/metrics/finance`.
  - הרחבת API ל:
    - `/api/admin/payments`
    - `/api/admin/users`
  - אינטגרציה עמוקה יותר ל-SLH Token / BSC / TON.

היתרון: כל זה יושב כבר על בסיס יציב של:

- payments + reserves
- מדדים / metrics
- בוט פעיל עם לקוחות אמיתיים.

---

## 9. אם משהו נכשל

אם ה-Container ב-Railway נופל:

1. פתח את ה-Logs.
2. חפש:
   - שגיאות חיבור ל-DB (`DATABASE_URL`).
   - שגיאה ב-Telegram Webhook (`Webhook error: ...`).
   - שגיאה ב-init_schema (`init_schema failed: ...`).

לרוב:
- אם DATABASE_URL לא מוגדר → DB functions יהיו no-op (הבוט יוכל לתפקד חלקית, אך בלי רישום מלא).
- אם BOT_TOKEN שגוי → טלגרם לא יקבל הודעות.

---

זהו – זו השכבה הראשונה *המלאה* עם רזרבות, מדדים, אתר ובוט,
נבנתה כך שהיא יציבה ורצה, ומוכנה להתרחבות לשכבות הבאות.


---

## 10. שכבת ADVANCED – סימולציות, טוקנומיקה וניתוח סיכונים

הפרויקט כולל גם רואטר מתקדם בנתיב `/api/advanced` (קובץ `SLH/slh_advanced_api.py`), המממש חלקים מהתוכנית המלאה:

### 10.1. סימולציית תשואות

- `GET /api/advanced/yield/simulate`  
  פרמטרים:
  - `amount` – סכום השקעה בשקלים (חובה)
  - `months` – מספר חודשים (ברירת מחדל: 12)
  - `tier` – רמת משקיע: `pioneer/early/community/standard/vip`

ה-API מחזיר:
- `monthly_rate` – ריבית חודשית לפי tier (10% ל־pioneer, טווח 8–12% בהתאם ל-tier)
- `effective_apy` – תשואה שנתית אפקטיבית (אם `months >= 12`)
- `total_return` – סך רווח צפוי
- `total_with_principal` – קרן + רווח

### 10.2. טוקנומיקה (SLH / SELA)

- `GET /api/advanced/tokenomics/summary`

מחזיר:
- מחיר SELA משוער (444 ₪)
- יחס חלוקת SLH (1 SLH לכל 1 ₪)
- חלוקת הכנסות:
  - 30% קרן ערבויות
  - 30% פיתוח וטכנולוגיה
  - 20% קהילה ושיווק
  - 20% רווח ותשואות
- יחס רזרבה בפועל: 49% לכל תשלום (בהתאם למה שנרשם ב-payments)

### 10.3. רשת הפניות

- `GET /api/advanced/referrals/top?limit=10`  
  מחזיר את המפנים המובילים מתוך טבלת `referrals` בבסיס הנתונים.

### 10.4. ניהול סיכונים בסיסי

- `GET /api/advanced/risk/summary`

מבוסס על:
- סך התשלומים (`total_amount`)
- סך הרזרבות (`total_reserve`)
- סך הנטו (`total_net`)
- `diversification_index` – מדד פשטני לפיזור סיכון (יחס רזרבה/סך תשלומים)

---

## 11. שילוב עם דשבורד ה-Web

בדשבורד (`docs/dashboard/index.html`) נטענת ספריית `docs/js/dashboard.js`:

- היא קוראת אל:
  - `/api/metrics/finance` – נתונים כספיים גולמיים
  - ניתן להרחיב בקלות לקריאה גם אל:
    - `/api/advanced/yield/simulate`
    - `/api/advanced/tokenomics/summary`
    - `/api/advanced/risk/summary`

כך תוכל לבנות:

- דשבורד למשקיעים
- דשבורד פנימי לאדמין
- מצגות חיות על בסיס נתונים אמיתיים מהמערכת.



BOTSHOP – גרסת V11 (סטטיסטיקת START + תפריט אדמין + מסך פתיחה מעודכן)
====================================================================

מה חדש בגרסה הזו?
------------------
1. לוגים אמינים יותר לכל /start:
   * כל לחיצה על /start נרשמת כאירוע ב-referrals.json (start_events_total, starts_by_user, last_start_at).
   * נשלחת הודעת לוג גם ל-LOGS_GROUP_CHAT_ID וגם ל-ADMIN_ALERT_CHAT_ID (אם הוגדרו).

2. מסך פתיחה חדש ומשופר:
   * טקסט מפורט בשלושה–ארבעה חלקים, כפי שביקשת.
   * תמונת פתיחה מהנתיב: assets/start_banner.jpg (או מה-START_IMAGE_PATH ב-ENV אם הוגדר).
   * מקלדת עם כפתורים:
     - 🏦 תשלום בהעברה בנקאית (מציג פרטי חשבון הבנק של קאופמן צביקה).
     - 💎 תשלום ב-TON (מציג את כתובת הטון שלך).
     - 🧩 איך להגדיר ארנק TON (הסבר שלב-אחר-שלב).
     - ℹ️ מה אני מקבל בקהילה? (הסבר ערכי ותדמיתי).

3. תפריט אדמין חדש – /admin:
   * נגיש רק למי ש-id שלו מופיע במשתנה ADMIN_OWNER_IDS.
   * מציג:
     - מספר משתמשים רשומים (total_users מתוך referrals.json).
     - מספר לחיצות /start מצטבר (start_events_total).
     - זמן /start אחרון (last_start_at).
   * בנוסף מציג רשימת פקודות עיקריות של הבוט.

4. Healthz מורחב לדיבוג:
   * /health – כמו קודם (מצב כללי).
   * /healthz – מחזיר:
     - telegram_ready – האם הבוט הצליח לבצע getMe.
     - db_connected – האם החיבור ל-DB הצליח (אם קיים מודול db עם get_session).
     - details – כולל bot_username, bot_id, admin/chat ids ועוד.

מה לעדכן ב-Railway?
--------------------
חובה:
1. BOT_TOKEN – הטוקן של @Buy_My_Shop_bot.
2. WEBHOOK_URL – למשל:
   https://botshop-production.up.railway.app/webhook
3. ADMIN_OWNER_IDS – לדוגמה:
   224223270
   (אפשר גם רשימה עם פסיקים/רווחים, המערכת תאתר את כל המספרים).

מומלץ:
4. ADMIN_ALERT_CHAT_ID – chat_id של קבוצת האדמינים/לוגים (הבוט חייב להיות חבר בקבוצה).
5. LOGS_GROUP_CHAT_ID – אם רוצים קבוצה נפרדת ללוגים; אם לא, אפשר להשאיר ריק והשדה ישתמש ב-ADMIN_ALERT_CHAT_ID.
6. START_IMAGE_PATH – נתיב יחסי לתמונה, למשל:
   assets/start_banner.jpg

איך לעדכן את ה-chat_id של קבוצת הלוגים?
----------------------------------------
1. הוסף את הבוט לקבוצה.
2. שלח לקבוצה הודעה כלשהי.
3. השתמש בבוט @RawDataBot או בכלי אחר כדי לקבל את ה-chat_id של הקבוצה.
   (זה ייראה כמו -1001748319682).
4. ב-Railway:
   - הגדר ADMIN_ALERT_CHAT_ID לערך הזה, לדוגמה:
     -1001748319682
   - אם תרצה, הגדר גם LOGS_GROUP_CHAT_ID לאותו ערך או לקבוצה אחרת.

הערה: בקוד החדש יש פונקציית _parse_chat_id שמוציאה את המספר מתוך מחרוזת,
גם אם הכנסת בטעות תווים נוספים מסביב.

איך לפרוס את הגרסה החדשה?
--------------------------
1. מחק את כל הקבצים הקיימים בתיקיית הפרויקט המקומית של BOTSHOP (או גבה אותם).
2. חלץ את קובץ ה-zip החדש לתיקייה.
3. ודא שהתיקייה assets/start_banner.jpg קיימת ושם התמונה מתאים.
4. דחוף את הקוד ל-GitHub (אם אתה עובד עם Git),
   או העלה את הקבצים ישירות ל-Railway אם אתה מעדיף.
5. ב-Railway:
   - ודא שכל משתני הסביבה (ENV) מוגדרים כנדרש.
   - לחץ Redeploy לשירות botshop.

בדיקות מהירות אחרי פריסה:
-------------------------
1. בקר ב:
   https://botshop-production.up.railway.app/healthz
   ודא שאתה מקבל JSON עם:
   - "status": "ok"
   - "telegram_ready": true
   - "db_connected": true או false (תלוי אם יש DB)
   - details עם bot_username וכו'.

2. פתח את הבוט בטלגרם:
   - שלח /start כמה פעמים מחשבונות שונים (או לפחות פעמיים מאותו חשבון).
   - ודא:
     * שאתה מקבל את כל 4 ההודעות הטקסטואליות.
     * שהתמונה מוצגת (אם קיים קובץ).
     * שהכפתורים מופיעים:
       🏦 תשלום בהעברה בנקאית
       💎 תשלום ב-TON
       🧩 איך להגדיר ארנק TON
       ℹ️ מה אני מקבל בקהילה?

3. לחץ על כל אחד מהכפתורים:
   - ודא שאתה מקבל את ההסברים הנכונים.

4. כנס כ-ADMIN ושלח /admin:
   - ודא שאתה רואה את הסטטיסטיקות (total_users, start_events_total, last_start_at).

5. בדוק בקבוצת הלוגים (ADMIN_ALERT_CHAT_ID / LOGS_GROUP_CHAT_ID):
   - כל /start אמור לייצר הודעה חדשה עם פרטי המשתמש וה-referrer.

אם משהו לא ברור או תרצה להרחיב את פאנל האדמין (למשל להוסיף /broadcast, /export, /debug),
אפשר להמשיך משגרה זו ולהוסיף פונקציות נוספות.


# Buy My Shop – Telegram Gateway Bot

בוט טלגרם שמשמש כ"שער כניסה" לקהילת עסקים, עם:

- תשלום חד־פעמי (39 ₪) במספר ערוצים (בנק, פייבוקס, ביט, PayPal, TON).
- אישור תשלום ידני + שליחת קישור לקהילת העסקים.
- העברת לוגים של תשלומים לקבוצת ניהול.
- תמונת שער עם מונים (כמה פעמים הוצגה, כמה עותקים נשלחו אחרי אישור).
- תפריט אדמין עם סטטוס מערכת, מונים ורעיונות לפיתוח עתידי.
- אינטגרציה אופציונלית ל-PostgreSQL דרך `db.py`.
- דף נחיתה סטטי ב-GitHub Pages לשיתוף ברשתות:
  - `https://osifeu-prog.github.io/botshop/`

## קבצים עיקריים

- `main.py` – לוגיקת הבוט + FastAPI + webhook + JobQueue.
- `requirements.txt` – ספריות נדרשות.
- `Procfile` – פקודת הרצה ל-PaaS (Railway).
- `.gitignore` – הגדרות גיט.
- `assets/start_banner.jpg` – תמונת שער ל-/start (הבוט משתמש בה).
- `docs/index.html` – דף נחיתה ל-GitHub Pages (עם Open Graph לתמונה).
- `db.py` (אופציונלי) – חיבור ל-PostgreSQL ללוגים של תשלומים.
- `.env.example` – דוגמה למשתני סביבה.

## משתני סביבה (Railway → Variables)

חובה:

- `BOT_TOKEN` – הטוקן שקיבלת מ-@BotFather.
- `WEBHOOK_URL` – ה-URL המלא של ה-webhook, לדוגמה:  
  `https://webwook-production-4861.up.railway.app/webhook`

אופציונלי, אבל מומלץ:

- `PAYBOX_URL` – לינק תשלום לפייבוקס (אפשר להחליף מדי פעם).
- `BIT_URL` – לינק תשלום לביט.
- `PAYPAL_URL` – לינק ל-PayPal.
- `LANDING_URL` – לינק לדף הנחיתה (ברירת מחדל: GitHub Pages).
- `START_IMAGE_PATH` – נתיב לתמונת השער (ברירת מחדל: `assets/start_banner.jpg`).
- `DATABASE_URL` – אם משתמשים ב-PostgreSQL (מבנה: `postgres://user:pass@host:port/dbname`).

## הרצה לוקאלית

```bash
python -m venv .venv
source .venv/bin/activate  # ב-Windows: .venv\Scripts\activate
pip install -r requirements.txt

# הגדרת משתני סביבה לדוגמה:
export BOT_TOKEN="123:ABC"
export WEBHOOK_URL="https://your-public-url/webhook"

uvicorn main:app --host 0.0.0.0 --port 8000
