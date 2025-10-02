# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import random
import logging
from pathlib import Path

# ---------------- .env & paths bootstrap ----------------
try:
    from dotenv import load_dotenv
    # קורא .env מהתיקייה של הקובץ
    load_dotenv(dotenv_path=Path(__file__).parent / ".env")
except Exception:
    pass

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()

# נבנה רשימת מקורות תמונות: PIC_DIR, IMAGE_LIBRARY_PATH וגם ./images כגיבוי
_IMG_ROOTS = []
for key in ("PIC_DIR", "IMAGE_LIBRARY_PATH"):
    val = os.getenv(key)
    if val:
        _IMG_ROOTS.append(val)
_IMG_ROOTS.append("./images")

def _collect_image_files(paths):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    files = []
    for p in paths:
        pth = Path(p)
        if pth.exists():
            files.extend(str(f) for f in pth.rglob("*") if f.suffix.lower() in exts)
    # יוניק + שומר סדר
    seen, uniq = set(), []
    for f in files:
        if f not in seen:
            uniq.append(f)
            seen.add(f)
    return uniq

IMG_FILES = _collect_image_files(_IMG_ROOTS)
IMG_COUNT = len(IMG_FILES)

PAYMENT_GROUP_ID = int(os.getenv("PAYMENT_GROUP_ID", "-1001699922921"))
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "224223270"))
SITE_URL = os.getenv("SITE_URL", "https://osifeu-prog.github.io/OsifsCardShop").strip()

# לוג בסיסי
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("niftii-bot")
log.info("✅ מקורות תמונות: %s", " | ".join(_IMG_ROOTS))
log.info("✅ נטענו %d תמונות", IMG_COUNT)

# Windows asyncio fix
if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# --------------------------------------------------------

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputMediaPhoto,
    constants,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# בדיקת הטוקן
if not TOKEN:
    print("❌ שגיאה: TELEGRAM_TOKEN לא נמצא או ריק! ודא שהוא ב-.env")
    sys.exit(1)

print(f"✅ טוקן נטען: {TOKEN[:8]}...")
print(f"📁 סה\"כ תמונות: {IMG_COUNT}")

# כיתובים לגלריה
GALLERY_CAPS = [
    "3. בוט זה יסייע לכם להרחיב את מכירותיכם, להגדיר את השפע הכלכלי שלכם, ולקיים קשר עם הקהילה שתיווצר סביבכם!",
    "3.1 🖼️ היום לכל אחד ואחת יכול להיות נכס דיגיטלי רווחי\n— חנות למכירת קלפי NFT מניבה וכלכלית שלכם!\nתוכלו למכור, לשווק ולהרוויח *בכל יום ויום* ממכירה חוזרת של התמונה שרכשתם – ישירות לחשבון הבנק שלכם!💸",
    "3.2 בבוט זה בנוי כחנות קלפים בו תוכלו לרכוש קלף + חנות משלכם לשווק למכירה חוזרת, ולהרוויח מכל מכירה של הקלף שלכם.",
    "3.4 הרעיון פשוט: אתם משתפים את הקלף שלכם, מרוויחים ישירות לבנק שלכם, ואנחנו מרוויחים מרישום הבוטים של מצטרפים חדשים לקהילת האספנים של ישראל!\n**WIN WIN WIN WIN**",
    "3.5 בהצטרפות ל\"NIFTII משחק החנויות שמשגע את המדינה\" תזכו להצטרף לקהילת העסקים המובילה בישראל, לזכות בשלל הטבות, ולהוביל לשינוי כלכלי וחברתי דרך כל קלף שתפרסמו ותמכרו!!",
    "3.6 ככל שתמכרו יותר – דירוגכם יעלה ותוכלו להרוויח יותר, הן ברווח ישיר, והן לאחר הנפקת המשחק בבורסות השונות.",
    "3.7 כן כן, קראתם נכון! משחק זה מבוסס NFT – סוג של קריפטו ייחודי לשיווק תמונות.\nמאחר שאפליקציה זו נבנתה במיוחד עבור בעלי עסקים בישראל, הערך הכלכלי של התמונות הללו שווה לכם כסף!",
]

