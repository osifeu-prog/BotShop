import os, logging, asyncio, time
from typing import Set
from dotenv import load_dotenv
from telegram import Update, MenuButtonCommands, BotCommand, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from storage import JsonStore, ReceiptBook, new_deal_id
from keyboards import user_reply_keyboard, pay_inline_menu, confirm_paid_inline
from payments import payment_urls, bank_text, bit_text, nis_price, quote_prices

load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger("Botshop")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
STORE_PATH = os.getenv("STORE_PATH", "/data/store.json")
RECEIPTS_CSV = os.getenv("RECEIPTS_CSV", "/data/receipts.csv")
ADMIN_NAME = os.getenv("ADMIN_NAME", "Admin")
ADMIN_IDS: Set[int] = set()
for part in (os.getenv("ADMIN_IDS","") or "").replace(";",",").split(","):
    p = part.strip()
    if p.isdigit():
        ADMIN_IDS.add(int(p))

GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "")
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK", "")

store = JsonStore(STORE_PATH)
receipts = ReceiptBook(RECEIPTS_CSV)

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

async def reply_menu(update: Update, text: str):
    if update.message:
        await update.message.reply_text(text, reply_markup=user_reply_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=user_reply_keyboard())

async def send_dm(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    try:
        await context.bot.send_message(chat_id, text)
    except Exception as e:
        log.warning(f"send_dm failed to {chat_id}: {e}")

# ---------------- Commands (User) ----------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    store.ensure_user(chat_id)
    nis, usd, fx = await quote_prices()
    hello = (
        f"ברוך הבא ל-Botshop 👋\n\n"
        f"מחיר הצטרפות: {nis:.0f} ₪  (~${usd:.2f} @ {fx} ILS/USD)\n"
        f"לאחר אישור תשלום תיפתח גישה לקבוצה ויזקף זיכוי SLH בשווי התשלום.\n\n"
        f"מה תרצה לעשות?"
    )
    await reply_menu(update, hello)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [
        f"Admin: {ADMIN_NAME}",
        "פקודות:",
        "/start – פתיחה",
        "/help – עזרה",
        "/status – סטטוס הרשאה ותשלום",
        "/join – תשלום והצטרפות",
        "/history – היסטוריית תשלומים",
    ]
    if is_admin(update.effective_user.id):
        lines += [
            "",
            "פקודות אדמין:",
            "/setprice <NIS> – עדכון מחיר הצטרפות",
            "/setfx <ILS_per_USD> – עדכון שער ידני (פולבאק)",
            "/markpaid <chat_id> – סימון משתמש כשילם",
            "/export_receipts – הורדת CSV",
            "/broadcast <msg> – הודעה לכל המשתמשים",
        ]
    await reply_menu(update, "\n".join(lines))

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = store.ensure_user(chat_id)
    paid_emoji = "✅" if u.get("paid") else "❌"
    wallet = u.get("wallet") or "(לא הוגדר)"
    group_hint = GROUP_INVITE_LINK or "אחרי אישור תשלום תקבל קישור לקבוצה."
    nis, usd, fx = await quote_prices()
    text = (
        f"סטטוס משתמש:\n"
        f"• תשלום: {paid_emoji}\n"
        f"• ארנק: {wallet}\n"
        f"• מחיר הצטרפות כעת: {nis:.0f} ₪ (~${usd:.2f})\n"
        f"• קבוצה: {group_hint}\n"
    )
    await reply_menu(update, text)

async def cmd_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = store.ensure_user(chat_id)
    nis, usd, fx = await quote_prices()
    pay_urls = payment_urls(chat_id)
    text = (
        f"🚀 הצטרפות לקהילה – {nis:.0f} ₪ (~${usd:.2f})\n\n"
        f"בחר שיטת תשלום. לאחר התשלום שלח פה 'שילמתי' או אסמכתא (צילום מסך)."
    )
    # כשיוזר לוחץ בנק/ביט נרשום כוונה (method_pending)
    u = store.update_user(chat_id, {"method_pending": ""})
    await update.message.reply_text(text, reply_markup=pay_inline_menu(pay_urls))

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = store.ensure_user(chat_id)
    hist = u.get("history", [])[:10]
    if not hist:
        return await reply_menu(update, "אין היסטוריית עסקאות עדיין.")
    lines = ["היסטוריית עסקאות (אחרונות):"]
    for e in hist:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("ts",0)))
        lines.append(f"• [{e.get('status','?')}] {e.get('type','?')} | {e.get('amount_nis',0)}₪ (~${e.get('amount_usd',0)}) | {ts} | #{e.get('deal_id','')}")
    await reply_menu(update, "\n".join(lines))

