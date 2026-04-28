from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from ..services.brain_manager import brain_manager

router = APIRouter(prefix="/brain", tags=["brain"])

class EvolutionInstructionsUpdate(BaseModel):
    instructions: str

@router.get("/context")
async def get_brain_context(user_id: str = "default", query: Optional[str] = None):
    """
    Retrieve long-term memory facts and evolved system instructions.
    """
    try:
        context = brain_manager.get_brain_context(user_id, query)
        return {"success": True, "data": context}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/feedback")
async def process_brain_feedback(payload: Dict[str, Any]):
    """
    Record user feedback to evolve prompts and store long-term facts.
    """
    try:
        brain_manager.process_feedback(payload)
        return {"success": True, "message": "Feedback processed and brain evolved."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/evolution/instructions")
async def get_evolution_instructions():
    """
    Query the current evolved instructions.
    """
    try:
        instructions = brain_manager.get_evolved_instructions()
        return {"success": True, "data": instructions}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.put("/evolution/instructions")
async def update_evolution_instructions(payload: EvolutionInstructionsUpdate):
    """
    Manually update the evolved instructions.
    """
    try:
        brain_manager.update_instructions(payload.instructions)
        return {"success": True, "message": "Instructions updated successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}
