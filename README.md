# Digital Assets Ecosystem / BOTSHOP

Production-ready FastAPI + Telegram Bot service for managing digital assets, referrals and marketing networks.

## ENV alignment with your Railway service

הקוד תומך ישירות בכל המשתנים שיש לך כבר על השרת:

- BOT_TOKEN
- BOT_USERNAME
- WEBHOOK_URL (מכוון ל-/webhook שתואם לקוד)
- ADMIN_DASH_TOKEN
- DATABASE_URL
- DATABASE_PUBLIC_URL (לא חובה)
- COMMUNITY_GROUP_LINK
- SUPPORT_GROUP_LINK
- PAYBOX_URL
- BIT_URL
- PAYPAL_URL
- LANDING_URL
- START_IMAGE_PATH
- TON_WALLET_ADDRESS
- (PYTHONIOENCODING, PYTHONPATH, your_password – לא נדרשים בקוד, אבל לא מזיקים אם קיימים)

## GitHub Pages – תיקיית DOCS

התיקייה `docs/` בפרויקט משמשת לאתר שיווקי סטטי ל-GitHub Pages.

- GitHub: Settings → Pages → Source = `Deploy from a branch` → `main` + folder `docs`.
- GitHub יציג את `docs/index.html` כלנדינג.

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env  # עדכן לערכים האמיתיים שלך
psql "$DATABASE_URL" -f database_schema.sql

uvicorn main:app --reload
```

בדיקות:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/api/docs`

## Railway

1. העלה לגיטהאב
2. Railway → New Project → GitHub → בחר Repo
3. Variables – הזן את אותם ערכים שכבר יש לך (כמו ברשימה למעלה)
4. ודא שה-Build מצליח
5. בדוק:

   - `https://<service>.up.railway.app/health`
   - `/api/docs`

6. בוט:

   - ודא שתהליך `bot` רץ
   - שלח `/start` לבוט → אמור להחזיר הודעת Welcome עם כל הלינקים שלך.
