from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..db.repositories.watchlist_repo import WatchlistRepository

class WatchlistItemCreate(BaseModel):
    symbol: str
    name: str
    market: str

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

def get_repo():
    try:
        from python_service.main import get_watchlist_repo
    except ImportError:
        from main import get_watchlist_repo
    return get_watchlist_repo()

@router.post("/", status_code=201)
async def add_to_watchlist(payload: WatchlistItemCreate, repo: WatchlistRepository = Depends(get_repo)):
    return repo.create(payload.symbol, payload.name, payload.market)

@router.get("/")
async def list_watchlist(repo: WatchlistRepository = Depends(get_repo)):
    items = repo.list_items()
    return {"items": items}

@router.delete("/{symbol}")
async def remove_from_watchlist(symbol: str, market: str, repo: WatchlistRepository = Depends(get_repo)):
    repo.delete_by_symbol(symbol, market)
    return {"success": True}
