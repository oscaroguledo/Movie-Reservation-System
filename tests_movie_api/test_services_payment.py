from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from repository.payment.redis import PaymentRedisRepository
from services.payment import PaymentService


def make_service():
    session = AsyncMock()
    session.get.return_value = None
    session.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))
    producer = AsyncMock()
    service = PaymentService(
        session=session, redis_repo=PaymentRedisRepository(), producer=producer
    )
    return service, producer, session


def uuid_from(id_str: str) -> UUID:
    return UUID(id_str)


class TestCharge:
    async def test_matching_amount_succeeds_and_publishes_an_event(self, fake_redis):
        service, producer, _ = make_service()
        reservation_id = uuid4()

        payment = await service.charge(reservation_id, Decimal("12.50"), Decimal("12.50"))

        assert payment["status"] == "succeeded"
        assert payment["reservation_id"] == str(reservation_id)
        producer.publish.assert_awaited_once()
        topic, event = producer.publish.await_args.args
        assert topic == "movies"
        assert event.payload["status"] == "succeeded"

    async def test_mismatched_amount_is_recorded_as_failed(self, fake_redis):
        service, _, _ = make_service()

        payment = await service.charge(uuid4(), Decimal("1.00"), Decimal("12.50"))

        assert payment["status"] == "failed"

    async def test_records_the_provider_reference(self, fake_redis):
        service, _, _ = make_service()

        payment = await service.charge(uuid4(), Decimal("12.50"), Decimal("12.50"), "tok_visa")

        assert payment["provider_reference"] == "tok_visa"


class TestRefund:
    async def test_records_a_refund(self, fake_redis):
        service, producer, _ = make_service()
        reservation_id = uuid4()

        payment = await service.refund(reservation_id, Decimal("12.50"))

        assert payment["status"] == "refunded"
        assert payment["reservation_id"] == str(reservation_id)
        producer.publish.assert_awaited_once()


class TestGet:
    async def test_returns_none_when_not_found(self, fake_redis):
        service, _, _ = make_service()

        assert await service.get(uuid4()) is None

    async def test_returns_the_cached_payment(self, fake_redis):
        service, _, _ = make_service()
        payment = await service.charge(uuid4(), Decimal("12.50"), Decimal("12.50"))

        again = await service.get(uuid_from(payment["id"]))

        assert again == payment

    async def test_falls_back_to_postgres_on_cache_miss(self, fake_redis):
        service, _, session = make_service()
        payment_id = uuid4()
        row = MagicMock()
        row.to_dict.return_value = {
            "id": str(payment_id),
            "reservation_id": str(uuid4()),
            "amount": 12.5,
            "status": "succeeded",
            "provider_reference": None,
            "created_at": None,
            "updated_at": None,
        }
        session.get.return_value = row

        payment = await service.get(payment_id)

        assert payment["status"] == "succeeded"
        assert await service.redis_repo.get(payment_id) == payment


class TestListForReservation:
    async def test_returns_empty_list_when_none_recorded(self, fake_redis):
        service, _, _ = make_service()

        assert await service.list_for_reservation(uuid4()) == []

    async def test_returns_payments_in_creation_order(self, fake_redis):
        service, _, _ = make_service()
        reservation_id = uuid4()
        first = await service.charge(reservation_id, Decimal("12.50"), Decimal("12.50"))
        second = await service.refund(reservation_id, Decimal("12.50"))

        payments = await service.list_for_reservation(reservation_id)

        assert [p["id"] for p in payments] == [first["id"], second["id"]]
