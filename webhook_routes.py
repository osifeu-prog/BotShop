from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/telegram")
async def telegram_webhook(request: Request):
    # This endpoint is kept for future PTB webhook integration
    update = await request.json()
    # you can log / enqueue the update here
    return {"ok": True}
