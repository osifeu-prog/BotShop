# niftii_bot_improved.py
import os
import asyncio
import random
import glob
import logging
from pathlib import Path
from decimal import Decimal
from typing import Optional

import aiosqlite
from aiohttp import web
from dotenv import load_dotenv

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TelegramError

from web3 import Web3, exceptions as w3_exceptions

# =========================
# Config
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN in environment")

PUBLIC_URL = os.getenv("PUBLIC_URL", "")
WEBHOOK_ROUTE = os.getenv("WEBHOOK_ROUTE", "/webhook")
PORT = int(os.getenv("PORT", "8080"))

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0) or None
PAYMENTS_CHAT_ID = int(os.getenv("PAYMENTS_CHAT_ID", "0") or 0) or None

BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org/")
BSC_CHAIN_ID = int(os.getenv("BSC_CHAIN_ID", "56"))
SELA_TOKEN_ADDRESS = os.getenv("SELA_TOKEN_ADDRESS", "0xACb0A09414CEA1C879c67bB7A877E4e19480f022")
TREASURY_ADDRESS = os.getenv("TREASURY_ADDRESS")
TREASURY_PRIVATE_KEY = os.getenv("TREASURY_PRIVATE_KEY")
SELA_NIS_VALUE = Decimal(os.getenv("SELA_NIS_VALUE", "240"))

DB_PATH = Path(os.getenv("DB_PATH", "bot.db"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", "images"))

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("niftii")

# =========================
# Telegram bot + web app
# =========================
bot = Bot(token=BOT_TOKEN)
app = web.Application()
routes = web.RouteTableDef()

# =========================
# Web3 setup
# =========================
w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL, request_kwargs={"timeout": 10}))
try:
    W3_CONNECTED = w3.is_connected()
except Exception:
    W3_CONNECTED = False
if not W3_CONNECTED:
    logger.warning("web3 not connected to RPC %s", BSC_RPC_URL)

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "recipient", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
]

ERC20 = None
if W3_CONNECTED:
    try:
        ERC20 = w3.eth.contract(address=Web3.to_checksum_address(SELA_TOKEN_ADDRESS), abi=ERC20_ABI)
    except Exception as e:
        logger.exception("ERC20 init failed: %s", e)

# =========================
# Utilities
# =========================
def is_admin(update: Update) -> bool:
    try:
        return ADMIN_ID is not None and update.effective_user and update.effective_user.id == ADMIN_ID
    except Exception:
        return False

def token_decimals() -> int:
    try:
        return ERC20.functions.decimals().call()
    except Exception:
        return 18

def token_symbol() -> str:
    try:
        return ERC20.functions.symbol().call()
    except Exception:
        return "SLH"

def nis_to_tokens(amount_nis: Decimal) -> Decimal:
    return (amount_nis / SELA_NIS_VALUE).quantize(Decimal("0.00000001"))

def to_raw_tokens(amount_tokens: Decimal, decimals: int) -> int:
    multiplier = Decimal(10) ** decimals
    return int((amount_tokens * multiplier).to_integral_value())

