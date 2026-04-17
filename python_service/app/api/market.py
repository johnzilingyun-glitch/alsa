from fastapi import APIRouter

router = APIRouter(prefix="/market", tags=["market"])

@router.get("/status")
async def market_status():
    return {"status": "ok", "sources": ["akshare", "sina", "yahoo"]}