# מצבי שיחה
PRICE, FIRST_NAME, LAST_NAME, PHONE, PAYMENT_CONFIRMATION = range(5)

# מקלדות
REPLY_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("☎️ צור קשר 📞"), KeyboardButton("✍🏻 רכישת חנות 🎯")],
        [KeyboardButton("🔄 תפריט ראשי 📚"), KeyboardButton("🌐 אתר")],
    ],
    resize_keyboard=True,
)

PAYMENT_KB = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("💳 טלגרם", callback_data="payment_tg")],
        [InlineKeyboardButton("💸 פייפאל", callback_data="payment_paypal")],
        [InlineKeyboardButton("📱 ביט/פייבוקס", callback_data="payment_bit")],
        [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="payment_bank")],
        [InlineKeyboardButton("🛒 השלם רכישה", callback_data="final_purchase")],
    ]
)

BANK_TRANSFER_KB = InlineKeyboardMarkup(
    [[InlineKeyboardButton("📸 העלה אישור העברה", callback_data="upload_receipt")]]
)

# ================= פונקציות =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    context.user_data.clear()

    # תמונה רנדומלית
    if IMG_COUNT:
        img_path = random.choice(IMG_FILES)
        try:
            await context.bot.send_photo(
                chat_id, photo=img_path,
                caption="🎉 ברוכים הבאים ל-NIFTII!! משחק ה-NFT שמשגע את המדינה! 🔥"
            )
        except Exception as e:
            log.error(f"שגיאה בשליחת תמונה: {e}")

    # הודעות פתיחה
    await context.bot.send_message(
        chat_id,
        text="💎 *היום זה כבר לא חלום* — לכל אחד ואחת יכול להיות קניון!! 🛍️",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    info_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📖 מידע", callback_data="open_shop")]])
    await context.bot.send_message(
        chat_id,
        text='רוצים לדעת איך אתם יכולים להיות מיליונרים ובקרוב? 👉\nלחצו על כפתור "מידע" לקבלת כל הידע לאיזה חנות קלפים משלכם בטלגרם.',
        reply_markup=info_kb,
    )

    await context.bot.send_message(chat_id, text="בחרו אפשרות נוספת מהתפריט למטה:", reply_markup=REPLY_KB)

async def open_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat.id
    else:
        chat_id = update.effective_chat.id

    benefits_text = (
        "✅ מערכת שלמה לשיווק רשתי\n"
        "✅ הכנסה קבועה ומשתלמת\n"
        "✅ ללא מאמץ\n"
        "✅ ללא התחייבות\n"
        "✅ הפתעות ותמלוגים"
    )
    await context.bot.send_message(chat_id, benefits_text, reply_markup=REPLY_KB)

    # גלריה: שולחים עד min(מס' תמונות, מס' כיתובים)
    if IMG_COUNT > 0:
        media_group = []
        limit = min(len(GALLERY_CAPS), IMG_COUNT, 10)  # מגביל לקבוצה סבירה
        for idx in range(limit):
            media_group.append(
                InputMediaPhoto(media=IMG_FILES[idx], caption=GALLERY_CAPS[idx], parse_mode=constants.ParseMode.MARKDOWN)
            )
        try:
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)
        except Exception as e:
            log.error(f"שגיאה בשליחת גלריה: {e}")
            # נפילה חכמה: שולח 3 בנפרד
            for idx in range(min(3, limit)):
                try:
                    await context.bot.send_photo(
                        chat_id, photo=IMG_FILES[idx],
                        caption=GALLERY_CAPS[idx], parse_mode=constants.ParseMode.MARKDOWN
                    )
                except Exception as ee:
                    log.error(f"שגיאה בשליחת תמונה {idx}: {ee}")

    await context.bot.send_message(
        chat_id,
        "רוצים לראות איך זה עובד?\nהתנסו עכשיו בחינם! שלב ראשון בוחרים תמונה!\n\nבחר קלף זה",
        reply_markup=REPLY_KB,
    )

    await show_card(context, chat_id, 0)

