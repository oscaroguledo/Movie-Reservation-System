import runpy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import worker
from core.events import Event, EventType
from sqlalchemy.exc import IntegrityError, OperationalError


def make_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    return session


class TestGenreHandlers:
    async def test_created_persists_a_new_genre(self):
        session = make_session()

        await worker.handle_genre_created(session, {"id": str(uuid4()), "name": "Action"})

        session.commit.assert_awaited_once()

    async def test_created_tolerates_redelivery_of_an_already_persisted_genre(self):
        session = make_session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        genre_id = uuid4()
        session.get.return_value = MagicMock(name="Action")
        session.get.return_value.name = "Action"

        await worker.handle_genre_created(session, {"id": str(genre_id), "name": "Action"})

        session.rollback.assert_awaited()

    async def test_updated_creates_when_the_row_does_not_exist_yet(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_genre_updated(session, {"id": str(uuid4()), "name": "Comedy"})

        assert session.add.called

    async def test_deleted_calls_delete(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_genre_deleted(session, {"id": str(uuid4())})

        session.get.assert_awaited()


class TestMovieHandlers:
    async def test_created_persists_a_new_movie_with_genres(self):
        session = make_session()

        await worker.handle_movie_created(
            session,
            {
                "id": str(uuid4()),
                "title": "Inception",
                "description": "x",
                "poster_image_url": "x.jpg",
                "release_date": "2010-07-16",
                "duration_minutes": 148,
                "genre_ids": [str(uuid4())],
            },
        )

        session.commit.assert_awaited_once()

    async def test_updated_creates_when_missing(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_movie_updated(
            session,
            {
                "id": str(uuid4()),
                "title": "Inception",
                "description": "x",
                "poster_image_url": "x.jpg",
                "release_date": None,
                "duration_minutes": None,
                "genre_ids": [],
            },
        )

        assert session.add.called

    async def test_deleted_calls_delete(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_movie_deleted(session, {"id": str(uuid4())})

        session.get.assert_awaited()


class TestShowroomHandlers:
    async def test_created_persists_a_new_showroom(self):
        session = make_session()

        await worker.handle_showroom_created(
            session, {"id": str(uuid4()), "name": "Room 1", "capacity": 100}
        )

        session.commit.assert_awaited_once()

    async def test_updated_creates_when_missing(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_showroom_updated(
            session, {"id": str(uuid4()), "name": "Room 1", "capacity": 100}
        )

        assert session.add.called

    async def test_deleted_calls_delete(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_showroom_deleted(session, {"id": str(uuid4())})

        session.get.assert_awaited()

    async def test_seats_created_persists_all_seats(self):
        session = make_session()
        showroom_id = str(uuid4())

        await worker.handle_showroom_seats_created(
            session,
            {
                "showroom_id": showroom_id,
                "seats": [
                    {"id": str(uuid4()), "showroom_id": showroom_id, "row": "A", "number": 1}
                ],
            },
        )

        session.add_all.assert_called_once()

    async def test_seats_created_tolerates_redelivery(self):
        session = make_session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        showroom_id = str(uuid4())

        await worker.handle_showroom_seats_created(
            session,
            {
                "showroom_id": showroom_id,
                "seats": [
                    {"id": str(uuid4()), "showroom_id": showroom_id, "row": "A", "number": 1}
                ],
            },
        )

        session.rollback.assert_awaited()


class TestScreeningHandlers:
    async def test_scheduled_persists_the_showtime_and_junction_row(self):
        session = make_session()

        await worker.handle_screening_scheduled(
            session,
            {
                "showtime_id": str(uuid4()),
                "movie_id": str(uuid4()),
                "showroom_id": str(uuid4()),
                "start_time": "2026-09-01T18:00:00+00:00",
                "end_time": "2026-09-01T20:00:00+00:00",
                "price": "12.50",
            },
        )

        session.commit.assert_awaited_once()

    async def test_deleted_calls_delete(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_screening_deleted(
            session,
            {"movie_id": str(uuid4()), "showroom_id": str(uuid4()), "showtime_id": str(uuid4())},
        )

        session.get.assert_awaited()


def make_reservation_payload(**overrides):
    payload = {
        "id": str(uuid4()),
        "user_id": str(uuid4()),
        "user_type": "regular",
        "movie_id": str(uuid4()),
        "showroom_id": str(uuid4()),
        "showtime_id": str(uuid4()),
        "showroom_seat_id": str(uuid4()),
        "status": "pending",
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    }
    payload.update(overrides)
    return payload


class TestReservationHandlers:
    async def test_created_persists_a_new_reservation(self):
        session = make_session()

        await worker.handle_reservation_created(session, make_reservation_payload())

        session.commit.assert_awaited_once()

    async def test_created_with_no_user_id_is_a_guest_reservation(self):
        session = make_session()

        await worker.handle_reservation_created(
            session, make_reservation_payload(user_id=None, user_type="guest")
        )

        session.commit.assert_awaited_once()

    async def test_status_changed_updates_an_existing_reservation(self):
        session = make_session()
        session.get.return_value = MagicMock()

        await worker.handle_reservation_status_changed(
            session, make_reservation_payload(status="confirmed", expires_at=None)
        )

        session.commit.assert_awaited_once()

    async def test_status_changed_creates_when_the_create_event_has_not_landed_yet(self):
        session = make_session()
        session.get.return_value = None

        await worker.handle_reservation_status_changed(
            session, make_reservation_payload(status="confirmed", expires_at=None)
        )

        assert session.add.called


def make_payment_payload(**overrides):
    payload = {
        "id": str(uuid4()),
        "reservation_id": str(uuid4()),
        "amount": "12.50",
        "status": "succeeded",
        "provider_reference": None,
    }
    payload.update(overrides)
    return payload


class TestPaymentHandlers:
    async def test_recorded_persists_a_new_payment(self):
        session = make_session()

        await worker.handle_payment_recorded(session, make_payment_payload())

        session.commit.assert_awaited_once()

    async def test_recorded_tolerates_redelivery_of_an_already_persisted_payment(self):
        session = make_session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        session.get.return_value = MagicMock()

        await worker.handle_payment_recorded(session, make_payment_payload())

        session.rollback.assert_awaited()


class TestHandleEvent:
    async def test_unknown_event_type_is_skipped_and_committed(self):
        event = MagicMock(event_type="unknown", event_id="x", payload={})

        assert await worker.handle_event(event) is True

    async def test_operational_error_is_not_committed(self):
        event = Event(
            event_type=EventType.GENRE_CREATED, payload={"id": str(uuid4()), "name": "x"}
        )
        error = OperationalError("s", {}, Exception())

        with patch("worker.async_session_factory", side_effect=error):
            assert await worker.handle_event(event) is False

    async def test_unexpected_error_is_still_committed(self):
        event = Event(event_type=EventType.GENRE_CREATED, payload={"bad": "payload"})

        assert await worker.handle_event(event) is True


class TestMain:
    async def test_consumes_and_commits_handled_events(self):
        event = Event(event_type=EventType.GENRE_DELETED, payload={"id": str(uuid4())})

        with patch("worker.KafkaConsumer") as mock_cls:
            instance = AsyncMock()
            instance.__aenter__.return_value = instance

            async def messages():
                yield event

            instance.messages = messages
            mock_cls.return_value = instance

            with patch("worker.handle_event", new=AsyncMock(return_value=True)) as mock_handle:
                await worker.main()

            mock_handle.assert_awaited_once_with(event)
            instance.commit.assert_awaited_once()


def test_entrypoint_runs_main_via_asyncio_run():
    with patch("asyncio.run", side_effect=lambda coro: coro.close()) as mock_run:
        runpy.run_module("worker", run_name="__main__")

    mock_run.assert_called_once()
