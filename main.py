# -*- coding: utf-8 -*-
# NIFTII – Bot Shop / Wallet / Payments – single-file edition
# Author: You
import os
import asyncio
import random
import glob
import sqlite3
import logging
from datetime import datetime
from decimal import Decimal

from aiohttp import web
from dotenv import load_dotenv

from telegram import (
    Bot, Update,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.utils.request import Request
from telegram.error import BadRequest

# =========================
# ENV & Logging
# =========================
load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("niftii")

BOT_TOKEN           = os.getenv("BOT_TOKEN")
PUBLIC_URL          = os.getenv("PUBLIC_URL", "")
WEBHOOK_ROUTE       = os.getenv("WEBHOOK_ROUTE", "/webhook")

# קבוצות / זרימת אישורים
PAYMENTS_CHAT_ID    = int(os.getenv("PAYMENTS_CHAT_ID", "0") or 0)     # לקבלת אישורים + כפתורי אדמין
APPROVED_CHAT_ID    = int(os.getenv("APPROVED_CHAT_ID", "0") or 0)     # רק מאושרים
ARCHIVE_CHAT_ID     = int(os.getenv("ARCHIVE_CHAT_ID", "0") or 0)      # דחויים/ארכיון
GAME_MAIN_GROUP_ID  = int(os.getenv("GAME_MAIN_GROUP_ID", "0") or 0)   # קהילת המשחק
GAME_MAIN_GROUP_URL = os.getenv("GAME_MAIN_GROUP_URL", "")             # לינק הצטרפות (אם יש)

# אדמין יחיד לפי בקשתך
ADMIN_ID            = int(os.getenv("ADMIN_ID", "0") or 0) or None

# BSC / SLH
BSC_RPC_URL         = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org/")
BSC_CHAIN_ID        = int(os.getenv("BSC_CHAIN_ID", "56"))
SELA_TOKEN_ADDRESS  = os.getenv("SELA_TOKEN_ADDRESS", "").strip()
TREASURY_ADDRESS    = os.getenv("TREASURY_ADDRESS", "") or None
TREASURY_PRIVATE_KEY= os.getenv("TREASURY_PRIVATE_KEY", "") or None
SELA_NIS_VALUE      = float(os.getenv("SELA_NIS_VALUE", "244"))

# AI (לא חובה; שמור לעתיד)
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
HF_API_TOKEN        = os.getenv("HF_API_TOKEN", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN חסר ב-Variables")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID חסר ב-Variables")
if not SELA_TOKEN_ADDRESS:
    raise RuntimeError("SELA_TOKEN_ADDRESS חסר ב-Variables")

# =========================
# Telegram + Web
# =========================
bot    = Bot(token=BOT_TOKEN, request=Request(con_pool_size=8))
app    = web.Application()
routes = web.RouteTableDef()

# =========================
# DB (SQLite)
# =========================
conn = sqlite3.connect('bot.db', check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS users(
    id           INTEGER PRIMARY KEY,
    username     TEXT,
    name         TEXT,
    wallet_bsc   TEXT,
    created_at   TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS payments(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    chat_id         INTEGER,
    amount_fiat     REAL,
    proof_file_id   TEXT,
    proof_type      TEXT, -- photo/document
    status          TEXT, -- pending/approved/rejected
    group_msg_id    INTEGER,
    created_at      TEXT,
    updated_at      TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS demo_state(
    chat_id INTEGER PRIMARY KEY,
    idx     INTEGER
)
""")
# המתנה לטקסט אדמין לאחר לחיצה על "✉️ הודעה ללקוח"
conn.execute("""
CREATE TABLE IF NOT EXISTS admin_reply_wait(
    admin_id   INTEGER,
    payment_id INTEGER,
    PRIMARY KEY (admin_id, payment_id)
)
""")
conn.commit()

# =========================
# Web3 / SLH
# =========================
from web3 import Web3
w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
try:
    w3_connected = w3.is_connected()
except Exception:
    w3_connected = False
if not w3_connected:
    log.warning("[web3] Not connected to %s", BSC_RPC_URL)

ERC20_ABI = [
  {"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
  {"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
  {"constant":True,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},
  {"constant":False,"inputs":[{"name":"recipient","type":"address"},{"name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"},
]
ERC20 = None
try:
    if SELA_TOKEN_ADDRESS:
        ERC20 = w3.eth.contract(address=Web3.to_checksum_address(SELA_TOKEN_ADDRESS), abi=ERC20_ABI)
except Exception as e:
    log.error("[web3] Contract init failed: %s", e)

def token_decimals():
    try: return ERC20.functions.decimals().call()
    except: return 18
def token_symbol():
    try: return ERC20.functions.symbol().call()
    except: return "SLH"
def to_decimal(raw: int, decimals: int) -> Decimal:
    q = Decimal(10) ** decimals
    return Decimal(raw) / q
def nis_to_tokens(amount_nis: float) -> Decimal:
    return Decimal(str(amount_nis)) / Decimal(str(SELA_NIS_VALUE))
def to_raw_tokens(amount_tokens: Decimal, decimals: int) -> int:
    q = Decimal(10) ** decimals
    return int((amount_tokens * q).to_integral_value())

def transfer_tokens_onchain(to_addr: str, amount_tokens: Decimal, gas_limit: int = 120000) -> str:
    if not ERC20:
        raise RuntimeError("ERC20 not initialized")
    if not TREASURY_PRIVATE_KEY or not TREASURY_ADDRESS:
        raise RuntimeError("TREASURY not configured")
    to = Web3.to_checksum_address(to_addr)
    dec = token_decimals()
    raw = to_raw_tokens(amount_tokens, dec)
    nonce = w3.eth.get_transaction_count(TREASURY_ADDRESS)
    gas_price = w3.eth.gas_price
    tx = ERC20.functions.transfer(to, raw).build_transaction({
        "chainId": BSC_CHAIN_ID,
        "gas": gas_limit,
        "gasPrice": gas_price,
        "nonce": nonce
    })
    pk = TREASURY_PRIVATE_KEY[2:] if TREASURY_PRIVATE_KEY.startswith("0x") else TREASURY_PRIVATE_KEY
    signed = w3.eth.account.sign_transaction(tx, private_key=pk)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    return tx_hash.hex()

# =========================
# Utils (Telegram send)
# =========================
async def tg_send(chat_id, text, **kwargs):
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, text, **kwargs))
async def tg_send_photo(chat_id, file_or_id, **kwargs):
    asyncio.create_task(asyncio.to_thread(bot.send_photo, chat_id, file_or_id, **kwargs))
async def tg_send_document(chat_id, file_id, **kwargs):
    asyncio.create_task(asyncio.to_thread(bot.send_document, chat_id, file_id, **kwargs))

def is_admin(update: Update) -> bool:
    try:
        uid = update.effective_user.id
    except:
        return False
    return bool(ADMIN_ID and uid == ADMIN_ID)

# =========================
# Gallery / Images
# =========================
IMAGES = []
for ext in ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp"):
    IMAGES.extend(glob.glob(os.path.join("images", ext)))
IMAGES = sorted(IMAGES)
def has_images(): return len(IMAGES) > 0

# =========================
# UI Texts
# =========================
WELCOME_TITLE = "🎉 ברוכים הבאים ל-NIFTII!! משחק ה-NFT שמשגע את המדינה! 🔥"
WELCOME_BODY = (
    "💎 *היום זה כבר לא חלום* — לכל אחד ואחת יכול להיות קניון!! 🛍️\n"
    "רוצים לדעת איך אתם יכולים להיות מיליונרים ובקרוב? 👉\n"
    "לחצו על \"מידע\" כדי להבין איך להרוויח דרך חנות קלפים משלכם בטלגרם."
)
INFO_PAGES = [
    "בוט זה יסייע לכם להרחיב מכירות, להגדיל שפע כלכלי, ולבנות קהילה סביבכם!",
    "🖼️ נכס דיגיטלי רווחי — חנות לקלפי NFT משלכם! רווחים ממכירה חוזרת 💸",
    "הבוט בנוי כחנות קלפים: רוכשים קלף + חנות ומשווקים למכירה חוזרת, מרוויחים מכל מכירה.",
    "WIN WIN: אתם משתפים ומרוויחים ישירות לבנק; אנחנו מרוויחים מהצטרפות אספנים חדשים.",
    "הצטרפות ל-NIFTII מביאה דירוג/חשיפה/הטבות, ועתיד הנפקה בבורסות.",
    "המשחק מבוסס NFT/קריפטו. לתמונות יש ערך כלכלי אמיתי.",
    "✅ שיווק רשתי ✅ הכנסה קבועה ✅ ללא התחייבות ✅ הפתעות ותמלוגים",
    "התחילו ב\"🃏 קנה קלף 39₪\" או \"🏬 פתח חנות 244₪\"."
]

DEMO_PRICE_PROMPT = (
    "5) איזה מחיר תרצו לגבות על הקלף שלכם?\n"
    "6) אנא הזינו מחיר (בש\"ח), לדוגמה: 120"
)

# Reply Keyboards
KB_INFO            = "ℹ️ מידע"
KB_BUY_CARD        = "🃏 קנה קלף 39₪"
KB_OPEN_SHOP       = "🏬 פתח חנות 244₪"
KB_WALLET_TG       = "🧧 ארנק טלגרם"
KB_ADD_WALLET      = "➕ הוסף ארנק"
KB_MY_WALLET       = "👛 הארנק שלי"
KB_PAYPAL          = "💳 פייפאל"
KB_BIT             = "📱 ביט/פייבוקס"
KB_BANK            = "🏦 העברה בנקאית"
KB_CONTACT         = "✉️ צור קשר"

def build_user_kb():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(KB_INFO), KeyboardButton(KB_BUY_CARD)],
            [KeyboardButton(KB_OPEN_SHOP), KeyboardButton(KB_MY_WALLET)],
            [KeyboardButton(KB_WALLET_TG), KeyboardButton(KB_ADD_WALLET)],
            [KeyboardButton(KB_PAYPAL), KeyboardButton(KB_BIT)],
            [KeyboardButton(KB_BANK), KeyboardButton(KB_CONTACT)],
        ],
        resize_keyboard=True
    )

def build_admin_kb():
    # תפריט אדמין — בסיסי
    kb = build_user_kb().keyboard
    kb.insert(0, [KeyboardButton("/echoid"), KeyboardButton("/help")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def info_nav_kb(idx: int):
    prev_idx = max(0, idx - 1)
    next_idx = min(len(INFO_PAGES) - 1, idx + 1)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️", callback_data=f"info_{prev_idx}"),
            InlineKeyboardButton("➡️", callback_data=f"info_{next_idx}")
        ],
    ])

def payments_admin_kb(payment_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ אשר", callback_data=f"payok_{payment_id}"),
        InlineKeyboardButton("❌ דחה", callback_data=f"payno_{payment_id}"),
        InlineKeyboardButton("✉️ הודעה ללקוח", callback_data=f"paymsg_{payment_id}"),
    ]])

# =========================
# Command registry
# =========================
handlers = {}
def command(name):
    def decorator(fn):
        handlers[name.lower()] = fn
        return fn
    return decorator

# =========================
# Commands
# =========================
@command('/start')
def start_cmd(update: Update):
    chat_id = update.effective_chat.id
    uid     = update.effective_user.id if update.effective_user else None
    uname   = update.effective_user.username if update.effective_user else ""
    name    = (update.effective_user.first_name or "") + " " + (update.effective_user.last_name or "") if update.effective_user else ""

    # upsert user
    conn.execute("INSERT OR IGNORE INTO users(id, username, name, created_at) VALUES(?,?,?,?)",
                 (uid, uname, name.strip(), datetime.utcnow().isoformat()))
    conn.commit()

    caption = f"{WELCOME_TITLE}\n\n{WELCOME_BODY}"
    reply_kb = build_admin_kb() if (uid == ADMIN_ID) else build_user_kb()

    if has_images():
        img = random.choice(IMAGES)
        asyncio.create_task(asyncio.to_thread(
            bot.send_photo, chat_id, open(img, "rb"),
            caption=caption, parse_mode="Markdown", reply_markup=reply_kb
        ))
    else:
        asyncio.create_task(asyncio.to_thread(
            bot.send_message, chat_id, caption,
            parse_mode="Markdown", reply_markup=reply_kb
        ))

@command('/help')
def help_cmd(update: Update):
    chat_id = update.effective_chat.id
    text = (
        "/start – התחלה\n"
        "/help – עזרה\n"
        "/echoid – קבלת Chat ID\n"
        "/set_wallet 0x... – שמירת ארנק BSC לקבלת תגמולים\n"
        "/my_wallet – צפייה בארנק וביתרה (SLH)\n"
    )
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, text, reply_markup=build_user_kb()))

@command('/echoid')
def echoid_cmd(update: Update):
    chat = update.effective_chat
    text = f"chat.type={chat.type}\nchat.id={chat.id}"
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat.id, text, reply_markup=build_user_kb()))

@command('/set_wallet')
def set_wallet_cmd(update: Update):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id if update.effective_user else None
    parts = (update.message.text or "").split(maxsplit=1)
    if not uid:
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, "לא זוהה משתמש.", reply_markup=build_user_kb()))
        return
    if len(parts) < 2 or not parts[1].startswith("0x") or len(parts[1]) != 42:
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id,
            "שימוש: /set_wallet 0xכתובתBSC חוקית\n(טיפ: העתק/הדבק מ-MetaMask)", reply_markup=build_user_kb()))
        return
    addr = parts[1]
    # ensure column
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if 'wallet_bsc' not in cols:
        try: conn.execute("ALTER TABLE users ADD COLUMN wallet_bsc TEXT")
        except Exception: pass
    conn.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
    conn.execute("UPDATE users SET wallet_bsc=? WHERE id=?", (addr, uid))
    conn.commit()
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, f"✅ עודכן ארנק BSC: {addr}", reply_markup=build_user_kb()))

@command('/my_wallet')
def my_wallet_cmd(update: Update):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id if update.effective_user else None
    row = conn.execute("SELECT wallet_bsc FROM users WHERE id=?", (uid,)).fetchone()
    addr = row[0] if row and row[0] else None
    if not addr:
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id,
            "אין עדיין ארנק. לחץ/י על \"➕ הוסף ארנק\" או השתמש/י ב־/set_wallet 0x...", reply_markup=build_user_kb()))
        return
    # balance
    try:
        dec = token_decimals()
        sym = token_symbol()
        bal_raw = ERC20.functions.balanceOf(Web3.to_checksum_address(addr)).call() if ERC20 else 0
        bal = to_decimal(bal_raw, dec)
        text = f"👛 הארנק שלך:\n{addr}\nיתרה: {bal} {sym}"
    except Exception as e:
        text = f"👛 הארנק שלך:\n{addr}\nיתרה: ? (שגיאת RPC: {e})"
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, text, reply_markup=build_user_kb()))

# אדמין בלבד – טסט תגמול on-chain
@command('/reward_test')
def reward_test_cmd(update: Update):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id if update.effective_user else None
    if not (ADMIN_ID and uid == ADMIN_ID):
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, "פקודה זו זמינה לאדמין בלבד.", reply_markup=build_admin_kb()))
        return
    parts = (update.message.text or "").split()
    if len(parts) != 3:
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, "שימוש: /reward_test <₪> <0xwallet>", reply_markup=build_admin_kb()))
        return
    try:
        amount_nis = float(parts[1]); to_wallet  = parts[2]
        if not (to_wallet.startswith("0x") and len(to_wallet) == 42):
            raise ValueError("כתובת לא חוקית")
        tokens = nis_to_tokens(amount_nis)
        async def do_send():
            try:
                txh = await asyncio.to_thread(transfer_tokens_onchain, to_wallet, tokens)
                await tg_send(chat_id, f"✅ נשלח תגמול של ~{tokens} {token_symbol()} עבור {amount_nis}₪\n🔗 https://bscscan.com/tx/{txh}")
            except Exception as e:
                await tg_send(chat_id, f"❌ שגיאה בשליחת תגמול: {e}")
        asyncio.create_task(do_send())
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, "מבצע שליחה on-chain…", reply_markup=build_admin_kb()))
    except Exception as e:
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, f"שגיאה: {e}", reply_markup=build_admin_kb()))

# =========================
# Callback handling
# =========================
async def on_callback(cq, update: Update):
    try:
        await asyncio.to_thread(bot.answer_callback_query, cq['id'])
    except BadRequest as e:
        log.debug("answer_callback_query: %s", e)

    data    = cq.get('data') or ""
    from_uid= cq.get('from',{}).get('id')
    # INFO pages
    if data.startswith("info_"):
        try: idx = int(data.split("_")[1])
        except: idx = 0
        idx = max(0, min(idx, len(INFO_PAGES)-1))
        await tg_send(cq['message']['chat']['id'], INFO_PAGES[idx], reply_markup=info_nav_kb(idx))
        return

    # Payments moderation
    if data.startswith("payok_") and from_uid == ADMIN_ID:
        pid = int(data.split("_")[1])
        row = conn.execute("SELECT user_id, chat_id, proof_file_id, proof_type FROM payments WHERE id=?", (pid,)).fetchone()
        if not row:
            await tg_send(cq['message']['chat']['id'], f"לא נמצא תשלום id={pid}")
            return
        user_id, user_chat, file_id, ptype = row
        # עדכון סטטוס
        conn.execute("UPDATE payments SET status=?, updated_at=? WHERE id=?", ("approved", datetime.utcnow().isoformat(), pid))
        conn.commit()
        # פידבק למשתמש
        await tg_send(user_chat, "✅ האישור התקבל ואושר! תודה 🌟")
        # שליחה לערוץ מאושרים (אם הוגדר)
        if APPROVED_CHAT_ID:
            caption = f"✅ תשלום מאושר (payment_id={pid})"
            if ptype == "photo":
                await tg_send_photo(APPROVED_CHAT_ID, file_id, caption=caption)
            else:
                await tg_send_document(APPROVED_CHAT_ID, file_id, caption=caption)
        # הזמנה לקבוצת המשחק (בהודעה עם לינק אם הוגדר)
        if GAME_MAIN_GROUP_URL:
            await tg_send(user_chat, f"📣 הצטרפו לקהילת המשחק: {GAME_MAIN_GROUP_URL}")
        elif GAME_MAIN_GROUP_ID:
            await tg_send(user_chat, "📣 הצטרפו לקהילת המשחק שלנו (פנה למנהל לקבלת לינק).")
        await tg_send(cq['message']['chat']['id'], f"✔️ אושר (payment_id={pid})")
        return

    if data.startswith("payno_") and from_uid == ADMIN_ID:
        pid = int(data.split("_")[1])
        row = conn.execute("SELECT user_id, chat_id, proof_file_id, proof_type FROM payments WHERE id=?", (pid,)).fetchone()
        if not row:
            await tg_send(cq['message']['chat']['id'], f"לא נמצא תשלום id={pid}")
            return
        user_id, user_chat, file_id, ptype = row
        conn.execute("UPDATE payments SET status=?, updated_at=? WHERE id=?", ("rejected", datetime.utcnow().isoformat(), pid))
        conn.commit()
        await tg_send(user_chat, "❌ הבדיקה הושלמה – התשלום נדחה. אפשר לנסות שוב/ליצור קשר.")
        if ARCHIVE_CHAT_ID:
            caption = f"📦 תשלום דחוי/לארכיון (payment_id={pid})"
            if ptype == "photo":
                await tg_send_photo(ARCHIVE_CHAT_ID, file_id, caption=caption)
            else:
                await tg_send_document(ARCHIVE_CHAT_ID, file_id, caption=caption)
        await tg_send(cq['message']['chat']['id'], f"✖️ נדחה (payment_id={pid})")
        return

    if data.startswith("paymsg_") and from_uid == ADMIN_ID:
        pid = int(data.split("_")[1])
        # רשום המתנה להודעת טקסט מהאדמין
        conn.execute("INSERT OR REPLACE INTO admin_reply_wait(admin_id, payment_id) VALUES(?,?)", (ADMIN_ID, pid))
        conn.commit()
        await tg_send(cq['message']['chat']['id'], f"✍️ כתוב/כתבי עכשיו את ההודעה ללקוח (payment_id={pid}) כהודעה חדשה בקבוצה זו.")
        return

# =========================
# on_message – main logic
# =========================
async def on_message(update: Update):
    chat = update.effective_chat
    chat_id = chat.id
    msg     = update.message
    text    = (msg.text or "").strip()
    uid     = update.effective_user.id if update.effective_user else None
    uname   = update.effective_user.username if update.effective_user else ""
    name    = (update.effective_user.first_name or "") + " " + (update.effective_user.last_name or "") if update.effective_user else ""

    # רישום משתמש בסיסי
    conn.execute("INSERT OR IGNORE INTO users(id, username, name, created_at) VALUES(?,?,?,?)",
                 (uid, uname, name.strip(), datetime.utcnow().isoformat()))
    conn.commit()

    # 0) האם זו הודעת טקסט של אדמין אחרי "✉️ הודעה ללקוח"?
    if chat_id == PAYMENTS_CHAT_ID and msg and msg.text and uid == ADMIN_ID:
        row = conn.execute("SELECT payment_id FROM admin_reply_wait WHERE admin_id=?", (ADMIN_ID,)).fetchone()
        if row:
            pid = row[0]
            prow = conn.execute("SELECT chat_id FROM payments WHERE id=?", (pid,)).fetchone()
            if prow:
                user_chat = prow[0]
                await tg_send(user_chat, f"📬 הודעה מהמנהל:\n\n{msg.text}")
                await tg_send(PAYMENTS_CHAT_ID, f"✉️ נשלחה הודעה ללקוח (payment_id={pid})")
            conn.execute("DELETE FROM admin_reply_wait WHERE admin_id=?", (ADMIN_ID,))
            conn.commit()
            return

    # 1) קבצי תמונה/מסמך — נועדים לאישורי תשלום
    if msg and (msg.photo or msg.document):
        # רק פותח תיעוד; ההפצה החוצה לפי מדיניות: מאושרות -> APPROVED_CHAT, דחויות -> ARCHIVE_CHAT
        if msg.photo:
            file_id = msg.photo[-1].file_id
            ptype   = "photo"
        else:
            file_id = msg.document.file_id
            ptype   = "document"

        # יצירת רשומת תשלום
        conn.execute("""
            INSERT INTO payments(user_id, chat_id, amount_fiat, proof_file_id, proof_type, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
        """, (uid, chat_id, None, file_id, ptype, "pending", datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

        who  = f"{update.effective_user.first_name or ''} {update.effective_user.last_name or ''} | @{uname or ''} | id={uid}"
        caption = f"🧾 אישור תשלום מהמשתמש:\n{who}\n\npayment_id={pid}"

        if PAYMENTS_CHAT_ID:
            if ptype == "photo":
                await tg_send_photo(PAYMENTS_CHAT_ID, file_id, caption=caption, reply_markup=payments_admin_kb(pid))
            else:
                await tg_send_document(PAYMENTS_CHAT_ID, file_id, caption=caption, reply_markup=payments_admin_kb(pid))
        await tg_send(chat_id, "✅ האישור התקבל והועבר לבדיקה. תקבל/י עדכון לאחר בדיקה.")
        return

    # 2) כפתורי Reply Keyboard / UX
    if text == KB_INFO:
        await tg_send(chat_id, INFO_PAGES[0], reply_markup=info_nav_kb(0))
        return

    if text == KB_BUY_CARD:
        await tg_send(chat_id,
            "💥 קלף זה יכול להיות שלכם *למכירה חוזרת כבר היום!*\n"
            "🏷️ *מבצע היום —* 39 ₪ בלבד\n"
            "🖼️ הזינו מחיר מכירה שתבקשו מהחברים (בש\"ח), לדוגמה: 120.\n\n"
            + DEMO_PRICE_PROMPT,
            parse_mode="Markdown", reply_markup=build_user_kb())
        conn.execute("INSERT OR REPLACE INTO demo_state(chat_id, idx) VALUES(?,?)", (chat_id, 1))
        conn.commit()
        return

    if text == KB_OPEN_SHOP:
        await tg_send(chat_id,
            "🛍️ פתיחת חנות בעלות *244 ₪* כוללת עד 8 תמונות למכירה חוזרת.\n"
            "להשלמת רכישה: בחר/י אמצעי תשלום (ארנק טלגרם/פייפאל/ביט/בנק) ושלח/י צילום אישור כאן.\n"
            "לאחר מכן נמלא פרטים ונפתח את החנות.",
            parse_mode="Markdown", reply_markup=build_user_kb())
        return

    if text == KB_WALLET_TG:
        # נסה לשלוח תמונה אם קיימת
        img_path = os.path.join("images", "sample.png")
        if os.path.exists(img_path):
            await tg_send_photo(chat_id, open(img_path, "rb"),
                                caption="יש לכם ארנק בטלגרם? לחצו @wallet ופתחו ארנק קריפטו מאובטח!")
        else:
            await tg_send(chat_id, "יש לכם ארנק בטלגרם? לחצו @wallet ופתחו ארנק קריפטו מאובטח!")

        await asyncio.sleep(0.3)
        await tg_send(chat_id, "הארנק בטלגרם מוגדר כהשקעה—נהדר לחיסכון עתידי וכלכלה חופשית ובריאה.")
        await asyncio.sleep(0.3)
        await tg_send(chat_id, "להעברה לחשבון המפתח:\nUQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp")
        return

    if text == KB_ADD_WALLET:
        await tg_send(chat_id,
            "📎 הדביקו כאן את כתובת ה־BSC שלכם מ־MetaMask (פורמט 0x… באורך 42 תווים)\n"
            "או השתמשו בפקודה: /set_wallet 0xYourBSCAddress")
        return

    if text == KB_MY_WALLET:
        my_wallet_cmd(update)
        return

    if text == KB_PAYPAL:
        await tg_send(chat_id, "פייפאל: https://paypal.me/osifdu")
        return

    if text == KB_BIT:
        await tg_send(chat_id, "ביט/פייבוקס להעברה: 0546671882")
        return

    if text == KB_BANK:
        await tg_send(chat_id,
            "פרטי העברה בנקאית:\n"
            "המוטב: קאופמן צביקה\n"
            "בנק הפועלים | סניף כפר גנים (153) | חשבון 73462")
        return

    if text == KB_CONTACT:
        await tg_send(chat_id, "📮 צור קשר: https://t.me/OsifFin")
        return

    # 3) קליטת מחיר לדמו
    state = conn.execute("SELECT idx FROM demo_state WHERE chat_id=?", (chat_id,)).fetchone()
    if state and state[0] == 1 and text.replace(".", "", 1).isdigit():
        try:
            price_nis = float(text)
        except Exception:
            price_nis = None
        conn.execute("DELETE FROM demo_state WHERE chat_id=?", (chat_id,))
        conn.commit()
        if price_nis is not None:
            try:
                pct = round(max(5.0, min(95.0, (price_nis / 39.0) * 30.0)), 1)
            except Exception:
                pct = 40.0
            await tg_send(chat_id,
                f"👏 לפי המחיר שביקשתם ({price_nis:.2f}₪) תוכלו להרוויח ~{pct}% מכל מכירה חוזרת!\n"
                "כדי להשלים: שלחו כאן צילום אישור תשלום (תמונה/מסמך).")
            return

    # 4) פקודות טקסט
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        fn  = handlers.get(cmd)
        if fn:
            fn(update)
        else:
            await tg_send(chat_id, "פקודה לא מוכרת. /help לקבלת עזרה.", reply_markup=build_user_kb())
    else:
        # Echo ברירת מחדל (לוגית)
        await tg_send(chat_id, f"Echo: {text}", reply_markup=build_user_kb())

# =========================
# Webhook routes
# =========================
@routes.get("/")
async def health(_):
    return web.Response(text="OK")

@routes.post(WEBHOOK_ROUTE)
async def handle(request):
    data = await request.json()

    # 1) callback_query
    if 'callback_query' in data:
        update = Update.de_json(data, bot)
        await on_callback(data['callback_query'], update)
        return web.Response(text="OK")

    # 2) no message
    if 'message' not in data:
        return web.Response(text="OK")

    # 3) message
    update = Update.de_json(data, bot)
    await on_message(update)
    return web.Response(text="OK")

app.add_routes(routes)

# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    log.info("Starting NIFTII on port %s (route=%s)", port, WEBHOOK_ROUTE)
    if PUBLIC_URL:
        log.info("Webhook expected at: %s%s", PUBLIC_URL, WEBHOOK_ROUTE)
    web.run_app(app, port=port)
