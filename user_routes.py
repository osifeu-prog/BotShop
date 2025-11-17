from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict

from auth_manager import auth_required
from database import db
from user_models import UserManager

router = APIRouter()

@router.get("/me")
async def get_me(user: Dict[str, Any] = Depends(auth_required)):
    return {"user": user}

@router.get("/{user_id}")
async def get_user(user_id: int):
    manager = UserManager(db)
    user = await manager.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.to_dict()
