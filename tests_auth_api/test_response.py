from core.response import APIResponse, EResponse, SResponse


def test_sresponse_defaults():
    response = SResponse()

    assert response.success is True
    assert response.message == "OK"
    assert response.status == 200
    assert response.data is None


def test_sresponse_with_data_and_overrides():
    response = SResponse(data={"id": 1}, message="Created", status=201)

    assert response.success is True
    assert response.message == "Created"
    assert response.status == 201
    assert response.data == {"id": 1}


def test_eresponse_defaults():
    response = EResponse()

    assert response.success is False
    assert response.message == "Error"
    assert response.status == 400
    assert response.data is None


def test_eresponse_with_overrides():
    response = EResponse(message="Not found", status=404, data={"field": "email"})

    assert response.success is False
    assert response.message == "Not found"
    assert response.status == 404
    assert response.data == {"field": "email"}


def test_apiresponse_is_generic_pydantic_model():
    response: APIResponse[int] = APIResponse(success=True, message="OK", status=200, data=42)

    assert response.model_dump() == {
        "success": True,
        "message": "OK",
        "status": 200,
        "data": 42,
    }
