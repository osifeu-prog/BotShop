# SLHNET Telegram Gateway – Enterprise Pack

זהו פרויקט Python מלא שמוכן לדחיפה ל‑Git ולהעלאה ל‑Railway כשער טלגרם מתקדם
עבור Buy_My_Shop / SLH / SELA – כולל:

- FastAPI + python‑telegram‑bot (async, webhook)
- הגנת SPAM ו‑duplicate updates
- Rate limiting ל‑/webhook
- Health checks בסיסיים ומורחבים
- metrics ל‑Prometheus
- חיבור אופציונלי ל‑Postgres למדדי אישורים / Reserve
- מערכת הודעות חכמה מ‑messages/messages.md
- תפריט /start מלא שמציג את עולם ההשקעות והחיסכון שלך

## איך מרימים מקומית

```bash
python -m venv .venv
source .venv/bin/activate  # ב‑Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# עדכן BOT_TOKEN, WEBHOOK_URL, ADMIN_ALERT_CHAT_ID וכו'

uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## פריסה ל‑Railway

1. צור שירות חדש מסוג Python והצב את root של ה‑repo הזה.
2. ודא שיש משתנה סביבה `PORT` (Railway מוסיף לבד).
3. קבע פקודת הרצה:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
4. עדכן ENV:
   - `BOT_TOKEN`
   - `WEBHOOK_URL=https://<your-service>.up.railway.app/webhook`
   - `ADMIN_ALERT_CHAT_ID` (לדוגמה: 224223270)
   - אופציונלי: `DATABASE_URL`

אחרי הדיפלוי:
- בדוק `GET /healthz`
- בדוק `GET /health/detailed`
- הגדר webhook בבוט (אם אינך עושה זאת אוטומטית):
  ```bash
  curl -X POST "https://api.telegram.org/bot<token>/setWebhook"        -d "url=https://<your-service>.up.railway.app/webhook"
  ```

משם – כל /start בבוט אמור להציג את ההודעה המלאה ואת כפתורי התשלום / קהילה.