async def show_card(context: ContextTypes.DEFAULT_TYPE, chat_id: int, idx: int) -> None:
    if not IMG_FILES or idx >= len(IMG_FILES):
        await context.bot.send_message(chat_id, "⚠️ אין תמונות זמינות כרגע")
        return

    caption = (
        "💥 קלף זה יכול להיות שלכם *למכירה חוזרת כבר היום!*\n"
        "🏷️ *מבצע היום — 39 ₪ בלבד*\n"
        "🖼️ לרכישת קלף שתוכלו למכור שוב כמה פעמים שתרצו, אנא "
        "בחרו עם החיצים תמונה מהגלריות שלנו ולחצו על לחצן 'רכישת תמונה זו'"
    )

    buttons = []
    if idx > 0:
        buttons.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"card_{idx-1}"))
    buttons.append(InlineKeyboardButton("🛒 בחירת הקלף", callback_data="select_card"))
    if idx < len(IMG_FILES) - 1:
        buttons.append(InlineKeyboardButton("➡️ הבא", callback_data=f"card_{idx+1}"))
    keyboard = InlineKeyboardMarkup([buttons])

    try:
        await context.bot.send_photo(
            chat_id, photo=IMG_FILES[idx], caption=caption, reply_markup=keyboard, parse_mode=constants.ParseMode.MARKDOWN
        )
    except Exception as e:
        log.error(f"שגיאה בהצגת קלף {idx}: {e}")
        await context.bot.send_message(chat_id, "❌ שגיאה בהצגת הקלף")

async def select_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await context.bot.send_message(
        query.message.chat.id,
        "5. איזה מחיר תרצו לגבות על קלף זה מחבריכם? כך תראו מה פוטנציאל התשואה שלכם מכל מכירה נוספת של הקלף שלכם:\n6. אנא הזינו מחיר (בין 42-149 ₪):",
    )
    return PRICE

async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = int(update.message.text)
        if 42 <= price <= 149:
            context.user_data["price"] = price
            profit_percent = min(80, 30 + (price - 42) // 2)

            card_idx = context.user_data.get("current_card_idx", 0)
            if IMG_FILES and card_idx < len(IMG_FILES):
                await update.message.reply_photo(
                    photo=IMG_FILES[card_idx],
                    caption=f"👏 לפי המחיר שביקשתם ({price} ₪) אתם תרוויחו {profit_percent}% מכל מכירה חוזרת!!\n\nלאחר רכישת הקלף ב-39 ש\"ח בלבד תוכל לעשות עסקים!!",
                )

            await update.message.reply_text("מעולה! עכשיו נזדקק לפרטים שלכם:\n\nאנא הזינו את שמכם הפרטי:")
            return FIRST_NAME
        else:
            await update.message.reply_text("❌ המחיר חייב להיות בין 42 ל-149 ₪. נסו שוב:")
            return PRICE
    except ValueError:
        await update.message.reply_text("❌ אנא הזינו מספר תקין בין 42 ל-149 ₪:")
        return PRICE

async def receive_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["first_name"] = update.message.text
    await update.message.reply_text("📝 אנא הזינו את שם המשפחה:")
    return LAST_NAME

async def receive_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["last_name"] = update.message.text
    await update.message.reply_text("📞 אנא הזינו את מספר הטלפון:")
    return PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["phone"] = update.message.text
    await update.message.reply_text(
        "💳 **אפשרויות תשלום:**\n\n"
        "לרכישה דרך העברה בנקאית, או חשבונות המצורפים ניתן ללחוץ על הכפתורים התואמים.\n"
        "הנתונים המוצגים כאן יכולים להיות שלכם!",
        reply_markup=PAYMENT_KB,
        parse_mode=constants.ParseMode.MARKDOWN,
    )
    return ConversationHandler.END

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    payment_methods = {
        "payment_tg": [
            "💡 הידעתם שיש ארנק בטלגרם? כל מה שצריך לעשות זה ללחוץ @wallet ויש לכם ארנק קריפטו מאובטח!",
            "💰 אם זה לא די, הארנק שלכם כאן אינו מחוייב במס ומוגדר כהשקעה! להעברת טלגרם לחשבון המפתח:",
            "UQCr743gEr_nqV_0SBkSp3CtYS_15R3LDLBvLmKeEv7XdGvp",
        ],
        "payment_paypal": "💸 פייפאל: https://paypal.me/osifdu",
        "payment_bit": "📱 ביט או פייבוקס: 0546671882",
        "payment_bank": """🏦 **העברה בנקאית - השיטה המועדפת**

להשלמת הרכישה, אנא בצע העברה בנקאית לפרטים הבאים:

👤 **המוטב:** קאופמן צביקה
🏦 **בנק:** הפועלים
📍 **סניף:** כפר גנים (153)
🔢 **חשבון:** 73462
💸 **סכום:** 39 ₪

**לאחר ההעברה:**
1. שמור/צלם את אישור ההעברה
2. לחץ על '📸 העלה אישור העברה'
3. העלה את תמונת האישור
4. אנו ניצור איתך קשר תוך 24 שעות!""",
    }

    method_data = payment_methods.get(query.data)
    if method_data:
        if isinstance(method_data, list):
            for msg in method_data:
                await asyncio.sleep(0.3)
                await query.message.reply_text(msg)
        else:
            await query.message.reply_text(method_data)

    if query.data == "payment_bank":
        await query.message.reply_text(
            "💳 **השלם רכישה - העברה בנקאית**\n\n"
            "להשלמת התהליך, אנא לחץ על הכפתור '🛒 השלם רכישה'",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🛒 השלם רכישה", callback_data="final_purchase")]]
            ),
        )

    if query.data == "final_purchase":
        await start_bank_transfer(update, context)

