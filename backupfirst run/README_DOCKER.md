# Botshop deploy quick guide

## Option A (Railpack + start.sh)
- אם הגדרת Root Directory = /bot → בהגדרת Deploy שים Custom Start Command: sh ./start.sh (מומלץ; לא דורש chmod).
- אם Root Directory = / (או ריק) → Redeploy; Railpack ימצא ./start.sh בשורש.

## Option B (Custom Start Command ללא start.sh)
- Root Directory = /bot, והגדר Start Command: python -m bot.main.

## Option C (Docker)
- השאר Root ריק// ותן ל-railway.toml לבנות מדוקר.

### Variables (Railway)
TELEGRAM_BOT_TOKEN  (חובה)
LOG_LEVEL=INFO
ADMIN_NAME=Osif
ADMIN_IDS=224223270
ENTRY_PRICE_NIS=39
STORE_PATH=/data/store.json
GROUP_CHAT_ID=-1002981609404
GROUP_INVITE_LINK=https://t.me/+HIzvM8sEgh1kNWY0