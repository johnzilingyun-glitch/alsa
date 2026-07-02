from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from ..services.brain_manager import brain_manager
from ..utils.responses import error_response, success_response

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
        return success_response(context)
    except Exception as e:
        return error_response("BRAIN_CONTEXT_FAILED", str(e))

class FeedbackPayload(BaseModel):
    role: Optional[str] = None
    user_id: str = "default"
    feedback: str
    context: Optional[str] = None

@router.post("/feedback")
async def process_brain_feedback(payload: FeedbackPayload):
    """
    Record user feedback to evolve prompts and store long-term facts.
    """
    try:
        brain_manager.process_feedback(payload.model_dump())
        return success_response({"message": "Feedback processed and brain evolved."})
    except Exception as e:
        return error_response("BRAIN_FEEDBACK_FAILED", str(e))

@router.get("/evolution/instructions")
async def get_evolution_instructions():
    """
    Query the current evolved instructions.
    """
    try:
        instructions = brain_manager.get_evolved_instructions()
        return success_response(instructions)
    except Exception as e:
        return error_response("BRAIN_INSTRUCTIONS_FAILED", str(e))

@router.get("/evolution/history")
async def get_evolution_history(role: str):
    """
    Retrieve evolution history (genes/mutations) for a specific role.
    """
    try:
        history = brain_manager.get_evolution_history(role)
        return success_response(history)
    except Exception as e:
        return error_response("BRAIN_HISTORY_FAILED", str(e))

@router.put("/evolution/instructions")
async def update_evolution_instructions(payload: EvolutionInstructionsUpdate):
    """
    Manually update the evolved instructions.
    """
    try:
        brain_manager.update_instructions(payload.instructions)
        return success_response({"message": "Instructions updated successfully."})
    except Exception as e:
        return error_response("BRAIN_UPDATE_FAILED", str(e))
