import os
import logging
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger("slhnet")


CHAIN_ID = int(os.getenv("CHAIN_ID", "56"))
RPC_URL = os.getenv("RPC_URL", "https://bsc-dataseed.binance.org")
TOKEN_ADDRESS = os.getenv("SLH_TOKEN_ADDRESS", "")
TOKEN_SYMBOL = os.getenv("SLH_TOKEN_SYMBOL", "SLH")
TOKEN_DECIMALS = int(os.getenv("SLH_TOKEN_DECIMALS", "15"))
SAFE_MODE = os.getenv("SAFE_MODE", "false").lower() in ("1", "true", "yes")


def get_public_meta() -> dict:
    return {
        "chain_id": CHAIN_ID,
        "rpc_url": RPC_URL,
        "token_address": TOKEN_ADDRESS,
        "decimals": TOKEN_DECIMALS,
        "symbol": TOKEN_SYMBOL,
        "safe_mode": SAFE_MODE,
        "is_connected": True,
    }


def get_public_token_balance(address: str) -> dict:
    return {
        "address": address,
        "token": TOKEN_ADDRESS,
        "symbol": TOKEN_SYMBOL,
        "decimals": TOKEN_DECIMALS,
        "raw_balance": "0",
        "balance": 0.0,
    }


def get_public_token_price() -> dict:
    return {
        "symbol": TOKEN_SYMBOL,
        "price_usd": None,
        "source": "not_connected_yet",
    }


def get_public_staking_info() -> dict:
    return {
        "apy": None,
        "lock_period_days": None,
        "notes": "staking module not connected yet – this is a placeholder.",
    }


@router.get("/meta")
def meta_route():
    return get_public_meta()


@router.get("/token/balance")
def balance_route(address: str):
    return get_public_token_balance(address)


@router.get("/token/price")
def price_route():
    return get_public_token_price()


@router.get("/staking/info")
def staking_route():
    return get_public_staking_info()
