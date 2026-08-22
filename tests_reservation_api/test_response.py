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


def test_eresponse_with_custom_message_status_and_data():
    response = EResponse(message="Not Found", status=404, data={"field": "id"})

    assert response.success is False
    assert response.message == "Not Found"
    assert response.status == 404
    assert response.data == {"field": "id"}


def test_apiresponse_serializes_as_expected():
    response = APIResponse[int](success=True, message="OK", status=200, data=5)

    assert response.model_dump() == {
        "success": True,
        "message": "OK",
        "status": 200,
        "data": 5,
    }
