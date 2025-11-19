
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
