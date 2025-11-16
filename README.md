📦 BOTSHOP – README
מערכת קהילה + תשלום + בוט טלגרם + API FastAPI
עדכון: 16/11/2025

---

## 🚀 מצב הפרויקט כרגע

הפרויקט כולל:

### 1. שרת API מבוסס FastAPI (botshop – Gateway)

- קובץ ראשי: `main.py`
- ריצה על Railway עם `uvicorn`
- נתיבי מערכת:
  - `GET /health` – בדיקת חיים ל-Railway
  - `POST /webhook` – נקודת כניסה לעדכוני טלגרם
  - `GET /admin/stats` – סטטוס אדמין (DB, תשלומים, מפנים)
- אינטגרציה ל־PostgreSQL דרך `db.py`:
  - לוג תשלומים
  - מונים וביצועים
  - הפניות (referrals)
- מודולי הרחבה:
  - `slh_public_api.py` – תצורת טוקן / מחיר / קישורי תשלום / `/api/token/*`
  - `social_api.py` – פיד פוסטים בסיסי ל־Front (`/api/posts`)
  - `slh_core_api.py` – לוגיקת ליבה (רפרלים, משתמשים)
  - `slhnet_extra.py` – כלים משלימים (תצוגה חיצונית, קונפיג ועוד)

### 2. בוט טלגרם מלא – Buy_My_Shop_bot

- טיפול בפקודת `/start` – שער הכניסה לקהילה.
- רישום משתמש חדש (כולל טיפול ב־deep-link להפניה).
- שכבת הרשמה:
  - תשלום חד־פעמי 39 ₪ (PayBox / ביט / PayPal / TON).
  - שליחת צילום אישור תשלום.
  - לוג תשלומים לקבוצת ניהול.
  - אישור/דחייה ידניים על ידי אדמין (כפתורים ולוגיקת `/approve` / `/reject`).
  - לאחר אישור – שליחת קישור לקבוצת העסקים.
- ניהול מפנים (referrals) ברמת בוט ו-DB.
- תפריט תמיכה: שליחת פניות לקבוצת תמיכה, עם אפשרות לאנשי צוות לחזור למשתמש בפרטי.

### 3. פרויקט רץ ב-Railway

- Deploy אוטומטי מ-GitHub: `osifeu-prog/botshop`.
- Healthcheck מוגדר על `/health`.
- Webhook לטלגרם מוגדר על:
  - `WEBHOOK_URL=https://webwook-production-4861.up.railway.app/webhook`
- שירות PostgreSQL מחובר דרך `DATABASE_URL`.

---

## 🔧 התיקונים האחרונים (16/11/2025)

### ✔ תיקון BIT_URL – ללא קריסת Inline Button

- בעבר: `BIT_URL` שימש ישר כ-URL לכפתור "תשלום בביט".
- כאשר הוגדר במספר טלפון (למשל `054...`) – טלגרם זרק שגיאה `BadRequest: ... wrong http url`.
- כעת:
  - אם `BIT_URL` מתחיל ב-`http://` או `https://` → יוצג ככפתור תקין.
  - אם `BIT_URL` הוא מספר טלפון בלבד → לא נוצר כפתור URL (הבוט לא קורס), והמספר מוצג בטקסט ההסבר לתשלום.

### ✔ חיבור מלא של ה־Routers ל-API

נוסף חיבור של:

- `slh_public_api.router` → `/api/token/price`, `/api/token/sales`, `/api/config`, ועוד.
- `social_api.router` → `/api/posts`
- `slh_core_api.router` → נקודות לוגיקה פנימית (רפרלים/משתמשים).
- `slhnet_extra.router` → נתיבי קונפיג/מידע משלימים.

כך הקריאות מהאתר (`/api/token/sales`, `/api/posts`) מקבלות תשובה תקינה (200) ולא 404.

### ✔ שמירה על מבנה פרויקט נקי (ZIP + Git)

- טופלו BOM ותווים שבורים בקבצים:
  - `db.py`
  - `slh_token.py`
  - `slhnet_extra.py`
- בוצעה בדיקת קומפילציה:
  - `python -m py_compile main.py db.py slh_token.py slhnet_extra.py slh_public_api.py slh_core_api.py social_api.py`
- בוצעה בדיקת import:
  - `python -c "import main"`

---

## 📂 מבנה פרויקט עדכני

