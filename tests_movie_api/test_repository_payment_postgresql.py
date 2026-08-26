from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from models import PaymentStatus
from repository.payment.postgresql import PaymentPostgresRepository
from sqlalchemy.exc import IntegrityError, OperationalError


def make_repo():
    session = AsyncMock()
    session.add = MagicMock()
    return PaymentPostgresRepository(session), session


class TestGet:
    async def test_returns_the_payment(self, fake_redis):
        repo, session = make_repo()
        payment = MagicMock()
        session.get.return_value = payment

        assert await repo.get(uuid4()) is payment


class TestListForReservation:
    async def test_returns_payments_for_the_reservation(self, fake_redis):
        repo, session = make_repo()
        session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

        payments = await repo.list_for_reservation(uuid4())

        assert payments == []


class TestCreate:
    async def test_creates_the_payment(self, fake_redis):
        repo, session = make_repo()

        payment = await repo.create(
            uuid4(), uuid4(), Decimal("12.50"), PaymentStatus.SUCCEEDED, "tok_visa"
        )

        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.amount == Decimal("12.50")
        session.commit.assert_awaited_once()

    async def test_integrity_error_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = IntegrityError("s", {}, Exception())

        with pytest.raises(IntegrityError):
            await repo.create(
                uuid4(), uuid4(), Decimal("12.50"), PaymentStatus.SUCCEEDED, None
            )

    async def test_db_outage_rolls_back_and_reraises(self, fake_redis):
        repo, session = make_repo()
        session.commit.side_effect = OperationalError("s", {}, Exception())

        with pytest.raises(OperationalError):
            await repo.create(
                uuid4(), uuid4(), Decimal("12.50"), PaymentStatus.SUCCEEDED, None
            )
