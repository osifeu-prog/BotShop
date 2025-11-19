import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter

logger = logging.getLogger("slhnet.social")
router = APIRouter()


_FAKE_PROFILE_STORE: Dict[int, Dict[str, Any]] = {}


def _get_or_create_profile(user_id: int) -> Dict[str, Any]:
    if user_id not in _FAKE_PROFILE_STORE:
        _FAKE_PROFILE_STORE[user_id] = {
            "user_id": user_id,
            "username": None,
            "bank_details": None,
            "personal_group_link": None,
        }
    return _FAKE_PROFILE_STORE[user_id]


@router.get("/profile/{user_id}")
def get_profile(user_id: int) -> Dict[str, Any]:
    return _get_or_create_profile(user_id)


@router.post("/profile/{user_id}/bank")
def set_bank_details(user_id: int, bank_details: str, username: Optional[str] = None) -> Dict[str, Any]:
    p = _get_or_create_profile(user_id)
    p["bank_details"] = bank_details
    if username:
        p["username"] = username
    return p


@router.post("/profile/{user_id}/group")
def set_personal_group(user_id: int, group_link: str, username: Optional[str] = None) -> Dict[str, Any]:
    p = _get_or_create_profile(user_id)
    p["personal_group_link"] = group_link
    if username:
        p["username"] = username
    return p
