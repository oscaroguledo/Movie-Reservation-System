from uuid import uuid4

import pytest
from pydantic import ValidationError
from schemas.reservation import ReservationCreate


class TestReservationCreate:
    def test_accepts_valid_fields(self):
        seat_id = uuid4()

        reservation = ReservationCreate(
            movie_id=uuid4(),
            showroom_id=uuid4(),
            showtime_id=uuid4(),
            showroom_seat_ids=[seat_id],
        )

        assert reservation.showroom_seat_ids == [seat_id]

    def test_rejects_an_empty_seat_list(self):
        with pytest.raises(ValidationError):
            ReservationCreate(
                movie_id=uuid4(), showroom_id=uuid4(), showtime_id=uuid4(), showroom_seat_ids=[]
            )
