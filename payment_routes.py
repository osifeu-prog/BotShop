from fastapi import APIRouter
from config import config

router = APIRouter()

@router.get("/methods")
async def list_payment_methods():
    return {
        "methods": ["bank_transfer", "card", "crypto"],
        "links": config.PAYMENT_LINKS,
    }
