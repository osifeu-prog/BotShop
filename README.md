# BotShop – גרסת FIX מלאה (2025‑11‑19)

החבילה הזו נועדה לתת לך בסיס יציב לבוט *Buy_My_Shop* על Railway, כולל:

- `main.py` מתוקן:
  - ייבוא מודולים נכון (`slh_public_api`, `slhnet_extra`, `social_api`, `SLH/slh_core_api`).
  - זרימת `/start` שיווקית ל־39 ₪ עם כפתורי תשלום + מידע.
  - פקודה `/chatinfo` למציאת `chat_id` של כל צ׳אט שבו הבוט נמצא.
- `db.py` מתוקן:
  - ללא בלוק הקוד השבור שגרם ל־`SyntaxError`.
  - הגדרת סכמה (`_init_schema_slhnet`) לכל הטבלאות של תשלומים, משתמשים, referrals ו־social posts.
- `templates/landing.html` + `static/` – דף נחיתה בסיסי שניתן להחלפה או שיפור.
- `docs/` – האתר הישן שלך (לשימור / שילוב עתידי).

---

## 1. מבנה התיקייה

לאחר חילוץ הזיפ:

```text
botshop-main/
  main.py
  db.py
  Procfile
  requirements.txt
  SLH/
  slh/
  social_api.py
  templates/
    landing.html
  static/
  docs/
  assets/
  bot_messages_slhnet.txt
```

עבור Git + Railway מומלץ שה־root של הריפו יהיה `botshop-main`.

---

## 2. משתני סביבה נדרשים ב‑Railway

בשירות `botshop`:

חובה:

- `BOT_TOKEN` – טוקן הבוט מטלגרם.
- `WEBHOOK_URL` – ה‑URL המלא שבו Railway חושף את השירות, למשל:  
  `https://botshop-production.up.railway.app/webhook`
- `DATABASE_URL` – כתובת החיבור לפוסטגרס (מתוך Service Postgres ב‑Railway).

מומלץ מאוד:

- `LANDING_URL` – דף הנחיתה הראשי (ברירת מחדל `https://slh-nft.com`).
- `PAYBOX_URL` – קישור לתשלום 39 ₪ (PayBox).
- `BIT_URL` – קישור לתשלום Bit (אם יש).
- `PAYPAL_URL` – אם אתה מוכר גם לחו״ל.
- `BUSINESS_GROUP_URL` – קישור לטלגרם של קהילת העסקים (לשורה השלישית בכפתורים).
- `GROUP_STATIC_INVITE` – קישור גיבוי לקבוצה (אם BUSINESS_GROUP_URL ריק).
- `START_IMAGE_PATH` – נתיב לתמונה שתופיע במסך הפתיחה (ברירת מחדל: `assets/start_banner.jpg`).

ללוגים ואדמינים:

- `ADMIN_ALERT_CHAT_ID` – `chat_id` של קבוצת לוגים / אדמינים (מספר, למשל `-1001234567890`).
- `ADMIN_OWNER_IDS` – רשימת `user_id` של אדמינים, מופרדת בפסיקים, למשל:  
  `224223270,5010371391`

---

## 3. בדיקות בריאות – /healthz ו‑/meta

### 3.1 לוקאלית

1. צור venv והתקן תלויות:

```bash
cd botshop-main
python -m venv .venv
source .venv/bin/activate   # ב-Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. הגדר מינימום ENV:

```bash
export BOT_TOKEN=XXXXXXXX:YYYYYYYYYYYY       # ב-Windows: set BOT_TOKEN=...
export WEBHOOK_URL=http://127.0.0.1:8080/webhook
# אם יש לך Postgres מקומי:
# export DATABASE_URL=postgresql://user:pass@localhost:5432/botshop
```

3. הרץ את השרת:

```bash
uvicorn main:app --reload --port 8080
```

4. בדוק בדפדפן / בעזרת curl:

- `http://127.0.0.1:8080/healthz` יחזיר JSON מסוג:

```json
{
  "status": "ok",
  "telegram_ready": true/false,
  "db_connected": true/false
}
```

