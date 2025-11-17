# social_api.py - FastAPI Router לשכבה חברתית / אזור אישי
from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Dict, Any, Optional, List

try:
    from db import (
        get_user_summary,
        store_user,
        add_referral,
        create_reward,
        get_support_tickets,
        create_support_ticket,
        get_promoter_summary,
        update_promoter_settings,
    )
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

router = APIRouter(prefix="/api", tags=["social"])

def require_db():
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DB disabled")
    return True

@router.post("/telegram-login")
async def telegram_login(user: Dict[str, Any], _=Depends(require_db)):
    """
    נקודת כניסה לקבלת משתמש מהווידג'ט של Telegram Login (Frontend).
    שומר את המשתמש ב-DB (אם קיים DB) ומחזיר OK.
    """
    try:
        user_id = int(user.get("id"))
        username = user.get("username")
        first_name = user.get("first_name")
        last_name = user.get("last_name")
        store_user(user_id, username, first_name, last_name)
        return {"status": "ok", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad user payload: {e}")

@router.get("/my")
async def my_summary(user_id: Optional[int] = None, _=Depends(require_db)):
    """
    מחזיר סיכום אזור אישי – נדרש user_id (מגיע מה-Frontend אחרי Telegram Login).
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    summary = get_user_summary(user_id) or {}
    return {"status": "ok", "data": summary}

@router.post("/promoter/update")
async def update_promoter(
    payload: Dict[str, Any],
    _=Depends(require_db),
):
    """
    עדכון הגדרות מקדם: bank_details / personal_group_link / global_group_link
    """
    try:
        user_id = int(payload["user_id"])
    except Exception:
        raise HTTPException(status_code=400, detail="user_id missing or invalid")

    bank_details = payload.get("bank_details")
    personal_group_link = payload.get("personal_group_link")
    global_group_link = payload.get("global_group_link")

    update_promoter_settings(
        user_id,
        bank_details=bank_details,
        personal_group_link=personal_group_link,
        global_group_link=global_group_link
    )
    return {"status": "ok"}

@router.get("/support/tickets")
async def support_tickets(status: Optional[str] = None, limit: int = 50, _=Depends(require_db)):
    """
    קריאת טיקטים (לשימוש בעתיד בלוח בקרה)
    """
    tickets = get_support_tickets(status, limit)
    return {"status": "ok", "tickets": tickets}

@router.post("/support/create")
async def support_create(payload: Dict[str, Any], _=Depends(require_db)):
    """
    יצירת טיקט תמיכה חדש
    """
    try:
        user_id = int(payload["user_id"])
        subject = payload.get("subject", "תמיכה כללית")
        message = payload.get("message", "")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")

    ticket_id = create_support_ticket(user_id, subject, message)
    return {"status": "ok", "ticket_id": ticket_id}