# ---------------- Admin ----------------
async def cmd_setprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("שימוש: /setprice <NIS>")
        return
    try:
        val = float(context.args[0])
    except Exception:
        await update.message.reply_text("ערך לא תקין.")
        return
    os.environ["ENTRY_PRICE_NIS"] = str(val)
    await update.message.reply_text(f"עודכן מחיר הצטרפות ל-{val:.0f} ₪")

async def cmd_setfx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("שימוש: /setfx <ILS_per_USD>  (לדוגמה: 3.7)")
        return
    try:
        rate = float(context.args[0])
        if rate <= 0: raise ValueError()
    except Exception:
        await update.message.reply_text("ערך לא תקין.")
        return
    os.environ["FX_USDILS"] = str(rate)
    await update.message.reply_text(f"עודכן שער ידני: {rate} ILS/USD (פולבאק אם ה־API נופל)")

async def cmd_markpaid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("שימוש: /markpaid <chat_id>")
        return
    try:
        cid = int(context.args[0])
    except Exception:
        await update.message.reply_text("chat_id לא תקין")
        return
    # יצירת רשומת עסקה "PAID" (אם אין deal תלוי, ניצור חדש)
    nis, usd, fx = await quote_prices()
    deal_id = new_deal_id()
    ts = int(time.time())
    store.append_history(cid, {
        "deal_id": deal_id,
        "ts": ts,
        "type": "membership",
        "method": "admin",
        "amount_nis": nis,
        "amount_usd": usd,
        "status": "PAID"
    })
    receipts.add(deal_id, ts, cid, "admin", nis, usd, "PAID")
    store.update_user(cid, {"paid": True})
    await update.message.reply_text(f"✅ סומן כשולם: {cid} | עסקה #{deal_id}")
    await send_dm(context, cid, f"תשלום אושר! ברוך הבא 🎉\nעסקה #{deal_id} | {nis:.0f} ₪ (~${usd:.2f})")
    if GROUP_INVITE_LINK:
        await send_dm(context, cid, f"📥 הצטרפות לקבוצה: {GROUP_INVITE_LINK}")

async def cmd_export_receipts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    path = os.getenv("RECEIPTS_CSV", "/data/receipts.csv")
    if not os.path.exists(path):
        return await update.message.reply_text("אין עדיין קבלות.")
    try:
        with open(path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=os.path.basename(path)))
    except Exception as e:
        await update.message.reply_text(f"שגיאה בשליחה: {e}")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("שימוש: /broadcast <message>")
        return
    msg = " ".join(context.args)
    users = store.all_users()
    ok, fail = 0, 0
    for sid in users.keys():
        try:
            await send_dm(context, int(sid), f"📣 {msg}")
            ok += 1
        except:
            fail += 1
    await update.message.reply_text(f"שוגר. הצליח: {ok}, נכשל: {fail}")

# ---------------- Messages ----------------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    # קיצורי מקלדת
    if text in ("🧭 תפריט", "/menu"):
        return await cmd_start(update, context)
    if text in ("🧾 סטטוס", "/status"):
        return await cmd_status(update, context)
    if text in ("💳 תשלום", "/join"):
        return await cmd_join(update, context)
    if text in ("📥 הצטרפות לקבוצה",):
        u = store.ensure_user(chat_id)
        if u.get("paid") and GROUP_INVITE_LINK:
            return await reply_menu(update, f"📥 הנה הקישור לקבוצה: {GROUP_INVITE_LINK}")
        else:
            return await reply_menu(update, "עדיין לא אושר תשלום. לחץ \"💳 תשלום\" והשלם.")
    if text in ("🧮 היסטוריה","/history"):
        return await cmd_history(update, context)

    # קלט כתובת ארנק 0x...
    if text.startswith("0x") and len(text) == 42:
        store.update_user(chat_id, {"wallet": text})
        return await reply_menu(update, "✅ כתובת ארנק נשמרה!")

    # "שילמתי" → נרשום עסקה במצב PENDING ומודיעים לאדמין
    if text.startswith("שילמתי"):
        nis, usd, fx = await quote_prices()
        deal_id = new_deal_id()
        ts = int(time.time())
        u = store.ensure_user(chat_id)
        method = u.get("method_pending") or "unknown"
        store.append_history(chat_id, {
            "deal_id": deal_id,
            "ts": ts,
            "type": "membership",
            "method": method,
            "amount_nis": nis,
            "amount_usd": usd,
            "status": "PENDING"
        })
        receipts.add(deal_id, ts, chat_id, method, nis, usd, "PENDING")
        # נעדכן את המשתמש
        await reply_menu(update, f"💬 קיבלנו דיווח תשלום. מספר עסקה #{deal_id}. ממתין לאישור אדמין.")
        # נודיע לאדמין עם כפתור אישור
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    aid,
                    f"🧾 עסקה חדשה (PENDING) #{deal_id} מאת {chat_id}\nשיטה: {method}\nסכום: {nis:.0f} ₪ (~${usd:.2f})",
                    reply_markup=confirm_paid_inline(chat_id, deal_id)
                )
            except Exception as e:
                log.warning(f"notify admin failed: {e}")
        return

    # דיפולט
    await reply_menu(update, "לא זוהה. השתמש במקלדת למטה או /help")

