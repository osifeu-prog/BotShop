# Botshop (Railway)

## Railway Settings
- **Root Directory**: /bot
- **Builder**: Railpack (Default)
- **Custom Start Command**: השאר ריק (Railway יקרא את Procfile)
- **Public Networking**: Port 8080 (לא חובה לשנות, זה בוט Polling)

## Required Variables
- TELEGRAM_BOT_TOKEN
- LOG_LEVEL=INFO
(אחרים לא נחוצים לשלב ההרמה הראשוני)

## Deploy flow
1) git add -A && git commit -m "botshop bootstrap" && git push
2) ב-Railway: Redeploy. בלוגים תראה:
   - Detected Python → Using pip → pip install -r requirements.txt
   - Starting polling…
3) בטלגרם: שלח /start לבוט ובדוק "Botshop is alive ✅".