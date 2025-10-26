import os, asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from .config import Config
from .utils.logging import setup_logging
from .storage.json_store import JsonStore
from .services.user_service import UserService
from .services.payment_service import PaymentService
from .handlers.admin import cmd_price, cmd_approve, cmd_revoke, cmd_give, cmd_stats
from .handlers.user import cmd_start, on_text, StateManager

def build_app(cfg: Config):
    log = setup_logging()
    if os.name != "nt":
        try:
            import uvloop; uvloop.install()
        except Exception:
            pass

    store = JsonStore(cfg.store_path)
    user_svc = UserService(store)
    pay = PaymentService(cfg)
    sm = StateManager()

    app = Application.builder().token(cfg.token).build()

    # Commands
    app.add_handler(CommandHandler("start", lambda u,c: cmd_start(u,c,cfg,user_svc)))
    app.add_handler(CommandHandler("price", lambda u,c: cmd_price(u,c,cfg)))
    app.add_handler(CommandHandler("approve", lambda u,c: cmd_approve(u,c,cfg,user_svc)))
    app.add_handler(CommandHandler("revoke", lambda u,c: cmd_revoke(u,c,cfg,user_svc)))
    app.add_handler(CommandHandler("give", lambda u,c: cmd_give(u,c,cfg,user_svc)))
    app.add_handler(CommandHandler("stats", lambda u,c: cmd_stats(u,c,cfg,user_svc)))

    # Text flow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: on_text(u,c,cfg,user_svc,pay,sm)))

    return app

def main():
    cfg = Config.from_env()
    app = build_app(cfg)
    app.run_polling()

if __name__ == "__main__":
    main()