- `http://127.0.0.1:8080/meta` יחזיר:

```json
{
  "bot_username": "Buy_My_Shop_bot",
  "webhook_url": "https://.../webhook",
  "community_group_link": "...",
  "support_group_link": "..."
}
```

אם אחד מהם מחזיר 500 – הלוג בטרמינל יסביר בדיוק מה חסר.

---

### 3.2 על Railway

לאחר Deploy מוצלח:

- כנס ל‑`https://botshop-production.up.railway.app/healthz`  
  (להחליף לדומיין האמיתי של השירות שלך).
- כנס ל‑`https://botshop-production.up.railway.app/meta`.

אם `telegram_ready=false` – כנראה שיש בעיה עם `BOT_TOKEN`.  
אם `db_connected=false` – `DATABASE_URL` לא מוגדר או לא נכון.

---

## 4. מציאת chat_id דרך /chatinfo

1. ודא שהשירות `botshop` רץ (healthz תקין).
2. הוסף את הבוט לקבוצת הלוגים שלך בטלגרם (או לכל קבוצה אחרת).
3. בקבוצה הזו כתוב:

```text
/chatinfo
```

הבוט יענה עם:

```text
chat_id: -100XXXXXXXXXX
סוג: supergroup
כותרת: ...
```

4. קח את הערך הזה, חזור ל‑Railway → Service `botshop` → Variables, והגדר:

- `ADMIN_ALERT_CHAT_ID = -100XXXXXXXXXX`

5. עשה Redeploy נוסף. מעכשיו כל לוג של /start או אישור תשלום יישלח לקבוצה הזו.

---

## 5. זרימת /start ל‑39 ₪ (שיווקית)

כאשר משתמש שולח `/start`:

1. `send_start_screen`:
   - מטעין טקסטים מ‑`bot_messages_slhnet.txt` (בלוקים `START_TITLE` ו‑`START_BODY`)  
     אם קובץ חסר – משתמש בברירות מחדל שיווקיות.
   - מנסה לשלוח תמונה (`START_IMAGE_PATH`) ככותרת השער.
   - מוסיף שלושה כפתורים:
     - `💳 תשלום 39 ₪ וגישה מלאה` → `PAYBOX_URL` או `LANDING_URL#join39`.
     - `ℹ️ לפרטים נוספים` → `LANDING_URL`.
     - `👥 הצטרפות לקבוצת העסקים` → `BUSINESS_GROUP_URL` או `GROUP_STATIC_INVITE`.
2. רושם לוג ל‑`ADMIN_ALERT_CHAT_ID` עם פרטי המשתמש + referrer (אם הגיע עם payload).

כדי לשפר את המסר השיווקי, פשוט ערוך את הקובץ:

```text
bot_messages_slhnet.txt
```

וחפש את הבלוקים:

```text
[START_TITLE]
...

[END_START_TITLE]

[START_BODY]
...

[END_START_BODY]
```

החלף אותם בטקסט שלך (הנוכחי, עם הדגשה על 39 ₪ והערך של הקהילה).

---

## 6. חיבור לפוסטגרס ב‑Railway

1. צור Service מסוג Postgres (אם עוד לא קיים).
2. בתוך Service Postgres, העתיק את ה‑`DATABASE_URL` שהוא נותן לך.
3. עבור לשירות `botshop` → Variables → הוסף:

- `DATABASE_URL = <ה‑URL שהעתקת>`

4. Redeploy.

ב‑startup, הפונקציה `_init_schema_slhnet()` יוצרת לבד את כל הטבלאות הדרושות:

- `payments`
- `users`
- `referrals`
- `rewards`
- `metrics`
- `posts`

---

אם משהו עדיין נופל, תוכל לשלוח את הלוגים ואעזור לכוון נקודתית – אבל החבילה הזו אמורה לתת לך בסיס יציב:  
בוט טלגרם + API + Postgres + דף נחיתה, מוכנים לצמיחה של כל הכלכלה סביב ה‑39 ₪. 
