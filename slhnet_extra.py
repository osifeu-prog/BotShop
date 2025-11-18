import os
import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("slhnet.extra")


class ExtraInfo(BaseModel):
    title: str
    description: str
    landing_url: str
    business_group_url: str
    logs_group_hint: str


@router.get("/slhnet/extra", response_model=ExtraInfo)
async def get_extra_info():
    landing_url = os.getenv("LANDING_URL", "https://slh-nft.com")
    business_group_url = os.getenv("BUSINESS_GROUP_URL", "")
    logs_group = os.getenv("LOGS_GROUP_CHAT_ID", "")

    return ExtraInfo(
        title="SLHNET  Social-Fi לעסקים אמיתיים",
        description=(
            "SLHNET מחברת בין בעלי עסקים, יוצרים ומשווקים לרשת ריפרל חכמה סביב טוקן SLH, "
            "חנויות דיגיטליות וקהילת עסקים פעילה."
        ),
        landing_url=landing_url,
        business_group_url=business_group_url,
        logs_group_hint=f"הלוגים נשלחים לקבוצת ID {logs_group}" if logs_group else "קבוצת לוגים לא הוגדרה.",
    )

