import logging
from fastapi import APIRouter

logger = logging.getLogger("slhnet.public")
router = APIRouter()


@router.get("/ping")
def ping():
    return {"ok": True}


@router.get("/info")
def info():
    return {
        "service": "SLHNET BotShop / Buy_My_Shop",
        "description": "Public API skeleton for SLH / BotShop ecosystem.",
    }