async def start_bank_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    bank_details = """
💼 **השלמת רכישה - העברה בנקאית**

🎯 **המטרה:** העברה בנקאית לחשבוננו ושליחת אימות תשלום ידני

📋 **הוראות:**

1. **בצע העברה בנקאית** לפרטים הבאים:
   👤 **המוטב:** קאופמן צביקה
   🏦 **בנק:** הפועלים
   📍 **סניף:** כפר גנים (153)
   🔢 **חשבון:** 73462
   💸 **סכום:** 39 ₪

2. **שמור את אישור ההעברה** מהבנק/האפליקציה
3. **לחץ על הכפתור למטה** להעלאת אישור ההעברה
4. **ניצור איתך קשר** תוך 24 שעות להפעלת הבוט הייחודי שלך!

📞 **לשאלות:** https://t.me/OsifFin/
"""
    await query.message.reply_text(bank_details, reply_markup=BANK_TRANSFER_KB, parse_mode=constants.ParseMode.MARKDOWN)

async def upload_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📸 **העלאת אישור העברה**\n\n"
        "אנא העלה עכשיו את תמונת אישור ההעברה הבנקאית.\n"
        "אפשר לצלם מסך מהאפליקציה או לצלם את האישור."
    )
    return PAYMENT_CONFIRMATION

