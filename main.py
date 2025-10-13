import os
import asyncio
import random
import glob
import sqlite3
from datetime import datetime

from aiohttp import web
from dotenv import load_dotenv

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.utils.request import Request
from telegram.error import BadRequest

# =========================
# קונפיגורציה ו־ENV
# =========================
load_dotenv()

BOT_TOKEN          = os.getenv("BOT_TOKEN")
PUBLIC_URL         = os.getenv("PUBLIC_URL", "")  # לשימוש חיצוני אם תרצה
WEBHOOK_ROUTE      = os.getenv("WEBHOOK_ROUTE", "/webhook")
PAYMENTS_CHAT_ID   = int(os.getenv("PAYMENTS_CHAT_ID", "0") or 0)   # קבוצה/ערוץ דיווח אישורי תשלום
ADMIN_ID           = int(os.getenv("ADMIN_ID", "0") or 0) or None   # אדמין ראשי (אופציונלי)

# BSC / SLH (סלה ללא גבולות)
BSC_RPC_URL        = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org/")
BSC_CHAIN_ID       = int(os.getenv("BSC_CHAIN_ID", "56"))
SELA_TOKEN_ADDRESS = os.getenv("SELA_TOKEN_ADDRESS", "0xACb0A09414CEA1C879c67bB7A877E4e19480f022")
TREASURY_ADDRESS   = os.getenv("TREASURY_ADDRESS")         # 0x...
TREASURY_PRIVATE_KEY = os.getenv("TREASURY_PRIVATE_KEY")   # hex (עם/בלי 0x)
SELA_NIS_VALUE     = float(os.getenv("SELA_NIS_VALUE", "240"))  # 1 SLH = 240 ₪

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN in environment")

# =========================
# Bot & DB
# =========================
bot    = Bot(token=BOT_TOKEN, request=Request(con_pool_size=8))
app    = web.Application()
routes = web.RouteTableDef()

