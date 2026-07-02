from typing import Any, Optional
from pydantic import BaseModel, Field

API_RESPONSE_SCHEMA_VERSION = "2026-07-02"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ResponseMeta(BaseModel):
    schema_version: str = API_RESPONSE_SCHEMA_VERSION

class StandardResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[ErrorBody] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

def success_response(data: Any = None, *, meta: Optional[dict] = None) -> dict:
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": _response_meta(meta),
    }

def error_response(code: str, message: str, *, details: Any = None, meta: Optional[dict] = None) -> dict:
    payload = {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
        "meta": _response_meta(meta),
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def _response_meta(extra: Optional[dict] = None) -> dict:
    base = {"schema_version": API_RESPONSE_SCHEMA_VERSION}
    if extra:
        base.update(extra)
    return base
