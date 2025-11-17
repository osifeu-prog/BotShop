# user_bot_handler.py
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

class UserBotHandler:
    def __init__(self):
        self.base_url = "https://api.telegram.org/bot"
    
    async def send_welcome_message(self, bot_token: str, chat_id: int, user_id: int):
        """
        שולח הודעת ברוך הבא בבוט האישי
        """
        try:
            welcome_text = (
                "🤖 *ברוך הבא לבוט האישי שלך!*\n\n"
                
                "🎉 *התשלום אושר! ברוך הבא לבעלי הנכסים!*\n\n"
                
                "💎 *הנכס הדיגיטלי שלך מוכן:*\n"
                f"🔗 *לינק אישי:* `https://t.me/Buy_My_Shop_bot?start=ref_{user_id}`\n\n"
                
                "🚀 *מה עכשיו?*\n"
                "1. שתף את הלינק עם אחרים\n"
                "2. השתמש בבוט האישי שלך למכירות\n"
                "3. כל רכישה דרך הלינק שלך מתועדת\n"
                "4. תוכל למכור נכסים נוספים\n"
                "5. צבור הכנסה מהפצות\n\n"
                
                "👥 *גישה לקהילה:*\n"
                "https://t.me/+HIzvM8sEgh1kNWY0\n\n"
                
                "💼 *ניהול הנכס:*\n"
                "השתמש בכפתור '👤 האזור האישי שלי'\n"
                "כדי לגשת לבוט שלך ולנהל את הנכס"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "💎 מכור נכסים", "callback_data": "sell_digital_asset"},
                        {"text": "🔗 שתף לינק", "callback_data": "share_link"}
                    ],
                    [
                        {"text": "📊 סטטיסטיקות", "callback_data": "stats"},
                        {"text": "👥 קבוצת קהילה", "url": "https://t.me/+HIzvM8sEgh1kNWY0"}
                    ],
                    [
                        {"text": "🆘 תמיכה", "url": "https://t.me/Buy_My_Shop_bot"}
                    ]
                ]
            }
            
            url = f"{self.base_url}{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": welcome_text,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Failed to send welcome message: {e}")
            return False

# instance גלובלי
user_bot_handler = UserBotHandler()