# resilient send helpers with retry
async def safe_send_message(chat_id: int, text: str, **kwargs):
    for attempt in range(3):
        try:
            await asyncio.to_thread(bot.send_message, chat_id, text, **kwargs)
            return
        except TelegramError as e:
            logger.warning("send_message attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(0.5)
    logger.error("Failed to send_message to %s after retries", chat_id)
    if ADMIN_ID:
        await asyncio.to_thread(bot.send_message, ADMIN_ID, f"Failed to send message to {chat_id}: {text}")

async def safe_send_photo(chat_id: int, fileobj, **kwargs):
    for attempt in range(3):
        try:
            await asyncio.to_thread(bot.send_photo, chat_id, fileobj, **kwargs)
            return
        except TelegramError as e:
            logger.warning("send_photo attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(0.5)
    logger.error("Failed to send_photo to %s after retries", chat_id)

async def safe_send_document(chat_id: int, fileobj, **kwargs):
    for attempt in range(3):
        try:
            await asyncio.to_thread(bot.send_document, chat_id, fileobj, **kwargs)
            return
        except TelegramError as e:
            logger.warning("send_document attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(0.5)
    logger.error("Failed to send_document to %s after retries", chat_id)

# =========================
# DB (aiosqlite)
# =========================
async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id         INTEGER PRIMARY KEY,
            name       TEXT,
            wallet_bsc TEXT
        );
        CREATE TABLE IF NOT EXISTS payments(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            amount_fiat   REAL,
            proof_file_id TEXT,
            status        TEXT,
            created_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS demo_state(
            chat_id INTEGER PRIMARY KEY,
            idx INTEGER
        );
        """)
        await db.commit()

async def db_set_wallet(user_id: int, wallet: str):
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        await db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (user_id,))
        await db.execute("UPDATE users SET wallet_bsc=? WHERE id=?", (wallet, user_id))
        await db.commit()

async def db_get_demo_idx(chat_id: int) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        cur = await db.execute("SELECT idx FROM demo_state WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def db_set_demo_idx(chat_id: int, idx: int):
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        await db.execute("INSERT OR REPLACE INTO demo_state(chat_id, idx) VALUES(?,?)", (chat_id, idx))
        await db.commit()

async def db_delete_demo(chat_id: int):
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        await db.execute("DELETE FROM demo_state WHERE chat_id=?", (chat_id,))
        await db.commit()

# =========================
# Images gallery
# =========================
def load_images():
    exts = ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp")
    files = []
    if IMAGES_DIR.exists() and IMAGES_DIR.is_dir():
        for ext in exts:
            files.extend(sorted(IMAGES_DIR.glob(ext)))
    return files

IMAGES = load_images()
gallery_state = {}

def has_images() -> bool:
    return len(IMAGES) > 0

# =========================
# UI texts & keyboards
# =========================
WELCOME_TITLE = "🎉 ברוכים הבאים ל-NIFTII!! משחק ה-NFT שמשגע את המדינה! 🔥"
WELCOME_BODY = (
    "💎 היום זה כבר לא חלום — לכל אחד יכולה להיות חנות קלפים דיגיטלית!\n"
    "לחצו על כפתור מידע לקבלת פרטים."
)

INFO_PAGES = [
    "3. הבוט יסייע להרחיב מכירות, להעצים שפע כלכלי, ולבנות קהילה סביבכם!",
    "3.1 🖼️ לכל אחד נכס דיגיטלי רווחי — חנות למכירת קלפי NFT.",
    "3.2 חנות קלפים: רכשו קלף + חנות משלכם, שווקו למכירה חוזרת והרוויחו מכל מכירה.",
    "3.4 משתפים את הקלף, מרוויחים לבנק שלכם, ואנחנו מרוויחים מרישום בוטים חדשים.",
    "3.5 הצטרפות לקהילה עסקית מובילה, הטבות ותמלוגים מכל קלף.",
]

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ מידע", callback_data="info_0")],
        [InlineKeyboardButton("🧪 דמו", callback_data="demo_start")],
        [InlineKeyboardButton("🛒 רכישה", callback_data="buy_intro")],
        [InlineKeyboardButton("✉️ צור קשר", url="https://t.me/OsifFin")],
    ])

def demo_nav_kb(idx: int):
    buttons = [
        InlineKeyboardButton("⬅️ הקודם", callback_data=f"demo_prev:{idx}"),
        InlineKeyboardButton("➡️ הבא", callback_data=f"demo_next:{idx}"),
    ]
    row2 = [InlineKeyboardButton("🛒 בחירת הקלף", callback_data=f"demo_pick:{idx}")]
    return InlineKeyboardMarkup([buttons, row2])

def info_nav_kb(idx: int):
    prev_idx = max(0, idx - 1)
    next_idx = min(len(INFO_PAGES) - 1, idx + 1)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️", callback_data=f"info_{prev_idx}"),
            InlineKeyboardButton("➡️", callback_data=f"info_{next_idx}")
        ],
        [InlineKeyboardButton("🏠 תפריט", callback_data="home")]
    ])

# =========================
# Commands registry
# =========================
handlers = {}

def command(name: str):
    def decorator(fn):
        handlers[name.lower()] = fn
        return fn
    return decorator

# =========================
# Commands
# =========================
@command('/start')
async def start_cmd(update: Update):
    chat_id = update.effective_chat.id
    if has_images():
        img_path = random.choice(IMAGES)
        with img_path.open("rb") as f:
            await safe_send_photo(chat_id, f, caption=f"{WELCOME_TITLE}\n\n{WELCOME_BODY}", reply_markup=main_menu(), parse_mode="Markdown")
    else:
        await safe_send_message(chat_id, f"{WELCOME_TITLE}\n\n{WELCOME_BODY}", reply_markup=main_menu(), parse_mode="Markdown")

@command('/help')
async def help_cmd(update: Update):
    chat_id = update.effective_chat.id
    text = (
        "/start – התחלה\n"
        "/help – עזרה\n"
        "/echoid – קבלת Chat ID\n"
        "/set_wallet 0x... – שמירת ארנק BSC\n"
    )
    await safe_send_message(chat_id, text)

@command('/echoid')
async def echoid_cmd(update: Update):
    chat = update.effective_chat
    text = f"chat.type={chat.type}\nchat.id={chat.id}"
    await safe_send_message(chat.id, text)

@command('/set_wallet')
async def set_wallet_cmd(update: Update):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id if update.effective_user else None
    parts = (update.message.text or "").split(maxsplit=1)
    if not uid:
        await safe_send_message(chat_id, "לא זוהה משתמש.")
        return
    if len(parts) < 2 or not parts[1].startswith("0x") or len(parts[1]) != 42:
        await safe_send_message(chat_id, "שימוש: /set_wallet 0xכתובתBSC חוקית")
        return
    addr = parts[1]
    await db_set_wallet(uid, addr)
    await safe_send_message(chat_id, f"✅ עודכן ארנק BSC: {addr}")

# =========================
# Callback handling
# =========================
async def on_callback(cq, update: Update):
    try:
        await asyncio.to_thread(bot.answer_callback_query, cq['id'])
    except BadRequest as e:
        logger.debug("answer_callback_query: %s", e)

    chat_id = update.effective_chat.id
    data = cq.get('data') or ""

    if data == "home":
        if has_images():
            img_path = random.choice(IMAGES)
            with img_path.open("rb") as f:
                await safe_send_photo(chat_id, f, caption=f"{WELCOME_TITLE}\n\n{WELCOME_BODY}", reply_markup=main_menu(), parse_mode="Markdown")
        else:
            await safe_send_message(chat_id, f"{WELCOME_TITLE}\n\n{WELCOME_BODY}", reply_markup=main_menu(), parse_mode="Markdown")
        return

    if data.startswith("info_"):
        try:
            idx = int(data.split("_", 1)[1])
        except Exception:
            idx = 0
        idx = max(0, min(idx, len(INFO_PAGES) - 1))
        await safe_send_message(chat_id, INFO_PAGES[idx], reply_markup=info_nav_kb(idx))
        return

    if data == "demo_start":
        if not has_images():
            await safe_send_message(chat_id, "אין כרגע תמונות בגלריה.")
            return
        gallery_state[chat_id] = 0
        idx = 0
        img_path = IMAGES[idx]
        with img_path.open("rb") as f:
            await safe_send_photo(chat_id, f,
                caption=("💥 קלף זה יכול להיות שלכם למכירה חוזרת כבר היום!\n"
                         "🏷️ מבצע היום — 39 ₪ בלבד\n"
                         "🖼️ בחרו תמונה בחיצים ולחצו „🛒 בחירת הקלף”"),
                reply_markup=demo_nav_kb(idx), parse_mode="Markdown"
            )
        await db_set_demo_idx(chat_id, idx)
        return

    if data.startswith("demo_prev:") or data.startswith("demo_next:"):
        if not has_images():
            await safe_send_message(chat_id, "אין גלריה.")
            return
        try:
            cur = int(data.split(":", 1)[1])
        except Exception:
            cur = gallery_state.get(chat_id, 0)
        if data.startswith("demo_prev:"):
            cur = (cur - 1) % len(IMAGES)
        else:
            cur = (cur + 1) % len(IMAGES)
        gallery_state[chat_id] = cur
        img_path = IMAGES[cur]
        with img_path.open("rb") as f:
            await safe_send_photo(chat_id, f,
                caption=("💥 קלף זה יכול להיות שלכם למכירה חוזרת כבר היום!\n"
                         "🏷️ מבצע היום — 39 ₪ בלבד\n"
                         "🖼️ בחרו תמונה בחיצים ולחצו „🛒 בחירת הקלף”"),
                reply_markup=demo_nav_kb(cur), parse_mode="Markdown"
            )
        await db_set_demo_idx(chat_id, cur)
        return

    if data.startswith("demo_pick:"):
        idx = await db_get_demo_idx(chat_id) or gallery_state.get(chat_id, 0)
        await safe_send_message(chat_id,
            "5) איזה מחיר תרצו לגבות על קלף זה מחבריכם?\n"
            "6) אנא הזינו מחיר (בש״ח), לדוגמה: 120"
        )
        await db_set_demo_idx(chat_id, idx)
        return

    if data == "buy_intro":
        await safe_send_message(chat_id,
            "לרכישה דרך העברה בנקאית/טלגרם ארנק/פייפאל/ביט/פייבוקס:\nבחרו אפשרות:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧧 /טלגרם", callback_data="pay_wallet")],
                [InlineKeyboardButton("💳 פייפאל", url="https://paypal.me/osifdu")],
                [InlineKeyboardButton("📱 ביט/פייבוקס", callback_data="pay_bit")],
                [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="pay_bank")],
                [InlineKeyboardButton("✉️ צור קשר", url="https://t.me/OsifFin")],
            ]))
        return

    if data == "pay_wallet":
        await safe_send_message(chat_id, "הידעתם שיש ארנק בטלגרם? לחצו @wallet ויש לכם ארנק קריפטו מאובטח!")
        await asyncio.sleep(0.25)
        await safe_send_message(chat_id, "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp")
        return

    if data == "pay_bit":
        await safe_send_message(chat_id, "ביט/פייבוקס להעברה: 0546671882")
        return

    if data == "pay_bank":
        await safe_send_message(chat_id,
            "פרטי העברה בנקאית:\n"
            "המוטב: קאופמן צביקה\n"
            "בנק הפועלים | סניף כפר גנים (153) | חשבון 73462"
        )
        return

# =========================
# Message processing
# =========================
async def on_message(update: Update):
    chat_id = update.effective_chat.id
    msg = update.message
    text = (msg.text or "").strip()

    # forward payment proofs to payments chat
    if PAYMENTS_CHAT_ID:
        user = msg.from_user
        who = f"{user.first_name or ''} {user.last_name or ''} | @{user.username or ''} | id={user.id}"
        if msg.photo:
            file_id = msg.photo[-1].file_id
            cap = (msg.caption or "").strip()
            caption = f"🧾 אישור תשלום מהמשתמש:\n{who}\n\n{cap}" if cap else f"🧾 אישור תשלום מהמשתמש:\n{who}"
            await safe_send_photo(PAYMENTS_CHAT_ID, file_id, caption=caption)
        elif msg.document:
            file_id = msg.document.file_id
            cap = (msg.caption or "").strip()
            caption = f"🧾 אישור תשלום (מסמך) מהמשתמש:\n{who}\n\n{cap}" if cap else f"🧾 אישור תשלום (מסמך) מהמשתמש:\n{who}"
            await safe_send_document(PAYMENTS_CHAT_ID, file_id, caption=caption)

    # demo price capture
    demo_idx = await db_get_demo_idx(chat_id)
    if demo_idx is not None and text.replace(".", "", 1).isdigit():
        try:
            price_nis = float(text)
            await db_delete_demo(chat_id)
            pct = min(95, max(5, int((price_nis / 39.0) * 10)))
            await safe_send_message(chat_id, f"👏 לפי המחיר שביקשתם ({price_nis:.0f}₪) אתם תרוויחו ~{pct}% מכל מכירה חוזרת!!")
            await safe_send_message(chat_id,
                "לאחר רכישת הקלף ב־39 ש\"ח בלבד, שלחו כאן אישור תשלום (תמונה/מסמך) או בחרו אמצעי תשלום מתפריט '🛒 רכישה'.")
            return
        except Exception as e:
            logger.exception("demo parse error: %s", e)

    # dispatch commands
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        fn = handlers.get(cmd)
        if fn:
            try:
                await fn(update)
            except Exception as e:
                logger.exception("Command %s failed: %s", cmd, e)
                await safe_send_message(chat_id, "אירעה שגיאה בעיבוד הפקודה.")
                if ADMIN_ID:
                    await safe_send_message(ADMIN_ID, f"Error in command {cmd}: {e}")
        else:
            await safe_send_message(chat_id, "פקודה לא מוכרת. /help לקבלת עזרה.")
    else:
        # default echo
        await safe_send_message(chat_id, f"Echo: {text}")

# =========================
# Webhook handlers
# =========================
@routes.get("/")
async def health(request):
    return web.Response(text="OK")

@routes.post(WEBHOOK_ROUTE)
async def handle(request):
    try:
        data = await request.json()
    except Exception:
        return web.Response(text="OK")
    if 'callback_query' in data:
        cq = data['callback_query']
        update = Update.de_json(data, bot)
        try:
            await on_callback(cq, update)
        except Exception as e:
            logger.exception("on_callback failed: %s", e)
        return web.Response(text="OK")
    if 'message' in data:
        update = Update.de_json(data, bot)
        try:
            await on_message(update)
        except Exception as e:
            logger.exception("on_message failed: %s", e)
        return web.Response(text="OK")
    return web.Response(text="OK")

app.add_routes(routes)

# =========================
# Optional: on-start tasks
# =========================
async def on_startup(app):
    await init_db()
    logger.info("DB initialized at %s", DB_PATH)
    if not has_images():
        logger.info("No images found in %s", IMAGES_DIR)
    else:
        logger.info("Loaded %d images", len(IMAGES))

app.on_startup.append(on_startup)

# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    logger.info("Starting NIFTII on port %s (route=%s)", PORT, WEBHOOK_ROUTE)
    web.run_app(app, port=PORT)
