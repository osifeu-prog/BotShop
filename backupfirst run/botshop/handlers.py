from __future__ import annotations
import logging, re, time
from telegram import Update
from telegram.ext import ContextTypes
from .config import Config
from .store import JsonStore
from .keyboards import reply_main, inline_pay_actions
from .payments import payment_text

log = logging.getLogger("Botshop")

ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, store: JsonStore):
    u = update.effective_user
    await store.upsert_user(u.id, {"username": u.username or "", "first_name": u.first_name or ""})
    prefix = f"Admin: {cfg.admin_name}\n" if u.id in cfg.admin_ids else ""
    await update.message.reply_text(
        prefix + "ברוך הבא ל*SLH Botshop* 👋\n"
        f"עלות כניסה: *{cfg.entry_price_nis:.0f}*.\n"
        "בחר פעולה מתחת או שלח לי צילום אסמכתה לאחר תשלום.",
        reply_markup=reply_main(),
        parse_mode="Markdown"
    )

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, store: JsonStore):
    text = (update.message.text or "").strip()
    lower = text.lower()

    if text == "💳 תשלום":
        await update.message.reply_text(payment_text(), reply_markup=reply_main(), parse_mode="Markdown")
        await update.message.reply_text("לאחר התשלום, שלח/י כאן צילום אסמכתה ונבדוק. ⤵️", reply_markup=inline_pay_actions(cfg.group_invite_link), parse_mode="Markdown")
        return

    if text == "📥 הצטרפות":
        if cfg.group_invite_link:
            await update.message.reply_text("להצטרפות לקבוצה, לחצו:", reply_markup=inline_pay_actions(cfg.group_invite_link))
        else:
            await update.message.reply_text("קישור קבוצה לא מוגדר כרגע.")
        return

    if text == "ℹ️ מצב":
        u = await store.get_user(update.effective_user.id) or {}
        paid = "✅" if u.get("paid") else "❌"
        wallet = u.get("wallet","—")
        await update.message.reply_text(
            f"סטטוס: {paid}\nארנק: {wallet}\nהצטרפת: {time.strftime('%Y-%m-%d', time.gmtime(u.get('joined_at',0)))}",
            reply_markup=reply_main()
        )
        return

    if text == "👥 קבוצה":
        if cfg.group_invite_link:
            await update.message.reply_text(f"👉 {cfg.group_invite_link}", reply_markup=reply_main())
        else:
            await update.message.reply_text("אין קישור קבוצה מוגדר.", reply_markup=reply_main())
        return

    # Try wallet capture
    if ADDR_RE.match(text):
        await store.upsert_user(update.effective_user.id, {"wallet": text})
        await update.message.reply_text("✅ כתובת נשמרה.", reply_markup=reply_main())
        return

    await update.message.reply_text("לא הבנתי 🙏 בחר פעולה מהמקלדת למטה.", reply_markup=reply_main())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, store: JsonStore):
    await update.message.reply_text(
        "/start  התחלה\n"
        "/help  עזרה\n"
        "/approve <user_id>  אדמין: סימון תשלום מאושר\n"
        "/price <NIS>  אדמין: עדכון מחיר כניסה",
    )

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, store: JsonStore):
    if update.effective_user.id not in cfg.admin_ids:
        return await update.message.reply_text("למנהלים בלבד.")
    try:
        val = float((update.message.text or "").split(maxsplit=1)[1])
        cfg.entry_price_nis = val
        await update.message.reply_text(f"✅ מחיר עודכן ל{val:.0f}")
    except Exception:
        await update.message.reply_text("פורמט: /price 39")

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, store: JsonStore):
    if update.effective_user.id not in cfg.admin_ids:
        return await update.message.reply_text("למנהלים בלבד.")
    parts = (update.message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await update.message.reply_text("שימוש: /approve <user_id>")
    uid = int(parts[1])
    await store.upsert_user(uid, {"paid": True})
    await update.message.reply_text(f"✅ משתמש {uid} סומן כמשלם.")