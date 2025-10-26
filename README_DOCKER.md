# Botshop  Docker on Railway (/bot root)

## Railway Settings (חשוב)
- **Root Directory**: /bot
- **Builder**: Dockerfile (או השאר Default  Railpack יזהה Dockerfile)
- **Custom Start Command**: ריק (Dockerfile דואג ל-CMD)
- **Variables**:
  - TELEGRAM_BOT_TOKEN = <טוקן הבוט>
  - LOG_LEVEL = INFO

## Deploy
1) git add -A && git commit -m "botshop docker bootstrap" && git push
2) Railway → Redeploy → יופיע 'Building with Dockerfile', ואז 'Starting Container'.
3) בלוגים תחפש 'Starting polling…' ואז שלח /start לבוט.

אם אתה רואה ModuleNotFoundError: No module named 'telegram'  סימן שלא בנו עם Dockerfile.
ודא Root Directory=/bot ושה-Builder מזהה Docker.