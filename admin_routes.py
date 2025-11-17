from fastapi import APIRouter, Depends
from auth_manager import auth_required
from database import db
from config import config

router = APIRouter()

@router.get("/healthz")
async def admin_health(user = Depends(auth_required)):
    return {
        "ok": True,
        "db": db.health_check(),
        "landing_url": config.LANDING_URL,
    }
