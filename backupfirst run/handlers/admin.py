import time, random
from telegram import Update
from telegram.ext import ContextTypes
from ..config import Config
from ..services.user_service import UserService
from ..services.payment_service import PaymentService
from ..utils.tg_ui import reply_menu

def admin_only(cfg: Config, update: Update) -> bool:
    u = update.effective_user
    return u and (u.id in cfg.admin_ids)

async def ensure_group_invite_link(context: ContextTypes.DEFAULT_TYPE, cfg: Config) -> str:
    if not cfg.group_chat_id:
        return ""
    if cfg.group_invite_link:
        return cfg.group_invite_link
    try:
        link = await context.bot.create_chat_invite_link(chat_id=cfg.group_chat_id, creates_join_request=False)
        return link.invite_link
    except:
        try:
            return await context.bot.export_chat_invite_link(chat_id=cfg.group_chat_id)
        except:
            return ""

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config):
    if not admin_only(cfg, update):
        return await context.bot.send_message(update.effective_chat.id, "❌ מנהלים בלבד.")
    if context.args:
        try:
            cfg.entry_price_nis = float(context.args[0])
            return await context.bot.send_message(update.effective_chat.id, f"✅ עודכן מחיר כניסה: {cfg.entry_price_nis}")
        except:
            return await context.bot.send_message(update.effective_chat.id, "ערך לא תקין.")
    return await context.bot.send_message(update.effective_chat.id, f"מחיר כניסה: {cfg.entry_price_nis}")

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, user_svc: UserService):
    if not admin_only(cfg, update):
        return await context.bot.send_message(update.effective_chat.id, "❌ מנהלים בלבד.")
    if not context.args:
        return await context.bot.send_message(update.effective_chat.id, "שימוש: /approve <chat_id>")
    try:
        uid = int(context.args[0])
        await user_svc.set_paid(uid, True)
        await user_svc.add_balance(uid, slh=cfg.demo_grant_slh, bnb=cfg.demo_grant_bnb)
        await context.bot.send_message(uid, f"✅ תשלום אושר! קיבלת {cfg.demo_grant_slh} SLH-דמה ו{cfg.demo_grant_bnb} BNB-דמה.", reply_markup=reply_menu(True))
        link = await ensure_group_invite_link(context, cfg)
        if link:
            await context.bot.send_message(uid, f"👥 הצטרפות לקהילה: {link}")
        await context.bot.send_message(update.effective_chat.id, f"✅ אושר ל-{uid}")
    except Exception as e:
        await context.bot.send_message(update.effective_chat.id, f"שגיאה: {e}")

async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, user_svc: UserService):
    if not admin_only(cfg, update):
        return await context.bot.send_message(update.effective_chat.id, "❌ מנהלים בלבד.")
    if not context.args:
        return await context.bot.send_message(update.effective_chat.id, "שימוש: /revoke <chat_id>")
    try:
        uid=int(context.args[0]); await user_svc.set_paid(uid, False)
        await context.bot.send_message(uid, "⛔ הרשאה בוטלה. פנה לתמיכה.", reply_markup=reply_menu(False))
        await context.bot.send_message(update.effective_chat.id, f"בוטלה הרשאה ל-{uid}")
    except Exception as e:
        await context.bot.send_message(update.effective_chat.id, f"שגיאה: {e}")

async def cmd_give(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, user_svc: UserService):
    if not admin_only(cfg, update):
        return await context.bot.send_message(update.effective_chat.id, "❌ מנהלים בלבד.")
    if len(context.args) < 2:
        return await context.bot.send_message(update.effective_chat.id, "שימוש: /give <chat_id> <SLH>")
    try:
        uid=int(context.args[0]); amt=float(context.args[1])
        await user_svc.add_balance(uid, slh=amt)
        await context.bot.send_message(uid, f"🎁 התקבלו {amt} SLH-דמה מהאדמין.", reply_markup=reply_menu(True))
        await context.bot.send_message(update.effective_chat.id, f"✅ הוקצו {amt} SLH-דמה ל-{uid}")
    except Exception as e:
        await context.bot.send_message(update.effective_chat.id, f"שגיאה: {e}")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, user_svc: UserService):
    if not admin_only(cfg, update):
        return await context.bot.send_message(update.effective_chat.id, "❌ מנהלים בלבד.")
    d = await user_svc.store.get()
    users = len(d["users"])
    paid = sum(1 for u in d["users"].values() if u.get("paid"))
    s_sum = sum(float(b.get("slh",0)) for b in d["balances"].values())
    await context.bot.send_message(update.effective_chat.id, f"סטטיסטיקות:\n• משתמשים: {users}\n• בתשלום: {paid}\n• SLH-דמה כולל: {s_sum}")