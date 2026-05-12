from typing import Any, Optional
from pydantic import BaseModel

class StandardResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[dict] = None

def success_response(data: Any = None) -> dict:
    return {
        "success": True,
        "data": data
    }

def error_response(code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message
        }
    }
