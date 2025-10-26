# SLH Botshop (Docker + Railway)

This repo builds a Telegram bot (python-telegram-bot v20) with Docker.
- Reply Keyboard (קבוע) למשתמשים
- /price, /approve למנהלים
- הצגת אפשרויות תשלום (בנק, PayPal, ביט/פייבוקס, TON)
- שמירת משתמשים ב/data/store.json (בContainer)

## Files
- botshop/Dockerfile
- botshop/railway.toml  (forces Railway to use Dockerfile)
- botshop/requirements.txt
- botshop/botshop/*.py  (app code)
- botshop/.env.example  (variables template)

## Local run
1) copy `.env.example` -> `.env` and fill TELEGRAM_BOT_TOKEN
2) docker build -t botshop ./botshop
3) docker run --rm -e TELEGRAM_BOT_TOKEN=xxx -e ADMIN_IDS=224223270 -p 8080:8080 -v %cd%/botshop/data:/data botshop

## Railway
- Connect GitHub repo
- Ensure these *Service Variables* exist (no secrets in git):
  TELEGRAM_BOT_TOKEN, LOG_LEVEL, ADMIN_IDS, ADMIN_NAME, ENTRY_PRICE_NIS,
  DEMO_GRANT_SLH, DEMO_GRANT_BNB, STORE_PATH=/data/store.json,
  GROUP_CHAT_ID, GROUP_INVITE_LINK
- Redeploy: Railway will read `railway.toml` and build from `botshop/Dockerfile`.