async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data
    user_id = update.message.from_user.id

    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        os.makedirs("receipts", exist_ok=True)
        photo_path = f"receipts/receipt_{user_id}_{update.message.message_id}.jpg"
        await photo_file.download_to_drive(photo_path)

        admin_message = (
            "🛒 **רכישה חדשה - אישור העברה התקבל!**\n\n"
            f"👤 **לקוח:** {user_data.get('first_name', 'N/A')} {user_data.get('last_name', 'N/A')}\n"
            f"📞 **טלפון:** {user_data.get('phone', 'N/A')}\n"
            f"💰 **מחיר שהתבקש:** {user_data.get('price', 'N/A')} ₪\n"
            f"🆔 **User ID:** {user_id}\n"
            f"👤 **Username:** @{update.message.from_user.username or 'N/A'}\n\n"
            f"📧 **ליצירת קשר ישיר:** https://t.me/{update.message.from_user.username or 'N/A'}\n"
            f"💬 **לשליחת בוט ייחודי:** User ID: {user_id}"
        )

        try:
            await context.bot.send_photo(chat_id=ADMIN_USER_ID, photo=photo_path, caption=admin_message)
            await context.bot.send_message(chat_id=PAYMENT_GROUP_ID, text=admin_message)
            await update.message.reply_photo(
                photo=photo_path,
                caption=(
                    "✅ **אישור ההעברה התקבל!**\n\n"
                    "📧 תוך 24 שעות ניצור איתך קשר ישיר בטלגרם\n"
                    "🤖 לקבלת הבוט הייחודי שלך!\n\n"
                    "👤 **פרטיך:**\n"
                    f"שם: {user_data.get('first_name', 'N/A')} {user_data.get('last_name', 'N/A')}\n"
                    f"טלפון: {user_data.get('phone', 'N/A')}\n\n"
                    "📞 **לשאלות:** https://t.me/OsifFin/"
                ),
            )
            await update.message.reply_text(
                "💼 **יצירת קשר עסקי ישיר**\n\n"
                "כעת נוצר קשר עסקי ישיר בינך לבין צוות NIFTII!\n\n"
                "👨‍💼 **אוסיף אונגר** יוצר איתך קשר ישירות\n"
                "📧 דרך הטלגרם האישי: https://t.me/OsifEU\n\n"
                "תוך 24 שעות תקבל:\n"
                "• בוט טלגרם ייחודי משלך\n"
                "• הדרכה מלאה\n"
                "• ליווי אישי\n\n"
                "🎉 ברוך הבא לקהילת NIFTII!",
                reply_markup=REPLY_KB,
            )
        except Exception as e:
            log.error(f"שגיאה בשליחת אישור: {e}")
            await update.message.reply_text(
                "❌ שגיאה בשליחת האישור. אנא פנה לתמיכה: https://t.me/OsifFin/", reply_markup=REPLY_KB
            )
    else:
        await update.message.reply_text("❌ אנא העלה תמונה של אישור ההעברה.", reply_markup=BANK_TRANSFER_KB)
        return PAYMENT_CONFIRMATION

    return ConversationHandler.END

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📞 **צור קשר:**\n\nלפרטים נוספים או תמיכה:\n👨‍💼 https://t.me/OsifFin/\n\nנשמח לעזור לך!",
        reply_markup=REPLY_KB,
    )

async def handle_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"🌐 **אתר האינטרנט שלנו:**\n\n{SITE_URL}", reply_markup=REPLY_KB)

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

async def handle_purchase_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await open_shop(update, context)

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "open_shop":
        await open_shop(update, context)
    elif data.startswith("card_"):
        idx = int(data.split("_")[1])
        context.user_data["current_card_idx"] = idx
        await show_card(context, query.message.chat.id, idx)
    elif data == "select_card":
        await select_card(update, context)
    elif data == "upload_receipt":
        await upload_receipt(update, context)
    elif data in ["payment_tg", "payment_paypal", "payment_bit", "payment_bank", "final_purchase"]:
        await handle_payment_method(update, context)

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(select_card, pattern="^select_card$"),
            CallbackQueryHandler(upload_receipt, pattern="^upload_receipt$"),
        ],
        states={
            PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price)],
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_first_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_last_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            PAYMENT_CONFIRMATION: [MessageHandler(filters.PHOTO, receive_receipt)],
        },
        fallbacks=[],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(callback_router))

    # כפתורי תפריט תחתון
    app.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), handle_contact))
    app.add_handler(MessageHandler(filters.Text("🌐 אתר"), handle_website))
    app.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), handle_main_menu))
    app.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), handle_purchase_shop))

    log.info("🤖 מתחיל את בוט NIFTII...")

    from telegram import Update as TgUpdate
    app.run_polling(
        poll_interval=0,  # הכי מהיר מקומית
        allowed_updates=TgUpdate.ALL_TYPES,
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
