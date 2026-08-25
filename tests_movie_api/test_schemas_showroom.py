import pytest
from pydantic import ValidationError
from schemas.showroom import ShowroomCreate, ShowroomSeatBulkCreate, ShowroomUpdate


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


class TestShowroomSeatBulkCreate:
    def test_accepts_valid_fields(self):
        bulk = ShowroomSeatBulkCreate(rows=["A", "B"], seats_per_row=10)

        assert bulk.rows == ["A", "B"]
        assert bulk.seats_per_row == 10

    def test_rejects_an_empty_rows_list(self):
        with pytest.raises(ValidationError):
            ShowroomSeatBulkCreate(rows=[], seats_per_row=10)

    def test_rejects_a_non_positive_seats_per_row(self):
        with pytest.raises(ValidationError):
            ShowroomSeatBulkCreate(rows=["A"], seats_per_row=0)

    def test_rejects_an_overly_long_row_label(self):
        with pytest.raises(ValidationError):
            ShowroomSeatBulkCreate(rows=["TOOLONG"], seats_per_row=10)
