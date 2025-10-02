# -*- coding: utf-8 -*-
import os
import random
import logging
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
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

# ---------------- Windows asyncio fix ----------------
if sys.platform.startswith("win") and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ---------------- ENV ----------------
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=True)

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
PIC_DIR = os.getenv("IMAGE_LIBRARY_PATH", "./images").strip()
PAYMENT_GROUP_ID = os.getenv("PAYMENT_GROUP_ID", "-1001699922921").strip()
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "224223270").strip()
SITE_URL = os.getenv("SITE_URL", "https://osifeu-prog.github.io/OsifsCardShop").strip()

# ---------------- Basic checks ----------------
if not TOKEN:
    print("❌ שגיאה: TELEGRAM_TOKEN לא נמצא או ריק!")
    sys.exit(1)

print(f"✅ טוקן נטען: {TOKEN[:10]}...")
print(f"📁 תמונות: {PIC_DIR}")

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("niftii-bot")

# ---------------- Load images ----------------
try:
    if os.path.exists(PIC_DIR):
        IMG_FILES = [
            str(p)
            for p in Path(PIC_DIR).iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        ]
        IMG_COUNT = len(IMG_FILES)
        log.info(f"✅ נטענו {IMG_COUNT} תמונות מ-{PIC_DIR}")
    else:
        log.warning(f"❌ תיקיית תמונות לא נמצאה: {PIC_DIR}")
        IMG_FILES = []
        IMG_COUNT = 0
except Exception as e:
    log.error(f"❌ שגיאה בטעינת תמונות: {e}")
    IMG_FILES = []
    IMG_COUNT = 0

# ---------------- Gallery captions ----------------
GALLERY_CAPS = [
    "3. בוט זה יסייע לכם להרחיב את מכירותיכם, להגדיר את השפע הכלכלי שלכם, ולקיים קשר עם הקהילה שתיווצר סביבכם!",
    "3.1 🖼️ היום לכל אחד ואחת יכול להיות נכס דיגיטלי רווחי\n— חנות למכירת קלפי NFT מניבה וכלכלית שלכם!\nתוכלו למכור, לשווק ולהרוויח *בכל יום ויום* ממכירה חוזרת של התמונה שרכשתם – ישירות לחשבון הבנק שלכם!💸",
    "3.2 בבוט זה בנוי כחנות קלפים בו תוכלו לרכוש קלף + חנות משלכם לשווק למכירה חוזרת, ולהרוויח מכל מכירה של הקלף שלכם.",
    "3.4 הרעיון פשוט: אתם משתפים את הקלף שלכם, מרוויחים ישירות לבנק שלכם, ואנחנו מרוויחים מרישום הבוטים של מצטרפים חדשים לקהילת האספנים של ישראל!\n**WIN WIN WIN WIN**",
    "3.5 בהצטרפות ל\"NIFTII משחק החנויות שמשגע את המדינה\" תזכו להצטרף לקהילת העסקים המובילה בישראל, לזכות בשלל הטבות, ולהוביל לשינוי כלכלי וחברתי דרך כל קלף שתפרסמו ותמכרו!!",
    "3.6 ככל שתמכרו יותר – דירוגכם יעלה ותוכלו להרוויח יותר, הן ברווח ישיר, והן לאחר הנפקת המשחק בבורסות השונות.",
    "3.7 כן כן, קראתם נכון! משחק זה מבוסס NFT – סוג של קריפטו ייחודי לשיווק תמונות.\nמאחר שאפליקציה זו נבנתה במיוחד עבור בעלי עסקים בישראל, הערך הכלכלי של התמונות הללו שווה לכם כסף!",
]

# ---------------- Conversation states ----------------
PRICE, FIRST_NAME, LAST_NAME, PHONE, PAYMENT_CONFIRMATION = range(5)

# ---------------- Keyboards ----------------
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

