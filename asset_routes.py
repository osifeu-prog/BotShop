from fastapi import APIRouter
from typing import Dict, Any

from digital_ecosystem import ecosystem

router = APIRouter()

@router.post("/{user_id}/create")
async def create_asset(user_id: int, body: Dict[str, Any]):
    tier = body.get("tier", "basic")
    asset = await ecosystem.create_digital_asset(user_id=user_id, tier=tier)
    return asset.to_dict()

@router.get("/{user_id}")
async def list_assets(user_id: int):
    assets = await ecosystem.get_user_assets(user_id=user_id)
    return [a.to_dict() for a in assets]
