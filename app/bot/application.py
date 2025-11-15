import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.core.config import get_settings
from app.bot.handlers_start import start
from app.bot.handlers_payment import (
    on_send_payment_proof,
    on_amount,
    on_photo,
    on_cancel,
    on_payment_status,
    admin_list_pending,
    admin_approve_callback,
    admin_reject_callback,
    ASK_AMOUNT,
)

logger = logging.getLogger(__name__)


def build_application() -> Application:
    settings = get_settings()
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", start))

    # Payment conversation
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_send_payment_proof, pattern="^send_payment_proof$"),
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_amount)],
            ConversationHandler.WAITING: [MessageHandler(filters.PHOTO, on_photo)],
        },
        fallbacks=[CommandHandler("cancel", on_cancel)],
    )
    app.add_handler(conv)

    # Simple callbacks
    app.add_handler(CallbackQueryHandler(on_payment_status, pattern="^payment_status$"))

    # Admin
    app.add_handler(CallbackQueryHandler(admin_list_pending, pattern="^admin_list_pending$"))
    app.add_handler(CallbackQueryHandler(admin_approve_callback, pattern="^admin_approve:"))
    app.add_handler(CallbackQueryHandler(admin_reject_callback, pattern="^admin_reject:"))

    logger.info("Telegram Application built")
    return app
