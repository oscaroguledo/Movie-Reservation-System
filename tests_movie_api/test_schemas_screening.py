from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from schemas.screening import ScreeningCreate


def make_screening_create(**overrides):
    defaults = dict(
        movie_id=uuid4(),
        showroom_id=uuid4(),
        start_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
        price="12.50",
    )
    defaults.update(overrides)
    return ScreeningCreate(**defaults)


class TestScreeningCreate:
    def test_accepts_valid_fields(self):
        screening = make_screening_create()

        assert screening.price == 12.50

    def test_rejects_end_time_before_start_time(self):
        with pytest.raises(ValidationError, match="end_time must be after start_time"):
            make_screening_create(
                start_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc),
            )

    def test_rejects_end_time_equal_to_start_time(self):
        same_time = datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)

        with pytest.raises(ValidationError, match="end_time must be after start_time"):
            make_screening_create(start_time=same_time, end_time=same_time)

    def test_rejects_a_non_positive_price(self):
        with pytest.raises(ValidationError):
            make_screening_create(price="0")
