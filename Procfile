web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4
worker: python background_tasks.py
bot: python telegram_bot.py
