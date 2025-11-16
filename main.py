
    import logging
    from datetime import datetime

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, RedirectResponse

    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        ApplicationBuilder,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )

    from config import (
        BOT_TOKEN,
        BOT_USERNAME,
        WEBHOOK_URL,
        ADMIN_LOGS_CHAT_ID,
        SUPPORT_GROUP_CHAT_ID,
        BUSINESS_GROUP_URL,
        SUPPORT_GROUP_URL,
        SLH_NIS,
        BIT_URL,
        PAYBOX_URL,
        PAYPAL_URL,
        LANDING_URL,
    )
    from db import SessionLocal, init_db, get_or_create_user, PaymentProof, SupportTicket

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    logger = logging.getLogger("botshop-gateway")

    app = FastAPI(title="BotShop Gateway Minimal")

    telegram_app: Application | None = None


    # =========================
    # Telegram Handlers
    # =========================


    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_chat is None:
            return

        tg_user = update.effective_user
        chat = update.effective_chat

        # DB: ensure user exists
        session = SessionLocal()
        try:
            user = get_or_create_user(session, tg_user)
        finally:
            session.close()

        # Log to admin group
        if ADMIN_LOGS_CHAT_ID:
            try:
                text = (
                    "📥 משתמש חדש הפעיל את הבוט\n"
                    f"ID: {tg_user.id}\n"
                    f"Username: @{tg_user.username}\n"
                    f"Name: {tg_user.full_name}\n"
                    f"Chat ID: {chat.id}\n"
                )
                await context.bot.send_message(chat_id=ADMIN_LOGS_CHAT_ID, text=text)
            except Exception as e:
                logger.warning("Failed to send new user log: %s", e)

        # Message to user
        text_lines = [
            "🌐 שער הכניסה ל-SLHNET – נכס דיגיטלי לכל אחד",
            "",
            f"חד פעמית: *{int(SLH_NIS)} ש"ח* להצטרפות לקהילת העסקים שלנו.",
            "",
            "מה תקבל אחרי התשלום?",
            "• גישה לקבוצת עסקים פרטית (הדרכות, שיתופי פעולה, מבצעים).",
            "• מקום לקבל נכסים דיגיטליים, קלפים ו-NFT מניבי ערך.",
            "• קישור שיתוף אישי – כל מי שנכנס דרכך מתועד במערכת.",
            "",
            "אחרי ביצוע התשלום – שלח כאן *צילום מסך / אישור העברה* ונאשר אותך ידנית.",
        ]

        keyboard = [
            [
                InlineKeyboardButton("💳 לשלם 39 ש"ח", callback_data="pay"),
            ],
            [
                InlineKeyboardButton("📢 קהילת העסקים (לאחר תשלום)", url=BUSINESS_GROUP_URL or LANDING_URL),
            ],
            [
                InlineKeyboardButton("🛠 תמיכה טכנית", callback_data="support"),
            ],
            [
                InlineKeyboardButton("🌐 אתר הפרויקט", url=LANDING_URL),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "\n".join(text_lines),
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


    async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.callback_query is None:
            return
        query = update.callback_query
        data = query.data or ""

        if data == "pay":
            lines = [
                "💳 אפשרויות תשלום להצטרפות (39 ש"ח):",
                "",
                "1) Bit:",
                f"   {BIT_URL or 'עודכן מול האדמין'}",
                "",
                "2) PayBox:",
                f"   {PAYBOX_URL or 'עודכן מול האדמין'}",
                "",
                "3) PayPal:",
                f"   {PAYPAL_URL or 'עודכן מול האדמין'}",
                "",
                "לאחר התשלום – שלח כאן צילום של אישור ההעברה ונאשר אותך ידנית לקבוצת העסקים.",
            ]
            await query.answer()
            await query.edit_message_text("\n".join(lines))
            return

        if data == "support":
            await query.answer()
            await query.edit_message_text(
                "🛠 תמיכה טכנית\n\n"
                "כתוב לי כאן את נושא הפניה וההודעה, ואני אעביר אותה ישירות לצוות התמיכה. "
                "תוכל גם לצרף צילום מסך במידת הצורך."
            )
            # נסמן שאנחנו במצב תמיכה (בתור flag)
            if context.user_data is not None:
                context.user_data["awaiting_support"] = True
            return

        await query.answer()


    async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """כל תמונה בצ'אט פרטי נחשבת כאישור תשלום."""
        if update.message is None or update.effective_user is None:
            return
        if update.effective_chat is None or update.effective_chat.type != "private":
            return

        tg_user = update.effective_user
        message = update.message

        if not message.photo:
            return

        photo = message.photo[-1]  # highest resolution
        file_id = photo.file_id
        caption = message.caption or ""

        # DB save
        session = SessionLocal()
        try:
            user = get_or_create_user(session, tg_user)
            proof = PaymentProof(
                user_id=user.id,
                telegram_id=tg_user.id,
                username=tg_user.username,
                photo_file_id=file_id,
                caption=caption,
                status="pending",
            )
            session.add(proof)
            session.commit()
        finally:
            session.close()

        # Forward to admin logs
        if ADMIN_LOGS_CHAT_ID:
            try:
                text = (
                    "📥 התקבל אישור תשלום חדש.\n"
                    f"user_id = {tg_user.id}\n"
                    f"username = @{tg_user.username}\n"
                    f"from chat_id = {update.effective_chat.id}\n"
                    "\n"
                    "לאישור ידני של תשלום זה, יש ליצור קשר עם המשתמש בפרטי."
                )
                await context.bot.send_photo(
                    chat_id=ADMIN_LOGS_CHAT_ID,
                    photo=file_id,
                    caption=text,
                )
            except Exception as e:
                logger.warning("Failed to forward payment proof to admin group: %s", e)

        await message.reply_text(
            "✅ תודה! אישור התשלום התקבל ונמצא כעת בבדיקה.
"
            "לאחר האישור תקבל קישור לקבוצת העסקים שלנו."
        )


    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return

        tg_user = update.effective_user
        text = update.message.text or ""

        # אם המשתמש במוד תמיכה
        if context.user_data is not None and context.user_data.get("awaiting_support"):
            subject = text.split("\n", 1)[0][:200]

            session = SessionLocal()
            try:
                ticket = SupportTicket(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    subject=subject,
                    message=text,
                )
                session.add(ticket)
                session.commit()
            finally:
                session.close()

            # שליחה לקבוצת התמיכה
            if SUPPORT_GROUP_CHAT_ID:
                try:
                    msg = (
                        "🛠 פניה חדשה לתמיכה\n"
                        f"ID: {tg_user.id}\n"
                        f"Username: @{tg_user.username}\n"
                        "\n"
                        f"נושא: {subject}\n"
                        "\n"
                        f"הודעה:\n{text}"
                    )
                    await context.bot.send_message(chat_id=SUPPORT_GROUP_CHAT_ID, text=msg)
                except Exception as e:
                    logger.warning("Failed to send support message to group: %s", e)

            if context.user_data is not None:
                context.user_data["awaiting_support"] = False

            await update.message.reply_text(
                "✅ ההודעה נשלחה לתמיכה. נחזור אליך בהקדם האפשרי."
            )
            return

        # טקסט רגיל – נחזיר רמז ללחיצה על /start
        await update.message.reply_text(
            "כדי להתחיל, השתמש בפקודת /start.
"
            "לאחר תשלום 39 ש"ח ושליחת אישור, תצורף לקבוצת העסקים."
        )


    # =========================
    # FastAPI routes
    # =========================


    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": "botshop-gateway-minimal",
            "db": "enabled",
        }


    @app.get("/")
    async def index() -> RedirectResponse:
        return RedirectResponse(LANDING_URL)


    @app.post("/webhook")
    async def telegram_webhook(request: Request):
        global telegram_app
        if telegram_app is None:
            return JSONResponse({"ok": False, "error": "telegram app not ready"}, status_code=503)

        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return JSONResponse({"ok": True})


    # =========================
    # Lifespan: init DB + Telegram app
    # =========================


    @app.on_event("startup")
    async def on_startup() -> None:
        global telegram_app
        logger.info("Starting up BotShop Gateway Minimal...")
        # DB tables
        init_db()

        if not BOT_TOKEN:
            logger.error("BOT_TOKEN is not set – Telegram bot will not start.")
            return

        telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

        # Telegram handlers
        telegram_app.add_handler(CommandHandler("start", cmd_start))
        telegram_app.add_handler(CallbackQueryHandler(on_callback))
        telegram_app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        await telegram_app.initialize()
        await telegram_app.start()

        if WEBHOOK_URL:
            try:
                await telegram_app.bot.set_webhook(WEBHOOK_URL)
                logger.info("Telegram webhook set to %s", WEBHOOK_URL)
            except Exception as e:
                logger.error("Failed to set Telegram webhook: %s", e)
        else:
            logger.warning("WEBHOOK_URL is not set – webhook not configured.")


    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        global telegram_app
        if telegram_app is not None:
            await telegram_app.stop()
            await telegram_app.shutdown()
            logger.info("Telegram application stopped.")