```text
botshop-main/
│
├── main.py                 # FastAPI + Telegram Bot + webhook + admin endpoints
├── db.py                   # PostgreSQL (לוג תשלומים, מונים, רפרלים)
├── slh_token.py            # תשתית טוקן SLH / בלוקצ'יין (BSC, עתידי)
├── slh_public_api.py       # /api/token/* + קושרי תשלום ציבוריים
├── slhnet_extra.py         # API משלים (קונפיג, מידע קהילה)
├── slh_core_api.py         # לוגיקת ליבה (משתמשים, referrals)
├── social_api.py           # /api/posts (פיד דמו)
│
├── requirements.txt        # ספריות Python
├── Procfile                # פקודת הרצה ל-Railway (uvicorn main:app)
├── README.md               # קובץ זה
├── bot_messages_slhnet.txt # טקסטים לבוט /start וכדומה
│
├── assets/
│   └── start_banner.jpg    # תמונת שער
├── templates/
│   └── landing.html        # טמפלייט (לא בשימוש ישיר כרגע)
├── static/
│   └── slh-og.svg          # אייקון/OpenGraph
└── docs/
    ├── index.html          # דף נחיתה סטטי ל-GitHub Pages
    ├── bot_messages_slhnet.txt
    ├── CNAME
    └── specs/
        └── social-logic.md
```

---

## 🌐 נתיבי API חשובים (botshop – Gateway)

נתיב | תיאור
---- | ----
`GET /health` | בדיקת חיים ל-Railway (ניטור)
`POST /webhook` | כניסת עדכוני טלגרם לבוט
`GET /admin/stats` | סטטוס מערכת עבור האדמין
`GET /api/token/price` | מחיר SLH ב-NIS (מבוסס `SLH_NIS`)
`GET /api/token/sales` | רשימת מכירות (כרגע דמו ריק, כדי שה-Front לא ייפול)
`GET /api/posts` | פוסטים דמו לפיד
נתיבים נוספים | ממומשים ב-`slh_core_api.py`, `slhnet_extra.py` לתרחישים עתידיים

---

## 🔗 שירותי API נוספים (Shop System + TON)

### 1. SLH Shop System (נפרד מהבוט)

מערכת חנויות/הזמנות נפרדת שרצה על:

- בסיס כתובת: `https://slhshopsystem-production.up.railway.app`
- דוקומנטציה: `/docs`

Endpoints עיקריים:

- `/users/telegram-sync`
- `/shops`, `/shops/{shop_id}`, `/shops/{shop_id}/items`, `/shops/{shop_id}/items`
- `/orders`, `/orders/{order_id}`
- `/payments/upload-proof`
- וכו׳ – לפי ה-Swagger.

בשלב זה **לא משנים** את המערכת הזו מתוך `botshop-main`. היא ממשיכה לרוץ כ־Microservice נפרד. אפשר בהמשך לחבר את הבוט למערכת זו דרך קריאות HTTP.

### 2. מערכת TON (חוזה על TON + בוט ייעודי)

קיים חוזה פעיל על רשת TON ובוט מקביל שמטפל בו.  
בהתאם לדרישה – **לא נוגעים כרגע במערכת TON** ולא משנים אותה מתוך פרויקט זה.  
הבוט הנוכחי הוא *שער הרשמה ותשלום 39 ₪* בלבד, לא ניהול החוזה.

---

## ⚙️ משתני סביבה (ENV – Railway)

להגדיר בשירות `botshop`:

חובה:

- `BOT_TOKEN` – טוקן הבוט הראשי (Buy_My_Shop_bot).
- `WEBHOOK_URL` – URL מלא ל-webhook, לדוגמה:  
  `https://webwook-production-4861.up.railway.app/webhook`
- `DATABASE_URL` – מחרוזת חיבור ל-PostgreSQL (Railway Postgres).

תשלומים:

- `PAYBOX_URL` – קישור PayBox לתשלום 39 ₪.
- `BIT_URL` – **אם זה URL** (של ביט) → יופיע ככפתור.  
  **אם זה מספר טלפון** (למשל `054...`) → יוצג בטקסט בלבד, בלי לקרוס.
- `PAYPAL_URL` – קישור PayPal לתשלום.

קבוצות / קישורים:

