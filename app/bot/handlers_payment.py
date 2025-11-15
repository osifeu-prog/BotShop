    import logging
    from decimal import Decimal
    from typing import Optional

    from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
    from telegram.ext import ContextTypes, ConversationHandler

    from app.db.repositories import create_payment, insert_metric

    logger = logging.getLogger(__name__)

    ASK_AMOUNT = 1

    async def on_send_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat = update.effective_chat
        if not chat:
            return ConversationHandler.END

        await context.bot.send_message(
            chat_id=chat.id,
            text="מעולה. אנא שלח/י את סכום התשלום שביצעת (במספרים בלבד, לדוגמה: 39).",
        )
        return ASK_AMOUNT


    async def on_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat = update.effective_chat
        user = update.effective_user
        if not chat or not user:
            return ConversationHandler.END

        text = (update.message.text or "").strip()
        try:
            amount = Decimal(text)
        except Exception:
            await update.message.reply_text("לא הצלחתי לקרוא את הסכום. נסה שוב עם מספר בלבד, לדוגמה: 39")
            return ASK_AMOUNT

        context.user_data["payment_amount"] = float(amount)
        await update.message.reply_text(
            "עכשיו אנא שלח/י צילום מסך / תמונת אישור התשלום.
"
            "לאחר שליחת התמונה – אני אשמור את זה ואעביר לבדיקה."
        )
        return ConversationHandler.WAITING


    async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat = update.effective_chat
        user = update.effective_user
        message = update.message
        if not chat or not user or not message or not message.photo:
            return ConversationHandler.END

        amount = context.user_data.get("payment_amount")
        if amount is None:
            await message.reply_text("לא נמצא סכום תשלום קודם. התחל מחדש עם /start.")
            return ConversationHandler.END

        # Take highest resolution photo
        photo = message.photo[-1]
        proof_file_id = photo.file_id

        await create_payment(
            telegram_id=user.id,
            amount=float(amount),
            currency="₪",
            proof_type="photo",
            proof_file_id=proof_file_id,
        )

        await insert_metric(
            event_name="payment_proof_submitted",
            telegram_id=user.id,
            payload={
                "amount": float(amount),
                "currency": "₪",
                "chat_id": chat.id,
            },
        )

        await message.reply_text(
            "קיבלתי את אישור התשלום שלך 🙌
"
            "אדמין יעבור עליו, ולאחר האישור תקבל קישור לקבוצת העסקים והטבות נוספות."
        )

        context.user_data.pop("payment_amount", None)
        return ConversationHandler.END


    async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.message:
            await update.message.reply_text("הפעולה בוטלה.")
        return ConversationHandler.END


    async def on_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if not chat:
            return
        await context.bot.send_message(
            chat_id=chat.id,
            text="סטטוס תשלום: כרגע אין לי מעקב מפורט לפי עסקה בודדת. "
                 "בשלב הזה אם יש שאלה – פנה לתמיכה בקבוצה.",
        )


    # Admin handlers

    async def admin_list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from app.db.repositories import list_pending_payments

        user = update.effective_user
        chat = update.effective_chat
        if not user or not chat:
            return

        pending = await list_pending_payments(limit=20)
        if not pending:
            await context.bot.send_message(chat_id=chat.id, text="אין תשלומים ממתינים כרגע ✅")
            return

        lines = ["תשלומים ממתינים:"]
        keyboard_buttons = []
        for row in pending:
            pid = str(row["id"])
            amount = row.get("amount_numeric")
            cid = row.get("telegram_id")
            created = row.get("created_at")
            lines.append(f"- {pid} | משתמש {cid} | סכום {amount} | {created}")
            keyboard_buttons.append([
                InlineKeyboardButton(f"✅ אשר {pid}", callback_data=f"admin_approve:{pid}"),
                InlineKeyboardButton(f"❌ דחה {pid}", callback_data=f"admin_reject:{pid}"),
            ])

        await context.bot.send_message(
            chat_id=chat.id,
            text="\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None,
        )


    async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from app.db.repositories import approve_payment

        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        _, pid = query.data.split(":", 1)
        await approve_payment(pid)
        await query.edit_message_text(f"התשלום {pid} אושר ✅")


    async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from app.db.repositories import reject_payment

        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        _, pid = query.data.split(":", 1)
        await reject_payment(pid)
        await query.edit_message_text(f"התשלום {pid} נדחה ❌")
