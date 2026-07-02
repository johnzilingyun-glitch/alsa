from python_service.app.utils.responses import API_RESPONSE_SCHEMA_VERSION, error_response, success_response


def test_success_response_uses_standard_envelope():
    response = success_response({"value": 1})

    assert response == {
        "success": True,
        "data": {"value": 1},
        "error": None,
        "meta": {"schema_version": API_RESPONSE_SCHEMA_VERSION},
    }


def test_error_response_uses_structured_error_with_details():
    response = error_response("BAD_INPUT", "Invalid symbol", details={"field": "symbol"})

    assert response["success"] is False
    assert response["data"] is None
    assert response["error"] == {
        "code": "BAD_INPUT",
        "message": "Invalid symbol",
        "details": {"field": "symbol"},
    }
    assert response["meta"]["schema_version"] == API_RESPONSE_SCHEMA_VERSION


def test_response_meta_allows_trace_fields():
    response = success_response(None, meta={"request_id": "req_123"})

    assert response["meta"] == {
        "schema_version": API_RESPONSE_SCHEMA_VERSION,
        "request_id": "req_123",
    }
