import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter

logger = logging.getLogger("slhnet.core")
router = APIRouter()


_FAKE_REFERRAL_STORE: Dict[int, Dict[str, Any]] = {}


def _get_user_referral(user_id: int) -> Dict[str, Any]:
    if user_id not in _FAKE_REFERRAL_STORE:
        _FAKE_REFERRAL_STORE[user_id] = {
            "user_id": user_id,
            "total_leads": 0,
            "total_payers": 0,
            "campaigns": {},
        }
    return _FAKE_REFERRAL_STORE[user_id]


@router.get("/referral/{user_id}")
def get_referral_info(user_id: int) -> Dict[str, Any]:
    data = _get_user_referral(user_id)
    return data


@router.post("/referral/{user_id}/lead")
def register_lead(user_id: int, campaign: Optional[str] = None) -> Dict[str, Any]:
    rec = _get_user_referral(user_id)
    rec["total_leads"] += 1

    if campaign:
        rec["campaigns"].setdefault(campaign, {"leads": 0, "payers": 0})
        rec["campaigns"][campaign]["leads"] += 1

    return rec


@router.post("/referral/{user_id}/payer")
def register_payer(user_id: int, campaign: Optional[str] = None) -> Dict[str, Any]:
    rec = _get_user_referral(user_id)
    rec["total_payers"] += 1

    if campaign:
        rec["campaigns"].setdefault(campaign, {"leads": 0, "payers": 0})
        rec["campaigns"][campaign]["payers"] += 1

    return rec
