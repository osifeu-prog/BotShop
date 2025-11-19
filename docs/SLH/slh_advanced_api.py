
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db import (
    get_reserve_stats,
    get_approval_stats,
    get_top_referrers,
    get_monthly_payments,
)

router = APIRouter(prefix="/api/advanced", tags=["advanced"])


# ============
# מודלים
# ============

class YieldSimulationResponse(BaseModel):
    amount: float
    months: int
    tier: str
    monthly_rate: float
    effective_apy: float
    total_return: float
    total_with_principal: float


class TokenomicsSummary(BaseModel):
    sela_price_ils: float
    slh_per_ils: float
    income_split: Dict[str, float]
    reserve_ratio: float
    notes: List[str]


class RiskSummary(BaseModel):
    total_amount: float
    total_reserve: float
    total_net: float
    diversification_index: float
    notes: List[str]


# ============
# לוגיקה
# ============

def _monthly_rate_for_tier(tier: str) -> float:
    """
    החזרת ריבית חודשית לפי tier.
    המודל מבוסס על התיאור:
    - 10% למשקיעי פריצה ראשונים (pioneer)
    - טווח 8%-12% בהתאם ל-tier.
    """
    tier = (tier or "standard").lower()
    if tier in ("pioneer", "founder", "early-bird"):
        return 0.10
    if tier in ("early", "seed"):
        return 0.09
    if tier in ("community", "network"):
        return 0.08
    if tier in ("vip", "whale"):
        return 0.12
    return 0.07  # ברירת מחדל זהירה


def _simulate_compound(amount: float, months: int, monthly_rate: float) -> float:
    """
    חישוב ריבית דריבית חודשית.
    """
    value = amount
    for _ in range(months):
        value *= (1.0 + monthly_rate)
    return value


# ============
# Endpoints
# ============

@router.get("/yield/simulate", response_model=YieldSimulationResponse)
async def simulate_yield(
    amount: float = Query(..., gt=0, description="סכום השקעה בשקלים"),
    months: int = Query(12, ge=1, le=60, description="מספר חודשים"),
    tier: str = Query("pioneer", description="רמת המשקיע: pioneer/early/community/standard/vip"),
):
    """
    סימולציית תשואה על בסיס המודל המתמטי:
    - ריבית חודשית לפי tier
    - ריבית דריבית
    - החזרת סך רווח + APY אפקטיבי משוער.
    """
    monthly_rate = _monthly_rate_for_tier(tier)
    final_value = _simulate_compound(amount, months, monthly_rate)
    total_return = final_value - amount
    # APY אפקטיבי בקירוב (אם months >= 12)
    years = months / 12.0
    if years > 0:
        effective_apy = (final_value / amount) ** (1 / years) - 1
    else:
        effective_apy = monthly_rate * 12

    return YieldSimulationResponse(
        amount=amount,
        months=months,
        tier=tier,
        monthly_rate=monthly_rate,
        effective_apy=effective_apy,
        total_return=total_return,
        total_with_principal=final_value,
    )


@router.get("/tokenomics/summary", response_model=TokenomicsSummary)
async def tokenomics_summary():
    """
    תקציר טוקנומיקה לפי המסמך:
    - SELA = 444 ₪
    - SLH: 1 SLH לכל 1 ₪
    - חלוקת הכנסות: 30/30/20/20
    - רזרבות: 49% מכל תשלום לטובת ביטחון המערכת.
    """
    sela_price_ils = 444.0
    slh_per_ils = 1.0
    income_split = {
        "guarantee_fund": 0.30,
        "technology_and_dev": 0.30,
        "community_and_marketing": 0.20,
        "profit_and_rewards": 0.20,
    }
    reserve_ratio = 0.49

    notes = [
        "מודל מבוסס על מסמך האסטרטגיה: SELA = 444 ₪",
        "SLH מחולק ביחס 1:1 על כל שקל תשלום (ניתן לשינוי בעתיד).",
        "49% מכל תשלום נכנס לרזרבות המערכת (על בסיס payments.reserve_amount).",
        "המודל מיועד למשקיעי פריצה ראשונים עם תשואות גבוהות ולכיוון צמיחה מתונה יותר בהמשך.",
    ]

    return TokenomicsSummary(
        sela_price_ils=sela_price_ils,
        slh_per_ils=slh_per_ils,
        income_split=income_split,
        reserve_ratio=reserve_ratio,
        notes=notes,
    )


@router.get("/referrals/top")
async def top_referrers(limit: int = 10):
    """
    מחזיר את המפנים המובילים לפי טבלת referrals.
    """
    rows = get_top_referrers(limit=limit)
    return {
        "items": rows,
        "count": len(rows),
    }


@router.get("/risk/summary", response_model=RiskSummary)
async def risk_summary():
    """
    דוח סיכון פשוט המבוסס על מצב ה-reserves בפועל מה-DB.
    מאפשר לראות:
    - כמה כסף עבר בתשלומים
    - כמה מתוכו הופרש לרזרבה
    - כמה נטו נשאר
    - אינדקס דמיוני לפיזור סיכון (כרגע חישוב פשוט).
    """
    stats = get_reserve_stats() or {}
    total_amount = float(stats.get("total_amount") or 0)
    total_reserve = float(stats.get("total_reserve") or 0)
    total_net = float(stats.get("total_net") or 0)

    diversification_index = 0.0
    if total_amount > 0:
        diversification_index = min(1.0, total_reserve / total_amount)

    notes = [
        "הנתונים מבוססים על טבלת payments בבסיס הנתונים.",
        "diversification_index הוא מדד פשטני לפיזור סיכון על סמך יחס הרזרבה.",
        "ניתן להחליף מודל זה במודל Risk מתקדם יותר בהמשך.",
    ]

    return RiskSummary(
        total_amount=total_amount,
        total_reserve=total_reserve,
        total_net=total_net,
        diversification_index=diversification_index,
        notes=notes,
    )
