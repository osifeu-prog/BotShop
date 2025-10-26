import os, math, asyncio
from typing import Dict, Tuple
import httpx

# ------- Pricing -------
def nis_price() -> float:
    try:
        return float(os.getenv("ENTRY_PRICE_NIS", "39"))
    except Exception:
        return 39.0

def default_fx() -> float:
    # ILS per 1 USD (e.g., 3.7) — can be overridden by FX_USDILS
    try:
        v = float(os.getenv("FX_USDILS", "3.7"))
        return v if v > 0 else 3.7
    except Exception:
        return 3.7

async def fetch_fx_usdils(timeout_sec: float = 4.0) -> float:
    # exchangerate.host: free & no-key; graceful fallback on failure.
    url = "https://api.exchangerate.host/latest?base=USD&symbols=ILS"
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            rate = float(data["rates"]["ILS"])
            return rate
    except Exception:
        return default_fx()

async def quote_prices() -> Tuple[float, float, float]:
    """return (nis, usd, fx) where fx = ILS per USD"""
    nis = nis_price()
    fx = await fetch_fx_usdils()
    usd = nis / fx if fx > 0 else nis / default_fx()
    return (round(nis,2), round(usd,2), round(fx,4))

# ------- Payment links / texts -------
def payment_urls(chat_id: int) -> Dict[str, str]:
    base = (os.getenv("PAYMENT_LINK_BASE","") or "").rstrip("/")
    paypal = base if base.startswith("http") else ""
    return {
        "paypal": paypal,
        "bank": "inline",
        "bit": "inline",
    }

def bank_text() -> str:
    return (
        "🏦 העברה בנקאית:\n"
        "בנק: הבנק הפועלים\n"
        "סניף: כפר גנים (153)\n"
        "חשבון: 73462\n"
        "שם מוטב: קאופמן צביקה\n\n"
        "לאחר ההעברה, שלח צילום מסך כאן לאישור מהיר ✅"
    )

def bit_text() -> str:
    return (
        "📲 ביט / PayBox לתשלום נוח:\n"
        "מספר: 054-667-1882\n"
        "שם: Osif\n\n"
        "לאחר התשלום, שלח צילום מסך כאן לאישור מהיר ✅"
    )