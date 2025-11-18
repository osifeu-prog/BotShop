import os
import logging
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger("slhnet")


# ==========
# הגדרות בסיס ל-SLHNET (BSC / Token)
# אפשר לשלוט בזה דרך משתני סביבה ברליווי
# ==========

CHAIN_ID = int(os.getenv("CHAIN_ID", "56"))  # Binance Smart Chain mainnet
RPC_URL = os.getenv("RPC_URL", "https://bsc-dataseed.binance.org")
TOKEN_ADDRESS = os.getenv("SLH_TOKEN_ADDRESS", "")
TOKEN_SYMBOL = os.getenv("SLH_TOKEN_SYMBOL", "SLH")
TOKEN_DECIMALS = int(os.getenv("SLH_TOKEN_DECIMALS", "15"))
SAFE_MODE = os.getenv("SAFE_MODE", "false").lower() in ("1", "true", "yes")


def get_public_meta() -> dict:
    """
    מחזיר מידע פומבי בסיסי על הרשת והטוקן.
    זה מה שנקרא מ-/meta.
    """
    return {
        "chain_id": CHAIN_ID,
        "rpc_url": RPC_URL,
        "token_address": TOKEN_ADDRESS,
        "decimals": TOKEN_DECIMALS,
        "symbol": TOKEN_SYMBOL,
        "safe_mode": SAFE_MODE,
        # כרגע לא מחוברים באמת ל-node (ON-CHAIN),
        # אבל המבנה מוכן לחיבור עתידי.
        "is_connected": True,
    }


def get_public_token_balance(address: str) -> dict:
    """
    החזרת יתרה פומבית של טוקן עבור address.
    כרגע מחזיר 0 כמחלקה – מוכן לחיבור ל-BNB/SLH בשלב הבא.
    """
    # TODO: לחבר ל-node או ל-SLH API חיצוני (Gateway) כדי להביא יתרת SLH אמיתית.
    return {
        "address": address,
        "token": TOKEN_ADDRESS,
        "symbol": TOKEN_SYMBOL,
        "decimals": TOKEN_DECIMALS,
        "raw_balance": "0",
        "balance": 0.0,
    }


def get_public_token_price() -> dict:
    """
    החזרת מחיר משוער של הטוקן (כרגע סטאבי).
    אפשר לחבר מאוחר יותר ל-API חיצוני (Dex / CEX).
    """
    return {
        "symbol": TOKEN_SYMBOL,
        "price_usd": None,
        "source": "not_connected_yet",
    }


def get_public_staking_info() -> dict:
    """
    מידע סטאבי על סטייקינג – מוכן לחיבור עתידי.
    """
    return {
        "apy": None,
        "lock_period_days": None,
        "notes": "staking module not connected yet – this is a placeholder.",
    }


# ==========
# FastAPI Routes – מחוברים ע"י main.py עם prefix=/extra
# ==========


@router.get("/meta")
def meta_route():
    """
    GET /extra/meta
    """
    return get_public_meta()


@router.get("/token/balance")
def balance_route(address: str):
    """
    GET /extra/token/balance?address=0x...
    """
    return get_public_token_balance(address)


@router.get("/token/price")
def price_route():
    """
    GET /extra/token/price
    """
    return get_public_token_price()


@router.get("/staking/info")
def staking_route():
    """
    GET /extra/staking/info
    """
    return get_public_staking_info()
