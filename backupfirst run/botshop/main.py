from __future__ import annotations
import asyncio, logging, os
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from .config import Config, setup_logging
from .store import JsonStore
from . import handlers as H

def build_app(cfg: Config) -> Application:
    setup_logging(cfg.log_level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = Application.builder().token(cfg.token).build()

    store = JsonStore(cfg.store_path)

    app.add_handler(CommandHandler("start", lambda u,c: H.cmd_start(u,c,cfg,store)))
    app.add_handler(CommandHandler("help",  lambda u,c: H.cmd_help(u,c,cfg,store)))
    app.add_handler(CommandHandler("price", lambda u,c: H.cmd_price(u,c,cfg,store)))
    app.add_handler(CommandHandler("approve", lambda u,c: H.cmd_approve(u,c,cfg,store)))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: H.on_text(u,c,cfg,store)))

    return app

def main():
    cfg = Config()
    app = build_app(cfg)
    app.run_polling(allowed_updates=["message","callback_query"])

if __name__ == "__main__":
    main()