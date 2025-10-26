from telegram import Update
from telegram.ext import ContextTypes
from ..config import Config
from ..services.user_service import UserService
from ..services.payment_service import PaymentService
from ..utils.tg_ui import reply_menu
from ..utils.validators import is_address, is_positive_float
from ..models.order import Order, OrderType
from ..models.state import UserState, UserStateType

class StateManager:
    def __init__(self):
        self._mem = {}

    def set(self, chat_id: int, st: UserState):
        self._mem[chat_id] = st

    def get(self, chat_id: int) -> UserState:
        return self._mem.get(chat_id, UserState())

    def clear(self, chat_id: int):
        self._mem.pop(chat_id, None)

async def send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, paid: bool):
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_menu(paid))

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, user_svc: UserService):
    cid = update.effective_chat.id
    await user_svc.ensure_user(cid)
    u = await user_svc.get_user(cid)
    header = f"👑 Admin: {cfg.admin_name}\n" if (cid in cfg.admin_ids) else ""
    txt = (header +
           "ברוך הבא לSLH Botshop (Sandbox) 🎮\n"
           f"• כניסה לקהילה: {cfg.entry_price_nis} (חדפעמי) — מענק דמה להתחלה\n"
           "• לאחר תשלום: תוכל לתרגל קנייה/מכירה/העברה במטבעות דמה\n"
           "• שמור 0x… כדי שנציג פרופיל מלא\n")
    await send(context, cid, txt, paid=u.paid)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: Config, user_svc: UserService, pay: PaymentService, sm: StateManager):
    cid = update.effective_chat.id
    await user_svc.ensure_user(cid)
    u = await user_svc.get_user(cid)
    t = (update.message.text or "").strip()

    st = sm.get(cid)

    # Reply keyboard actions
    if t == "📊 יתרה":
        b = await user_svc.get_balance(cid)
        return await send(context, cid, f"יתרה (דמה):\n• SLH: {b.slh}\n• BNB: {b.bnb}", u.paid)

    if t == "👤 פרופיל":
        return await send(context, cid, f"פרופיל:\n• סטטוס: {'✅ משולם' if u.paid else '⛔ לא שולם'}\n• ארנק: {u.wallet or '(לא נשמר)'}", u.paid)

    if t == "🧾 תשלום כניסה":
        url = pay.link_for(cid)
        return await send(context, cid, f"לתשלום {int(cfg.entry_price_nis)}:\n{url}\nלאחר תשלום, האדמין יאשר ידנית (זמני).", u.paid)

    if t == "🔗 שמור ארנק":
        sm.set(cid, UserState(UserStateType.AWAIT_WALLET))
        return await send(context, cid, "שלח עכשיו כתובת MetaMask (0x…)", u.paid)

    if st.t == UserStateType.AWAIT_WALLET:
        sm.clear(cid)
        if is_address(t):
            await user_svc.set_wallet(cid, t)
            return await send(context, cid, "✅ כתובת נשמרה!", u.paid)
        return await send(context, cid, "❌ כתובת לא תקינה. נסה שוב.", u.paid)

    if not u.paid:
        return await send(context, cid, "⛔ דרוש תשלום כניסה כדי להשתמש בפעולות הדמה.", False)

    if t == "🛒 קנייה (דמה)":
        sm.set(cid, UserState(UserStateType.AWAIT_BUY_AMOUNT))
        return await send(context, cid, "כמה SLH תרצה לקנות? (מספר)", True)

    if st.t == UserStateType.AWAIT_BUY_AMOUNT:
        sm.clear(cid)
        if not is_positive_float(t):
            return await send(context, cid, "❌ ערך לא תקין.", True)
        amt = float(t)
        await user_svc.add_balance(cid, slh=amt)
        await user_svc.add_order(Order(id=int(cid*1000), type=OrderType.BUY, frm=cid, to=cid, amount=amt))
        return await send(context, cid, f"🛒 בוצעה קנייה (דמה): +{amt} SLH.", True)

    if t == "🏪 מכירה (דמה)":
        sm.set(cid, UserState(UserStateType.AWAIT_SELL_AMOUNT))
        return await send(context, cid, "כמה SLH למכור? (מספר)", True)

    if st.t == UserStateType.AWAIT_SELL_AMOUNT:
        sm.clear(cid)
        if not is_positive_float(t):
            return await send(context, cid, "❌ ערך לא תקין.", True)
        amt=float(t); b=await user_svc.get_balance(cid)
        if b.slh < amt:
            return await send(context, cid, "❌ אין מספיק SLH-דמה.", True)
        await user_svc.add_balance(cid, slh=-amt)
        await user_svc.add_order(Order(id=int(cid*1000)+1, type=OrderType.SELL, frm=cid, to=cid, amount=amt))
        return await send(context, cid, f"🏪 מכירה (דמה): -{amt} SLH.", True)

    if t == "🔁 העברה (דמה)":
        sm.set(cid, UserState(UserStateType.AWAIT_TRANSFER_TO))
        return await send(context, cid, "שלח chat_id של חבר להעברה (דמה).", True)

    if st.t == UserStateType.AWAIT_TRANSFER_TO:
        if t.isdigit():
            sm.set(cid, UserState(UserStateType.AWAIT_TRANSFER_AMOUNT, data={"to": int(t)}))
            return await send(context, cid, "כמה SLH להעביר? (מספר)", True)
        sm.clear(cid)
        return await send(context, cid, "❌ chat_id לא תקין.", True)

    if st.t == UserStateType.AWAIT_TRANSFER_AMOUNT:
        sm.clear(cid)
        if not is_positive_float(t):
            return await send(context, cid, "❌ ערך לא תקין.", True)
        amt = float(t); b=await user_svc.get_balance(cid); to = st.data.get("to")
        if b.slh < amt:
            return await send(context, cid, "❌ אין מספיק SLH-דמה.", True)
        await user_svc.add_balance(cid, slh=-amt)
        await user_svc.ensure_user(to); await user_svc.add_balance(to, slh=amt)
        await user_svc.add_order(Order(id=int(cid*1000)+2, type=OrderType.TRANSFER, frm=cid, to=to, amount=amt))
        await send(context, cid, f"🔁 הועברו {amt} SLH-דמה ל-{to}.", True)
        try:
            await send(context, to, f"💌 קיבלת {amt} SLH-דמה מ-{cid}.", True)
        except: pass
        return

    if t == "📜 היסטוריה":
        items = await user_svc.list_orders_for(cid)
        if not items:
            return await send(context, cid, "אין היסטוריה.", True)
        lines = [f"#{o['id']} {o['type']} {o['amount']} {o['asset']} → {o['status']}" for o in items[-15:]]
        return await send(context, cid, "היסטוריה:\n"+"\n".join(lines), True)

    return await send(context, cid, "לא זוהה. /start", u.paid)