# ---------------- Bot handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    context.user_data.clear()

    # תמונה רנדומלית
    if IMG_COUNT:
        img_path = random.choice(IMG_FILES)
        try:
            with open(img_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id,
                    f,
                    caption="🎉 ברוכים הבאים ל-NIFTII!! משחק ה-NFT שמשגע את המדינה! 🔥",
                )
        except Exception as e:
            log.error(f"שגיאה בשליחת תמונה: {e}")

    # הודעות פתיחה
    await context.bot.send_message(
        chat_id,
        text="💎 *היום זה כבר לא חלום* — לכל אחד ואחת יכול להיות קניון!! 🛍️",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    # כפתור מידע
    info_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📖 מידע", callback_data="open_shop")]])

    await context.bot.send_message(
        chat_id,
        text='רוצים לדעת איך אתם יכולים להיות מיליונרים ובקרוב? 👉\nלחצו על כפתור "מידע" לקבלת כל הידע לאיזה חנות קלפים משלכם בטלגרם.',
        reply_markup=info_kb,
    )

    # תפריט ראשי
    await context.bot.send_message(
        chat_id,
        text="בחרו אפשרות נוספת מהתפריט למטה:",
        reply_markup=REPLY_KB,
    )

async def open_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # טיפול גם ב-callback query וגם בהודעת טקסט
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat.id
    else:
        chat_id = update.effective_chat.id

    # רשימת יתרונות
    benefits_text = (
        "✅ מערכת שלמה לשיווק רשתי\n"
        "✅ הכנסה קבועה ומשתלמת\n"
        "✅ ללא מאמץ\n"
        "✅ ללא התחייבות\n"
        "✅ הפתעות ותמלוגים"
    )

    await context.bot.send_message(chat_id, benefits_text, reply_markup=REPLY_KB)

    # גלריה
    if IMG_COUNT > 0:
        media_group = []
        for idx, caption in enumerate(GALLERY_CAPS):
            if idx < len(IMG_FILES):
                try:
                    with open(IMG_FILES[idx], "rb") as photo_file:
                        media_group.append(
                            InputMediaPhoto(
                                media=photo_file,
                                caption=caption,
                                parse_mode=constants.ParseMode.MARKDOWN,
                            )
                        )
                except Exception as e:
                    log.error(f"שגיאה בטעינת תמונה {idx}: {e}")

        if media_group:
            try:
                await context.bot.send_media_group(chat_id=chat_id, media=media_group)
            except Exception as e:
                log.error(f"שגיאה בשליחת גלריה: {e}")
                for idx, caption in enumerate(GALLERY_CAPS[: min(3, len(IMG_FILES))]):
                    try:
                        with open(IMG_FILES[idx], "rb") as photo_file:
                            await context.bot.send_photo(
                                chat_id,
                                photo_file,
                                caption=caption,
                                parse_mode=constants.ParseMode.MARKDOWN,
                            )
                    except Exception as e:
                        log.error(f"שגיאה בשליחת תמונה {idx}: {e}")

    # הזמנה לדמו
    await context.bot.send_message(
        chat_id,
        "רוצים לראות איך זה עובד?\nהתנסו עכשיו בחינם! שלב ראשון בוחרים תמונה!\n\nבחר קלף זה",
        reply_markup=REPLY_KB,
    )

    # הצגת קלף ראשון
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

    # כפתורי ניווט
    buttons = []
    if idx > 0:
        buttons.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"card_{idx-1}"))

    buttons.append(InlineKeyboardButton("🛒 בחירת הקלף", callback_data="select_card"))

    if idx < len(IMG_FILES) - 1:
        buttons.append(InlineKeyboardButton("➡️ הבא", callback_data=f"card_{idx+1}"))

    keyboard = InlineKeyboardMarkup([buttons])

    try:
        with open(IMG_FILES[idx], "rb") as photo_file:
            await context.bot.send_photo(
                chat_id,
                photo_file,
                caption=caption,
                reply_markup=keyboard,
                parse_mode=constants.ParseMode.MARKDOWN,
            )
    except Exception as e:
        log.error(f"שגיאה בהצגת קלף {idx}: {e}")
        await context.bot.send_message(chat_id, "❌ שגיאה בהצגת הקלף")

