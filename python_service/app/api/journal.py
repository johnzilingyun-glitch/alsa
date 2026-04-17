from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from ..db.repositories.journal_repo import JournalRepository

class JournalEntryCreate(BaseModel):
    symbol: str
    market: str
    action: str
    price_at_decision: float
    confidence: int
    reasoning: Optional[str] = None
    analysis_id: Optional[str] = None

router = APIRouter(prefix="/journal", tags=["journal"])

def get_repo():
    from ...main import get_journal_repo
    return get_journal_repo()

@router.post("/", status_code=201)
async def add_to_journal(payload: JournalEntryCreate, repo: JournalRepository = Depends(get_repo)):
    return repo.create(**payload.model_dump())

@router.get("/pending-reviews")
async def pending_reviews(repo: JournalRepository = Depends(get_repo)):
    items = repo.pending_reviews()
    return {"items": items}

@router.get("/")
async def list_journal(repo: JournalRepository = Depends(get_repo)):
    return {"items": repo.list_entries()}
