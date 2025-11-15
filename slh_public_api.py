"""
slh_public_api.py  ראוטר ציבורי עבור SLHNET
מטרות:
- לספק /config/public לאתר הראשי
- לספק /api/token/price, /api/token/sales, /api/posts כ-API בסיסי
- למנוע 404 בקשות מהפרונט
"""

from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter

router = APIRouter()

# קונפיג ציבורי לאתר
@router.get("/config/public")
async def get_public_config() -> Dict[str, Any]:
    return {
        "name": "SLHNET",
        "description": (
            "רשת עסקית המחברת בין חנויות דיגיטליות, טוקן SLH על Binance Smart Chain, "
            "בוטי טלגרם ורשת חברתית לשיתופי תוכן והמלצות."
        ),
        "token_symbol": "SLH",
        "token_display_price_nis": 444,
        "gateway_enabled": True,
        "wallet_section_enabled": True,
        "social_feed_enabled": True,
        "exchange_section_enabled": True,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


# מחיר טוקן  כרגע placeholder קבוע (444), אפשר לחבר אח"כ ל-API אמיתי / חוזה חכם
@router.get("/api/token/price")
async def get_token_price() -> Dict[str, Any]:
    return {
        "symbol": "SLH",
        "price_nis": 444,
        "source": "manual-placeholder",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


# מכירות / סטטיסטיקות  כרגע רשימה ריקה (אפשר להחליף בדאטה אמיתי בהמשך)
@router.get("/api/token/sales")
async def get_token_sales(limit: int = 50) -> Dict[str, Any]:
    return {
        "items": [],
        "limit": limit,
        "total": 0,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


# פוסטים מהקהילה  כרגע רשימה ריקה (להמשך חיבור לבסיס נתונים / בוט)
@router.get("/api/posts")
async def get_posts(limit: int = 20) -> Dict[str, Any]:
    return {
        "items": [],
        "limit": limit,
        "total": 0,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
