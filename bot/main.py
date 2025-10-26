import os
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from .utils.logger import setup_logger
from .handlers import user as user_handlers

def build_app():
    token = os.getenv("TELEGRAM_BOT_TOKEN","")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    log = setup_logger()
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", user_handlers.cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_handlers.on_text))

    log.info("Application built")
    return app

def main():
    app = build_app()
    app.run_polling(allowed_updates=filters.UpdateType.ALL_TYPES)

if __name__ == "__main__":
    main()