async def handle_card_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("card_"):
        idx = int(data.split("_")[1])
        context.user_data["current_card_idx"] = idx
        await show_card(context, query.message.chat.id, idx)

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

            # שליחת התמונה שנבחרה עם חישוב הרווח
            card_idx = context.user_data.get("current_card_idx", 0)
            if IMG_FILES and card_idx < len(IMG_FILES):
                with open(IMG_FILES[card_idx], "rb") as photo_file:
                    await update.message.reply_photo(
                        photo_file,
                        caption=(
                            f"👏 לפי המחיר שביקשתם ({price} ₪) אתם תרוויחו {profit_percent}% מכל מכירה חוזרת!!\n\n"
                            "לאחר רכישת הקלף ב-39 ש\"ח בלבד תוכל לעשות עסקים!!"
                        ),
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

4. **אנו ניצור איתך קשר** תוך 24 שעות להפעלת הבוט הייחודי שלך!

📞 **לשאלות:** https://t.me/OsifFin/
    """

    await query.message.reply_text(
        bank_details, reply_markup=BANK_TRANSFER_KB, parse_mode=constants.ParseMode.MARKDOWN
    )

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
        # קבלת התמונה באיכות הגבוהה ביותר
        photo_file = await update.message.photo[-1].get_file()
        photo_path = f"receipts/receipt_{user_id}_{update.message.message_id}.jpg"

        # יצירת תיקיית receipts אם לא קיימת
        os.makedirs("receipts", exist_ok=True)

        await photo_file.download_to_drive(photo_path)

        # הודעה למנהל עם כל הפרטים
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
            # שליחה למנהל עם התמונה
            with open(photo_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=ADMIN_USER_ID, photo=photo, caption=admin_message
                )

            # שליחה גם לקבוצת התשלומים
            await context.bot.send_message(chat_id=PAYMENT_GROUP_ID, text=admin_message)

            # אישור ללקוח עם עותק של התמונה
            with open(photo_path, "rb") as photo:
                await update.message.reply_photo(
                    photo,
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

            # הודעה נוספת עם פרטי קשר
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
                "❌ שגיאה בשליחת האישור. אנא פנה לתמיכה: https://t.me/OsifFin/",
                reply_markup=REPLY_KB,
            )
    else:
        await update.message.reply_text(
            "❌ אנא העלה תמונה של אישור ההעברה.", reply_markup=BANK_TRANSFER_KB
        )
        return PAYMENT_CONFIRMATION

    return ConversationHandler.END

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📞 **צור קשר:**\n\nלפרטים נוספים או תמיכה:\n👨‍💼 https://t.me/OsifFin/\n\nנשמח לעזור לך!",
        reply_markup=REPLY_KB,
    )

async def handle_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"🌐 **אתר האינטרנט שלנו:**\n\n{SITE_URL}", reply_markup=REPLY_KB
    )

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

async def handle_purchase_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """טיפול בלחיצה על הכפתור '✍🏻 רכישת חנות 🎯'"""
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

# ---------------- Conversation builder (with per_message=True) ----------------
def build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
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
        ],
        fallbacks=[],
        per_message=True,  # ←←← התיקון שמונע את התקיעה אחרי הזנת "מחיר"
    )

# ---------------- Optional: register for server usage ----------------
def register_handlers(app: Application) -> Application:
    """שימושי כשמייבאים את המודול לתוך שרת (Webhook)."""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(build_conversation_handler())
    app.add_handler(CallbackQueryHandler(callback_router))

    app.add_handler(MessageHandler(filters.Text("☎️ צור קשר 📞"), handle_contact))
    app.add_handler(MessageHandler(filters.Text("🌐 אתר"), handle_website))
    app.add_handler(MessageHandler(filters.Text("🔄 תפריט ראשי 📚"), handle_main_menu))
    app.add_handler(MessageHandler(filters.Text("✍🏻 רכישת חנות 🎯"), handle_purchase_shop))
    return app

# ---------------- Local polling (optional) ----------------
def main():
    """לשימוש מקומי בלבד. בפרודקשן עם Webhook תייבא ל-server.py ותקרא register_handlers."""
    app = Application.builder().token(TOKEN).build()
    register_handlers(app)
    log.info("🤖 מתחיל את בוט NIFTII (polling)...")
    print("🎉 הבוט מתחיל! לחץ Ctrl+C לעצירה.")
    app.run_polling()

if __name__ == "__main__":
    main()
