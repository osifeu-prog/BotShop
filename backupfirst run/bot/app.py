import os, time, json, logging, re, asyncio
from typing import Dict, Any
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

load_dotenv()
log = logging.getLogger("Botshop")
logging.basicConfig(level=getattr(logging, (os.getenv("LOG_LEVEL","INFO")).upper(), logging.INFO))

TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN","")
ADMIN  = int(os.getenv("ADMIN_ID","0") or 0)
ADMIN_NAME = os.getenv("ADMIN_NAME","Admin")
STORE  = os.getenv("STORE_PATH","./data/store.json")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID","0") or 0)
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK","").strip()
ENTRY_PRICE_NIS = float(os.getenv("ENTRY_PRICE_NIS","39"))
DEMO_GRANT_SLH  = float(os.getenv("DEMO_GRANT_SLH","39"))
DEMO_GRANT_BNB  = float(os.getenv("DEMO_GRANT_BNB","0.05"))
PAY_BASE = os.getenv("PAYMENT_LINK_BASE","https://pay.example.com/checkout")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN missing")

_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

def _now(): return int(time.time())

def load_store() -> Dict[str, Any]:
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users":{}, "balances":{}, "orders":[]}

def save_store(d: Dict[str, Any]):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def reply_menu(paid: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("ًں“ٹ ×™×ھ×¨×”"), KeyboardButton("ًں‘¤ ×¤×¨×•×¤×™×œ")],
        [KeyboardButton("ًں§¾ ×ھ×©×œ×•×‌ ×›× ×™×،×”"), KeyboardButton("ًں”— ×©×‍×•×¨ ×گ×¨× ×§")],
    ]
    if paid:
        rows += [
            [KeyboardButton("ًں›’ ×§× ×™×™×” (×“×‍×”)"), KeyboardButton("ًںڈھ ×‍×›×™×¨×” (×“×‍×”)")],
            [KeyboardButton("ًں”پ ×”×¢×‘×¨×” (×“×‍×”)"), KeyboardButton("ًں“œ ×”×™×،×ک×•×¨×™×”")],
        ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def show(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, paid=False):
    is_admin = (chat_id == ADMIN)
    header = f"ًں‘‘ Admin: {ADMIN_NAME}\n" if is_admin else ""
    await context.bot.send_message(chat_id=chat_id, text=header+text, reply_markup=reply_menu(paid=paid))

def ensure_user(chat_id: int):
    s = load_store()
    s["users"].setdefault(str(chat_id), {"paid": False, "wallet":"", "joined_at": _now()})
    s["balances"].setdefault(str(chat_id), {"slh": 0.0, "bnb": 0.0})
    save_store(s)

def is_paid(chat_id: int) -> bool:
    s=load_store(); return bool(s["users"].get(str(chat_id),{}).get("paid", False))

def set_paid(chat_id: int, val: bool):
    s=load_store(); s["users"].setdefault(str(chat_id), {})["paid"]=val; save_store(s)

def set_wallet(chat_id: int, addr: str):
    s=load_store(); s["users"].setdefault(str(chat_id), {})["wallet"]=addr; save_store(s)

def get_wallet(chat_id: int) -> str:
    s=load_store(); return s["users"].get(str(chat_id),{}).get("wallet","")

def add_balance(chat_id: int, slh=0.0, bnb=0.0):
    s=load_store()
    b=s["balances"].setdefault(str(chat_id), {"slh":0.0,"bnb":0.0})
    b["slh"] = round(b.get("slh",0.0)+slh, 8)
    b["bnb"] = round(b.get("bnb",0.0)+bnb, 8)
    save_store(s)

def get_balance(chat_id: int) -> Dict[str,float]:
    s=load_store(); return s["balances"].get(str(chat_id), {"slh":0.0,"bnb":0.0})

def add_order(**kw):
    s=load_store()
    kw.setdefault("id", int(time.time()%1e9))
    kw.setdefault("ts", _now())
    kw.setdefault("status","open")
    s["orders"].append(kw)
    save_store(s)
    return kw

def list_orders(chat_id: int):
    s=load_store()
    return [o for o in s["orders"] if o.get("from")==chat_id or o.get("to")==chat_id]

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ensure_user(chat_id)
    txt = (
        "×‘×¨×•×ڑ ×”×‘×گ ×œض¾SLH Botshop (Sandbox) ًںژ®\n"
        f"â€¢ ×›× ×™×،×” ×œ×§×”×™×œ×”: â‚ھ{ENTRY_PRICE_NIS} (×—×“ض¾×¤×¢×‍×™) â€” ×ھ×§×‘×œ ×‍×¢× ×§ ×“×‍×” ×œ×”×ھ×—×œ×”\n"
        "â€¢ ×گ×—×¨×™ ×ھ×©×œ×•×‌: ×ھ×•×›×œ ×œ×ھ×¨×’×œ ×§× ×™×™×”/×‍×›×™×¨×”/×”×¢×‘×¨×” ×‘×‍×ک×‘×¢×•×ھ ×“×‍×”\n"
        "â€¢ ×©×‍×•×¨ 0xâ€¦ ×›×“×™ ×©× ×“×¢ ×œ×”×¦×™×’ ×¤×¨×•×¤×™×œ ×‍×œ×گ\n"
    )
    await show(context, chat_id, txt, paid=is_paid(chat_id))

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN:
        return await show(context, chat_id, "×œ×گ×“×‍×™×ں ×‘×œ×‘×“.")
    global ENTRY_PRICE_NIS
    if context.args:
        try:
            ENTRY_PRICE_NIS = float(context.args[0]); await show(context, chat_id, f"âœ… ×¢×•×“×›×ں ×‍×—×™×¨ ×›× ×™×،×”: â‚ھ{ENTRY_PRICE_NIS}", True)
        except:
            await show(context, chat_id, "×¢×¨×ڑ ×œ×گ ×ھ×§×™×ں.", True)
    else:
        await show(context, chat_id, f"×‍×—×™×¨ ×›× ×™×،×” × ×•×›×—×™: â‚ھ{ENTRY_PRICE_NIS}", True)

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN:
        return await show(context, chat_id, "×œ×گ×“×‍×™×ں ×‘×œ×‘×“.")
    if not context.args:
        return await show(context, chat_id, "×©×™×‍×•×©: /approve <chat_id>", True)
    try:
        uid = int(context.args[0])
        set_paid(uid, True)
        add_balance(uid, slh=DEMO_GRANT_SLH, bnb=DEMO_GRANT_BNB)
        await show(context, uid, f"âœ… ×ھ×©×œ×•×‌ ×گ×•×©×¨! ×§×™×‘×œ×ھ {DEMO_GRANT_SLH} SLH-×“×‍×” ×•ض¾{DEMO_GRANT_BNB} BNB-×“×‍×”.", True)
        await show(context, chat_id, f"âœ… ×گ×•×©×¨ ×œ×‍×©×ھ×‍×© {uid}.", True)
    except:
        await show(context, chat_id, "×©×’×™×گ×” ×‘×¢×™×‘×•×“.", True)

async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN:
        return await show(context, chat_id, "×œ×گ×“×‍×™×ں ×‘×œ×‘×“.")
    if not context.args:
        return await show(context, chat_id, "×©×™×‍×•×©: /revoke <chat_id>", True)
    try:
        uid = int(context.args[0]); set_paid(uid, False)
        await show(context, uid, "â›” ×”×”×¨×©×گ×” ×‘×•×ک×œ×”. ×¤× ×” ×œ×ھ×‍×™×›×”.", False)
        await show(context, chat_id, f"×‘×•×ک×œ×” ×”×¨×©×گ×” ×œ-{uid}.", True)
    except:
        await show(context, chat_id, "×©×’×™×گ×”.", True)

async def cmd_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != ADMIN: return await show(context, chat_id, "×œ×گ×“×‍×™×ں ×‘×œ×‘×“.")
    if len(context.args)<2: return await show(context, chat_id, "×©×™×‍×•×©: /give <chat_id> <SLH>", True)
    try:
        uid=int(context.args[0]); amt=float(context.args[1])
        add_balance(uid, slh=amt)
        await show(context, chat_id, f"× ×ھ×ھ {amt} SLH-×“×‍×” ×œ-{uid}.", True)
        await show(context, uid, f"ًںژپ ×”×ھ×§×‘×œ×• {amt} SLH-×“×‍×” ×‍×”×گ×“×‍×™×ں.", is_paid(uid))
    except:
        await show(context, chat_id, "×©×’×™×گ×”.", True)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()
    ensure_user(chat_id)
    paid = is_paid(chat_id)

    # Reply keyboard map
    if text == "ًں“ٹ ×™×ھ×¨×”":
        bal = get_balance(chat_id)
        return await show(context, chat_id, f"×™×ھ×¨×” (×“×‍×”):\nâ€¢ SLH: {bal['slh']}\nâ€¢ BNB: {bal['bnb']}", paid)
    if text == "ًں‘¤ ×¤×¨×•×¤×™×œ":
        w = get_wallet(chat_id); status = "âœ… ×‍×©×•×œ×‌" if paid else "â›” ×œ×گ ×©×•×œ×‌"
        return await show(context, chat_id, f"×¤×¨×•×¤×™×œ:\nâ€¢ ×،×ک×ک×•×،: {status}\nâ€¢ ×گ×¨× ×§: {w or '(×œ×گ × ×©×‍×¨)'}", paid)
    if text == "ًں§¾ ×ھ×©×œ×•×‌ ×›× ×™×،×”":
        url = f"{PAY_BASE}?uid={chat_id}&amt={int(ENTRY_PRICE_NIS)}"
        return await show(context, chat_id, f"×œ×ھ×©×œ×•×‌ â‚ھ{int(ENTRY_PRICE_NIS)}:\n{url}\n×œ×گ×—×¨ ×ھ×©×œ×•×‌, ×”×گ×“×‍×™×ں ×™×گ×©×¨ ×گ×•×ھ×ڑ ×™×“× ×™×ھ (×–×‍× ×™).", paid)
    if text == "ًں”— ×©×‍×•×¨ ×گ×¨× ×§":
        context.user_data["await_wallet"]=True
        return await show(context, chat_id, "×©×œ×— ×¢×›×©×™×• ×›×ھ×•×‘×ھ MetaMask (0xâ€¦)", paid)
    if context.user_data.get("await_wallet"):
        context.user_data["await_wallet"]=False
        if _ADDR_RE.match(text):
            set_wallet(chat_id, text)
            return await show(context, chat_id, "âœ… × ×©×‍×¨!", paid)
        return await show(context, chat_id, "×›×ھ×•×‘×ھ ×œ×گ ×ھ×§×™× ×”.", paid)

    if not paid:
        return await show(context, chat_id, "â›” ×“×¨×•×© ×ھ×©×œ×•×‌ ×›× ×™×،×” ×›×“×™ ×œ×”×©×ھ×‍×© ×‘×¤×¢×•×œ×•×ھ ×”×“×‍×”.", False)

    # Paid-only demo actions
    if text == "ًں›’ ×§× ×™×™×” (×“×‍×”)":
        context.user_data["await_buy"]=True
        return await show(context, chat_id, "×›×‍×” SLH ×ھ×¨×¦×”? (×‍×،×¤×¨)", True)
    if context.user_data.get("await_buy"):
        context.user_data["await_buy"]=False
        try:
            amt=float(text); add_balance(chat_id, slh=amt)
            add_order(id=int(time.time()%1e9), type="buy", from=chat_id, to=chat_id, amount=amt, asset="SLH")
            return await show(context, chat_id, f"ًں›’ ×‘×•×¦×¢×” ×§× ×™×™×” (×“×‍×”): +{amt} SLH.", True)
        except:
            return await show(context, chat_id, "×‍×،×¤×¨ ×œ×گ ×ھ×§×™×ں.", True)

    if text == "ًںڈھ ×‍×›×™×¨×” (×“×‍×”)":
        context.user_data["await_sell"]=True
        return await show(context, chat_id, "×›×‍×” SLH ×œ×‍×›×•×¨? (×‍×،×¤×¨)", True)
    if context.user_data.get("await_sell"):
        context.user_data["await_sell"]=False
        try:
            amt=float(text); bal=get_balance(chat_id)
            if bal["slh"]<amt: return await show(context, chat_id, "×گ×™×ں ×‍×،×¤×™×§ SLH-×“×‍×”.", True)
            add_balance(chat_id, slh=-amt)
            add_order(id=int(time.time()%1e9), type="sell", from=chat_id, to=chat_id, amount=amt, asset="SLH")
            return await show(context, chat_id, f"ًںڈھ ×‍×›×™×¨×” (×“×‍×”): -{amt} SLH.", True)
        except:
            return await show(context, chat_id, "×‍×،×¤×¨ ×œ×گ ×ھ×§×™×ں.", True)

    if text == "ًں”پ ×”×¢×‘×¨×” (×“×‍×”)":
        context.user_data["await_to"]=True
        return await show(context, chat_id, "×©×œ×— chat_id ×©×œ ×—×‘×¨ ×œ×”×¢×‘×¨×” (×“×‍×”).", True)
    if context.user_data.get("await_to"):
        try:
            to=int(text); context.user_data["await_to"]=False; context.user_data["await_amt"]=to
            return await show(context, chat_id, "×›×‍×” SLH ×œ×”×¢×‘×™×¨? (×‍×،×¤×¨)", True)
        except:
            context.user_data["await_to"]=False
            return await show(context, chat_id, "chat_id ×œ×گ ×ھ×§×™×ں.", True)
    if context.user_data.get("await_amt"):
        try:
            to=context.user_data.pop("await_amt")
            amt=float(text); bal=get_balance(chat_id)
            if bal["slh"]<amt: return await show(context, chat_id, "×گ×™×ں ×‍×،×¤×™×§ SLH-×“×‍×”.", True)
            add_balance(chat_id, slh=-amt); ensure_user(to); add_balance(to, slh=amt)
            add_order(id=int(time.time()%1e9), type="transfer", from=chat_id, to=to, amount=amt, asset="SLH")
            await show(context, chat_id, f"ًں”پ ×”×•×¢×‘×¨×• {amt} SLH-×“×‍×” ×œ-{to}.", True)
            try: await show(context, to, f"ًں’Œ ×§×™×‘×œ×ھ {amt} SLH-×“×‍×” ×‍-{chat_id}.", is_paid(to))
            except: pass
            return
        except:
            context.user_data.pop("await_amt", None)
            return await show(context, chat_id, "×‍×،×¤×¨ ×œ×گ ×ھ×§×™×ں.", True)

    if text == "ًں“œ ×”×™×،×ک×•×¨×™×”":
        items = list_orders(chat_id)
        if not items: return await show(context, chat_id, "×گ×™×ں ×”×™×،×ک×•×¨×™×”.", True)
        lines = [f"#{o['id']} {o['type']} {o['amount']} {o['asset']} â†’ status={o['status']}" for o in items[-15:]]
        return await show(context, chat_id, "×”×™×،×ک×•×¨×™×”:\n"+"\n".join(lines), True)

    # Admin shortcuts
    if text.startswith("/price"): return await cmd_price(update, context)

    return await show(context, chat_id, "×œ×گ ×–×•×”×”. /start", paid)

def build_app():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.add_handler(CommandHandler("give", cmd_give))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app

def main():
    log.info("Botshop startingâ€¦")
    app = build_app()
    app.run_polling()

if __name__ == "__main__":
    main()
