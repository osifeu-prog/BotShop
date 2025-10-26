# Botshop – Railway bootstrap

תצורה שעובדת גם אם Root Directory = "/" וגם אם Root Directory = "/bot".

## מה חשוב ב-Railway
- **Builder**: Railpack (Default)
- **Root Directory**:
  - מומלץ: **/bot**
  - לחלופין: ריק/"/" (עובד כי יש קבצים גם ב-root וגם ב-/bot)
- **Custom Start Command**: להשאיר **ריק** (Railway יקרא את ה-Procfile)
- **Variables**: 
  - TELEGRAM_BOT_TOKEN (חובה)
  - LOG_LEVEL=INFO (מומלץ להתחלה)

## דיפלוי
1) git add -A && git commit -m "bootstrap botshop dual-root" && git push
2) Railway → Redeploy. חפש בלוגים:
   - Detected Python → Using pip → pip install -r requirements.txt
   - Starting polling…
3) שלח /start לבוט: תקבל "Botshop is alive ✅".