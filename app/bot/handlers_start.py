import logging
from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import main_menu_keyboard, admin_menu_keyboard
from app.core.config import get_settings
from app.db.repositories import upsert_user, insert_metric

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    is_admin = user.id in settings.TELEGRAM_ADMIN_IDS

    await upsert_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name or "",
        last_name=user.last_name,
        is_admin=is_admin,
    )

    await insert_metric(
        event_name="start",
        telegram_id=user.id,
        payload={
            "chat_id": chat.id,
            "username": user.username,
        },
    )

    text_lines = [
        "ברוך הבא למערכת BotShop / קבוצת העסקים שלנו!",
        "",
        "כאן תוכל לשלוח אישור תשלום, להצטרף לקבוצה ולקבל הטבות מיוחדות.",
    ]

    if is_admin:
        text_lines.append("זוהית כאדמין – יש לך גישה לפאנל ניהול.")

    keyboard = admin_menu_keyboard() if is_admin else main_menu_keyboard()
    await context.bot.send_message(
        chat_id=chat.id,
        text="\n".join(text_lines),
        reply_markup=keyboard,
    )
