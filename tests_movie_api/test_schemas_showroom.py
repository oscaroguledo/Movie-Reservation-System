import pytest
from pydantic import ValidationError
from schemas.showroom import ShowroomCreate, ShowroomUpdate


class TestShowroomCreate:
    def test_accepts_valid_fields(self):
        showroom = ShowroomCreate(name="Room 1", capacity=120)

        assert showroom.name == "Room 1"
        assert showroom.capacity == 120

    def test_rejects_an_empty_name(self):
        with pytest.raises(ValidationError):
            ShowroomCreate(name="", capacity=120)

    def test_rejects_a_non_positive_capacity(self):
        with pytest.raises(ValidationError):
            ShowroomCreate(name="Room 1", capacity=0)


class TestShowroomUpdate:
    def test_all_fields_are_optional(self):
        update = ShowroomUpdate()

        assert update.name is None
        assert update.capacity is None

    def test_rejects_a_non_positive_capacity(self):
        with pytest.raises(ValidationError):
            ShowroomUpdate(capacity=-1)