conn = sqlite3.connect('bot.db', check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS users(
    id         INTEGER PRIMARY KEY,
    name       TEXT,
    wallet_bsc TEXT
)
""")
conn.execute("""
CREATE TABLE IF NOT EXISTS payments(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    amount_fiat   REAL,
    proof_file_id TEXT,
    status        TEXT,        -- pending/approved/rejected
    created_at    TEXT
)
""")
conn.commit()

# מצב שיחות
handlers = {}
def command(name):
    def decorator(fn):
        handlers[name.lower()] = fn
        return fn
    return decorator

# זיכרון ריצה: גלריה לכל צ'אט
gallery_state = {}  # chat_id -> index
IMAGES = []
for ext in ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp"):
    IMAGES.extend(glob.glob(os.path.join("images", ext)))
IMAGES = sorted(IMAGES)

def has_images():
    return len(IMAGES) > 0

async def tg_send(chat_id, text, **kwargs):
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, text, **kwargs))

async def tg_send_photo(chat_id, file, **kwargs):
    asyncio.create_task(asyncio.to_thread(bot.send_photo, chat_id, file, **kwargs))

async def tg_send_document(chat_id, file_id, **kwargs):
    asyncio.create_task(asyncio.to_thread(bot.send_document, chat_id, file_id, **kwargs))

def is_admin(update: Update) -> bool:
    try:
        uid = update.effective_user.id
    except:
        return False
    return ADMIN_ID and uid == ADMIN_ID

# =========================
# WEB3 INJECT (SLH)
# =========================
from decimal import Decimal
from web3 import Web3

w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
try:
    w3_connected = w3.is_connected()
except Exception:
    w3_connected = False
if not w3_connected:
    print("[web3] Warning: Not connected to RPC", BSC_RPC_URL)

ERC20_ABI = [
  {"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
  {"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
  {"constant":True,"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},
  {"constant":False,"inputs":[{"name":"recipient","type":"address"},{"name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"},
]

ERC20 = None
try:
    ERC20 = w3.eth.contract(address=Web3.to_checksum_address(SELA_TOKEN_ADDRESS), abi=ERC20_ABI)
except Exception as e:
    print("[web3] Contract init failed:", e)

def token_decimals():
    try: return ERC20.functions.decimals().call()
    except: return 15  # לפי BscScan לטוקן שלך

def token_symbol():
    try: return ERC20.functions.symbol().call()
    except: return "SLH"

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
# UI – טקסטים וכפתורים
# =========================
WELCOME_TITLE = "🎉 ברוכים הבאים ל-NIFTII!! משחק ה-NFT שמשגע את המדינה! 🔥"
WELCOME_BODY = (
    "💎 *היום זה כבר לא חלום* — לכל אחד ואחת יכול להיות קניון!! 🛍️\n"
    "רוצים לדעת איך אתם יכולים להיות מיליונרים ובקרוב? 👉\n"
    "לחצו על כפתור \"מידע\" לקבלת כל הידע לאיך להרוויח דרך חנות קלפים משלכם בטלגרם."
)

INFO_PAGES = [
    "3. הבוט יסייע להרחיב מכירות, להעצים שפע כלכלי, ולבנות קהילה סביבכם!",
    "3.1 🖼️ לכל אחד נכס דיגיטלי רווחי — חנות למכירת קלפי NFT. רווח יומי ממכירה חוזרת 💸",
    "3.2 חנות קלפים: רכשו קלף + חנות משלכם, שווקו למכירה חוזרת והרוויחו מכל מכירה.",
    "3.4 הרעיון פשוט: משתפים את הקלף, מרוויחים לבנק שלכם, ואנחנו מרוויחים מרישום בוטים חדשים.\n*WIN WIN WIN WIN*",
    "3.5 בהצטרפות ל-NIFTII תיכנסו לקהילה עסקית מובילה, הטבות, והשפעה כלכלית-חברתית בכל קלף שתמכרו!",
    "3.6 ככל שתמכרו יותר, הדירוג וההכנסות שלכם יעלו—גם ישיר וגם אחרי הנפקת המשחק בבורסות.",
    "3.7 המשחק מבוסס NFT (קריפטו). ערך התמונות = כסף אמיתי לבעלי עסקים בישראל.",
    "✅מערכת שיווק רשתי\n✅הכנסה קבועה\n✅ללא מאמץ\n✅ללא התחייבות\n✅הפתעות ותמלוגים",
    "דמו חינמי: בחרו תמונה בגלריה וחוו תהליך רכישה—רק 39 ₪ לקלף דמו",
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
# פקודות
# =========================
@command('/start')
def start_cmd(update: Update):
    chat_id = update.effective_chat.id
    # תמונה רנדומלית
    if has_images():
        img = random.choice(IMAGES)
        asyncio.create_task(asyncio.to_thread(
            bot.send_photo, chat_id, open(img, "rb"),
            caption=f"{WELCOME_TITLE}\n\n{WELCOME_BODY}",
            reply_markup=main_menu(), parse_mode="Markdown"
        ))
    else:
        asyncio.create_task(asyncio.to_thread(
            bot.send_message, chat_id, f"{WELCOME_TITLE}\n\n{WELCOME_BODY}",
            reply_markup=main_menu(), parse_mode="Markdown"
        ))

@command('/help')
def help_cmd(update: Update):
    chat_id = update.effective_chat.id
    text = (
        "/start – התחלה\n"
        "/help – עזרה\n"
        "/echoid – קבלת Chat ID\n"
        "/set_wallet 0x... – שמירת ארנק BSC לקבלת תגמולים\n"
    )
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, text))

@command('/echoid')
def echoid_cmd(update: Update):
    chat = update.effective_chat
    text = f"chat.type={chat.type}\nchat.id={chat.id}"
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat.id, text))

@command('/set_wallet')
def set_wallet_cmd(update: Update):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id if update.effective_user else None
    parts = (update.message.text or "").split(maxsplit=1)
    if not uid:
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, "לא זוהה משתמש."))
        return
    if len(parts) < 2 or not parts[1].startswith("0x") or len(parts[1]) != 42:
        asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, "שימוש: /set_wallet 0xכתובתBSC חוקית"))
        return
    addr = parts[1]
    # הוסף עמודה אם חסרה
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if 'wallet_bsc' not in cols:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN wallet_bsc TEXT")
        except Exception:
            pass
    conn.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
    conn.execute("UPDATE users SET wallet_bsc=? WHERE id=?", (addr, uid))
    conn.commit()
    asyncio.create_task(asyncio.to_thread(bot.send_message, chat_id, f"✅ עודכן ארנק BSC: {addr}"))

# =========================
# Callback Handlers
# =========================
async def on_callback(cq, update: Update):
    # מענה מיידי כדי למנוע "Query is too old..."
    try:
        await asyncio.to_thread(bot.answer_callback_query, cq['id'])
    except BadRequest as e:
        print("answer_callback_query:", e)

    chat_id = update.effective_chat.id
    data    = cq.get('data') or ""

    if data == "home":
        if has_images():
            img = random.choice(IMAGES)
            await tg_send_photo(chat_id, open(img, "rb"),
                caption=f"{WELCOME_TITLE}\n\n{WELCOME_BODY}",
                reply_markup=main_menu(), parse_mode="Markdown")
        else:
            await tg_send(chat_id, f"{WELCOME_TITLE}\n\n{WELCOME_BODY}", reply_markup=main_menu(), parse_mode="Markdown")
        return

    # מידע מדפדף
    if data.startswith("info_"):
        try:
            idx = int(data.split("_")[1])
        except:
            idx = 0
        idx = max(0, min(idx, len(INFO_PAGES)-1))
        await tg_send(chat_id, INFO_PAGES[idx], reply_markup=info_nav_kb(idx))
        return

    # דמו – גלריה
    if data == "demo_start":
        gallery_state[chat_id] = 0
        if not has_images():
            await tg_send(chat_id, "אין כרגע תמונות בגלריה.")
            return
        idx = gallery_state[chat_id]
        await tg_send_photo(
            chat_id, open(IMAGES[idx], "rb"),
            caption=("💥 קלף זה יכול להיות שלכם *למכירה חוזרת כבר היום!*\n"
                     "🏷️ *מבצע היום —* 39 ₪ בלבד\n"
                     "🖼️ בחרו תמונה בחיצים ולחצו „🛒 בחירת הקלף”"),
            reply_markup=demo_nav_kb(idx), parse_mode="Markdown"
        )
        return

    if data.startswith("demo_prev:") or data.startswith("demo_next:"):
        if not has_images():
            await tg_send(chat_id, "אין גלריה.")
            return
        try:
            cur = int(data.split(":")[1])
        except:
            cur = gallery_state.get(chat_id, 0)
        if data.startswith("demo_prev:"):
            cur = (cur - 1) % len(IMAGES)
        else:
            cur = (cur + 1) % len(IMAGES)
        gallery_state[chat_id] = cur
        await tg_send_photo(
            chat_id, open(IMAGES[cur], "rb"),
            caption=("💥 קלף זה יכול להיות שלכם *למכירה חוזרת כבר היום!*\n"
                     "🏷️ *מבצע היום —* 39 ₪ בלבד\n"
                     "🖼️ בחרו תמונה בחיצים ולחצו „🛒 בחירת הקלף”"),
            reply_markup=demo_nav_kb(cur), parse_mode="Markdown"
        )
        return

    if data.startswith("demo_pick:"):
        idx = gallery_state.get(chat_id, 0)
        await tg_send(chat_id,
            "5) איזה מחיר תרצו לגבות על קלף זה מחבריכם?\n"
            "6) אנא הזינו מחיר (בש״ח), לדוגמה: 120",
        )
        # סימון סטייט לקליטת מחיר
        conn.execute("CREATE TABLE IF NOT EXISTS demo_state(chat_id INTEGER PRIMARY KEY, idx INTEGER)")
        conn.execute("INSERT OR REPLACE INTO demo_state(chat_id, idx) VALUES(?,?)", (chat_id, idx))
        conn.commit()
        return

    if data == "buy_intro":
        await tg_send(chat_id,
            "לרכישה דרך העברה בנקאית/טלגרם ארנק/פייפאל/ביט/פייבוקס:\n"
            "הנתונים המוצגים כאן יכולים להיות שלכם!\n\n"
            "בחרו אפשרות:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧧 /טלגרם", callback_data="pay_wallet")],
                [InlineKeyboardButton("💳 פייפאל", url="https://paypal.me/osifdu")],
                [InlineKeyboardButton("📱 ביט/פייבוקס", callback_data="pay_bit")],
                [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="pay_bank")],
                [InlineKeyboardButton("✉️ צור קשר", url="https://t.me/OsifFin")],
            ]))
        return

    if data == "pay_wallet":
        # שלוש הודעות ברצף איטי (0.3s)
        await tg_send(chat_id, "הידעתם שיש ארנק בטלגרם? לחצו @wallet ויש לכם ארנק קריפטו מאובטח!")
        await asyncio.sleep(0.3)
        await tg_send(chat_id, "הארנק כאן אינו מחוייב במס ומוגדר כהשקעה! להעברת טלגרם לחשבון המפתח:")
        await asyncio.sleep(0.3)
        await tg_send(chat_id, "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp")
        return

    if data == "pay_bit":
        await tg_send(chat_id, "ביט/פייבוקס להעברה: 0546671882")
        return

    if data == "pay_bank":
        await tg_send(chat_id,
            "פרטי העברה בנקאית:\n"
            "המוטב: קאופמן צביקה\n"
            "בנק הפועלים | סניף כפר גנים (153) | חשבון 73462"
        )
        return

# =========================
# עיבוד הודעות רגילות
# =========================
async def on_message(update: Update):
    chat_id = update.effective_chat.id
    msg     = update.message
    text    = (msg.text or "").strip()

    # --- העברת אישורי תשלום לקבוצת התשלומים ---
    if PAYMENTS_CHAT_ID:
        user = msg.from_user
        who  = f"{user.first_name or ''} {user.last_name or ''} | @{user.username or ''} | id={user.id}"
        if msg.photo:
            file_id = msg.photo[-1].file_id
            cap = (msg.caption or "").strip()
            caption = f"🧾 אישור תשלום מהמשתמש:\n{who}\n\n{cap}" if cap else f"🧾 אישור תשלום מהמשתמש:\n{who}"
            await tg_send_photo(PAYMENTS_CHAT_ID, file_id, caption=caption)
        elif msg.document:
            file_id = msg.document.file_id
            cap = (msg.caption or "").strip()
            caption = f"🧾 אישור תשלום (מסמך) מהמשתמש:\n{who}\n\n{cap}" if cap else f"🧾 אישור תשלום (מסמך) מהמשתמש:\n{who}"
            await tg_send_document(PAYMENTS_CHAT_ID, file_id, caption=caption)

    # --- קליטת מחיר בדמו ---
    row = conn.execute("SELECT idx FROM demo_state WHERE chat_id=?", (chat_id,)).fetchone()
    if row and text.replace(".", "", 1).isdigit():
        price_nis = float(text)
        conn.execute("DELETE FROM demo_state WHERE chat_id=?", (chat_id,))
        conn.commit()
        # חישוב % תשואה דמיוני (דוגמה UX)
        pct = min(95, max(5, int((price_nis / 39.0) * 10)))
        await tg_send(chat_id,
            f"👏 לפי המחיר שביקשתם ({price_nis:.0f}₪) אתם תרוויחו ~{pct}% מכל מכירה חוזרת!!")
        await tg_send(chat_id,
            "לאחר רכישת הקלף ב־39 ש\"ח בלבד, תוכל לעשות ארגזים!!\n"
            "שלחו כאן אישור תשלום (תמונה/מסמך) או בחרו אמצעי תשלום מתפריט '🛒 רכישה'.")
        return

    # --- דיספאץ' פקודות ---
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        fn  = handlers.get(cmd)
        if fn:
            fn(update)
        else:
            await tg_send(chat_id, "פקודה לא מוכרת. /help לקבלת עזרה.")
    else:
        # ברירת מחדל: Echo קליל
        await tg_send(chat_id, f"Echo: {text}")

# =========================
# Webhook Handlers
# =========================
@routes.get("/")
async def health(_):
    return web.Response(text="OK")

@routes.post(WEBHOOK_ROUTE)
async def handle(request):
    data = await request.json()

    # Callback query
    if 'callback_query' in data:
        cq     = data['callback_query']
        update = Update.de_json(data, bot)
        await on_callback(cq, update)
        return web.Response(text="OK")

    # Messages
    if 'message' not in data:
        return web.Response(text="OK")

    update = Update.de_json(data, bot)
    await on_message(update)
    return web.Response(text="OK")

app.add_routes(routes)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    print(f"Starting NIFTII – משחק החנויות 🔥 on port {port} (route={WEBHOOK_ROUTE})")
    web.run_app(app, port=port)