- `LANDING_URL` – דף נחיתה ראשי, כרגע: `https://slh-nft.com`
- `BUSINESS_GROUP_URL` / `GROUP_STATIC_INVITE` – קישור לקבוצת העסקים (משלמים):
  - כרגע: `https://t.me/+HIzvM8sEgh1kNWY0`
- `SUPPORT_GROUP_LINK` (אם תרצה להפוך ל-ENV) – קישור לקבוצת תמיכה:
  - כרגע בקוד: `https://t.me/+1ANn25HeVBoxNmRk`

לוגים ואדמינים (בקוד כרגע קבועים):

- `PAYMENTS_LOG_CHAT_ID` – קבוצת לוגים ותשלומים:
  - כרגע בקוד: `-1001748319682` (מתאים לקבוצת `https://t.me/+aww1rlTDUSplODc0`).
- `DEVELOPER_USER_ID` – הטלגרם ID שלך, לקבלת נפילות/אזהרות.

ערכים נוספים:

- `SLH_NIS` – מחיר ברירת מחדל של SLH בש״ח (ברירת מחדל בקוד: `444`).
- `GIT_REPO_URL` – `https://github.com/osifeu-prog/botshop.git`
- `OPENAI_API_KEY`, `HF_TOKEN`, ועוד – תשתיות AI (לא חובה לשכבת ההרשמה).

---

## 🧪 בדיקות לפני פריסה

במחשב מקומי (בתוך venv):

```bash
python -m pip install -r requirements.txt

python -m py_compile main.py db.py slh_token.py slhnet_extra.py slh_public_api.py slh_core_api.py social_api.py
python -c "import main"
```

אם שתי הפקודות האחרונות עוברות בלי שגיאה:

- השרת מוכן ל-Railway.
- הבוט וה-API יעברו את ה-healthcheck.

---

## 🚢 פריסה ל-Railway (סיכום קצר)

1. לוודא שגיט מעודכן:

```bash
git add .
git commit -m "botshop: stable gateway + API routers + BIT_URL fix"
git push origin main
```

2. Railway מחובר ל-`osifeu-prog/botshop` → יתבצע Deploy אוטומטי.
3. לבדוק בלוגים:
   - שאין יותר `BadRequest: ... wrong http url`.
   - שקריאות ל-`/api/token/sales` ו-`/api/posts` מחזירות 200.
4. לבדוק בדפדפן:
   - `https://webwook-production-4861.up.railway.app/health`
   - `https://webwook-production-4861.up.railway.app/api/token/sales`
   - `https://webwook-production-4861.up.railway.app/api/posts`

---

## 🧭 מטרות להמשך (Roadmap)

### שלב 1 – יציבות מלאה (Bot Gateway)

- לוודא שכל זרימת התשלום 39 ₪ עובדת:
  - `/start` → בחירת תשלום → שליחת אישור → לוג בקבוצת לוגים → אישור → קישור לקבוצת העסקים.
- ניטור לוגים וקונפיג על בסיס feedback מהמשתמשים הראשונים.

### שלב 2 – חיבור מודול החנויות (Shop System)

- לחבר את הבוט אל `slhshopsystem-production.up.railway.app` דרך endpoints:
  - יצירת משתמש/חנות לכל נרשם.
  - יצירת הזמנה (order) ויצירת פריטים (items) מהבוט.
- חיבור תיעוד מלא של מי רכש, איזו חנות נפתחה, ואיזה referral הביא אותו.

### שלב 3 – חיבור TON + Staking + Social-Fi

- שמירת address של TON כחלק מפרטי המשתמש (דרך /users/telegram-sync או שירות נפרד).
- חיבור ל-bot TON הקיים לצורך staking / airdrops.
- שילוב המידע על החזקת SLH / פעילות בקהילה במודל ניקוד ותגמולים.

---

## 🎯 סיכום

- הפרויקט חוזר להיות **יציב, קריא ומוכן לפיתוח המשך**.
- שכבת ההרשמה 39 ₪ + תיעוד תשלומים + לוגים לקבוצת הניהול – מוכנה ואחודה.
- האתר `https://slh-nft.com` יכול לצרוך את `/api/token/*` ו-`/api/posts` מהשירות הזה בלי 404.
- שירות ה-Shops והחוזה על TON נשארים מבודדים, ואפשר בהמשך לחבר אותם בצורה מסודרת מהבוט ומה-API.
