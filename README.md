# Botshop

Minimal, production-ready Telegram bot scaffold for Railway (Railpack/Nixpacks).

## Deploy (Railway)

1) **Settings → Source → Root Directory** = `/bot`.
2) **Deploy → Custom Start Command** = `sh start.sh` (or leave empty – Procfile included).
3) Variables (Service → Variables):
   - `TELEGRAM_BOT_TOKEN`
   - `LOG_LEVEL` = `INFO`
   - `ADMIN_IDS` = `224223270`
   - `ADMIN_NAME` = `Osif`
   - `ENTRY_PRICE_NIS` = `39`
   - `STORE_PATH` = `/data/store.json`
   - `GROUP_CHAT_ID` = `-1002981609404`
   - `GROUP_INVITE_LINK` = `https://t.me/+HIzvM8sEgh1kNWY0`
   - optional: `DEMO_GRANT_SLH` = `39`, `DEMO_GRANT_BNB` = `0.05`, `PAYMENT_LINK_BASE`

Redeploy. Logs should show: installing requirements, then `[start.sh] Starting Botshop…`, then polling.