# ---------------- Media (proof) ----------------
async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # נרשום עסקה בפנדינג אם אין טריגר אחר
    nis, usd, fx = await quote_prices()
    deal_id = new_deal_id()
    ts = int(time.time())
    u = store.ensure_user(chat_id)
    method = u.get("method_pending") or "unknown"
    store.append_history(chat_id, {
        "deal_id": deal_id,
        "ts": ts,
        "type": "membership",
        "method": method,
        "amount_nis": nis,
        "amount_usd": usd,
        "status": "PENDING"
    })
    receipts.add(deal_id, ts, chat_id, method, nis, usd, "PENDING")
    await reply_menu(update, f"💬 קיבלנו אסמכתא. עסקה #{deal_id} ממתינה לאישור.")
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(
                aid,
                f"🧾 עסקה חדשה (PENDING) #{deal_id} מאת {chat_id}\nשיטה: {method}\nסכום: {nis:.0f} ₪ (~${usd:.2f})",
                reply_markup=confirm_paid_inline(chat_id, deal_id)
            )
        except Exception as e:
            log.warning(f"notify admin failed: {e}")

# ---------------- Callbacks ----------------
async def on_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    cid = update.effective_user.id

    if data == "pay_bank":
        store.update_user(cid, {"method_pending": "bank"})
        return await q.edit_message_text(bank_text())
    if data == "pay_bit":
        store.update_user(cid, {"method_pending": "bit"})
        return await q.edit_message_text(bit_text())
    if data.startswith("admin_mark_paid:"):
        if not is_admin(update.effective_user.id):
            return await q.edit_message_text("❌ למנהלים בלבד")
        try:
            _, chat_id_str, deal_id = data.split(":")
            target_id = int(chat_id_str)
        except:
            return await q.edit_message_text("פרמטרים לא תקינים")
        # נעדכן סטטוס עסקה ל-PAID (נרשום רשומה מאשרת – פשוט)
        nis, usd, fx = await quote_prices()
        ts = int(time.time())
        # רישום שורת אישור נוספת
        store.append_history(target_id, {
            "deal_id": deal_id,
            "ts": ts,
            "type": "membership",
            "method": "admin",
            "amount_nis": nis,
            "amount_usd": usd,
            "status": "PAID"
        })
        receipts.add(deal_id, ts, target_id, "admin", nis, usd, "PAID")
        store.update_user(target_id, {"paid": True})
        await q.edit_message_text(f"✅ אושר תשלום ל-{target_id} | עסקה #{deal_id}")
        try:
            await context.bot.send_message(target_id, f"תשלום אושר! ברוך הבא 🎉\nעסקה #{deal_id} | {nis:.0f} ₪ (~${usd:.2f})")
            if GROUP_INVITE_LINK:
                await context.bot.send_message(target_id, f"📥 הצטרפות לקבוצה: {GROUP_INVITE_LINK}")
        except Exception as e:
            log.warning(f"notify user failed: {e}")
        return

# ---------------- Boot ----------------
def build_app() -> Application:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    app = Application.builder().token(TOKEN).build()
    app.bot.set_my_commands([
        BotCommand("start","פתיחה"),
        BotCommand("help","עזרה"),
        BotCommand("status","סטטוס"),
        BotCommand("join","תשלום והצטרפות"),
        BotCommand("history","היסטוריית תשלומים"),
    ])
    try:
        app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        log.info(f"set menu button failed (non-fatal): {e}")

    # User
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("join", cmd_join))
    app.add_handler(CommandHandler("history", cmd_history))

    # Admin
    app.add_handler(CommandHandler("setprice", cmd_setprice))
    app.add_handler(CommandHandler("setfx", cmd_setfx))
    app.add_handler(CommandHandler("markpaid", cmd_markpaid))
    app.add_handler(CommandHandler("export_receipts", cmd_export_receipts))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Messages / Media
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, on_media))

    # Callbacks
    app.add_handler(CallbackQueryHandler(on_cb))

    return app

def main():
    app = build_app()
    log.info("Botshop polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()