# Movie Reservation System

[![CI](https://github.com/oscaroguledo/Movie-Reservation-System/actions/workflows/ci.yml/badge.svg)](https://github.com/oscaroguledo/Movie-Reservation-System/actions/workflows/ci.yml)

A backend system for browsing movies, scheduling screenings, and booking seats — built as two independently deployable services connected by an event-driven pipeline, with Postgres as the durable store, Redis as the fast path, and Kafka as the backbone between them.

## Contents

- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Features](#features)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Database migrations](#database-migrations)
- [API reference](#api-reference)
- [Testing & quality](#testing--quality)
- [Design diagrams](#design-diagrams)

## Architecture

The system is split into two services that never share a database schema or call each other's internals directly:

- **`auth-api`** — accounts, authentication, and authorization. Issues the JWTs every other service trusts.
- **`movie_api`** — the movie catalog, showrooms, screenings, and the reservation/payment lifecycle.

Each service follows the same internal shape:

```
routes/  → services/  → repository/{redis,postgresql}/
```

Reads and writes go through Redis first (the fast path a request actually waits on); every write also publishes an event to Kafka, which a dedicated **worker** process consumes to durably persist it to Postgres. Postgres is the source of truth; Redis is a cache-aside layer that can always be rebuilt from it. This means the HTTP request path never blocks on a Postgres write, while the event log gives every write a durable, replayable record.

```
Client → FastAPI route → Service (Redis read/write) → Kafka event
                                                            │
                                                            ▼
                                              Worker → Postgres (durable)
```

Both services' schemas are owned by [Alembic](#database-migrations) migrations, applied by a dedicated one-shot container before either service starts — schema is never created ad hoc by the running app in any environment.

See [Design diagrams](#design-diagrams) for the full entity-relationship and reservation-lifecycle diagrams.

## Tech stack

| Layer | Choice |
|---|---|
| API framework | FastAPI (async) |
| Durable storage | PostgreSQL, via SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Cache / fast path | Redis |
| Event bus | Kafka (`aiokafka`) |
| Auth | JWT (`PyJWT`), Argon2id password hashing |
| Testing | pytest, pytest-asyncio, pytest-cov |
| Linting | ruff |
| Containerization | Docker Compose |
| CI | GitHub Actions |

## Features

**Accounts & auth**
- Registration, login, logout with server-side token revocation (a logged-out JWT is rejected immediately, not just on expiry)
- Argon2id password hashing
- Role-based access (`admin` / `regular`), with an admin-management surface (list, update, promote, delete users) that guards against privilege escalation
- Per-IP sliding-window rate limiting on login
- Background job purging expired revoked-token records

**Catalog**
- Full CRUD on genres, movies, showrooms, and showroom seating layouts
- Movies support many-to-many genre tagging

**Screenings**
- Scheduling a movie into a showroom/time slot, with an advisory lock preventing two screenings from overlapping in the same room
- Browsing screenings by date, by movie, or by showroom
- Seat-count validation against the showroom's actual capacity

**Reservations & payments**
- Seat holds with a short, configurable TTL — expiring holds are settled lazily on read, releasing the seat automatically
- Guests can hold, view, confirm, and cancel a reservation using nothing but its ID as the credential — no account required
- A partial unique index guarantees a seat can never be double-booked while a hold or confirmed booking is active
- Payment is a separate, append-only resource (a reservation can carry a failed attempt followed by a successful retry); confirming validates the charged amount against the screening's price
- Cancelling a confirmed reservation issues an automatic refund
- Deleting a genre, movie, showroom, or screening that's still referenced anywhere is rejected (409), instead of silently failing underneath

**Admin reporting**
- All reservations across every user, filterable
- Per-screening capacity utilization
- Revenue, from actual settled payments — not just confirmed reservations

## Project structure

```
auth-api/                 # Accounts & authentication service
  routes/ services/ repository/ models/ schemas/ core/
  migrations/              # Alembic migrations (auth_api schema)
  worker.py                 # Kafka consumer → Postgres
  main.py                    # FastAPI app

movie_api/                 # Catalog, screenings, reservations service
  routes/ services/ repository/ models/ schemas/ core/
  migrations/              # Alembic migrations (movie_api schema)
  worker.py
  main.py

tests_auth_api/            # auth-api test suite
tests_movie_api/           # movie_api test suite

docker-compose.yml         # Full local stack: both services + Postgres, Redis, Kafka
.env.example                # Reference for every environment variable
```

## Getting started

### Run everything with Docker Compose (recommended)

Requires Docker Desktop (or an equivalent engine) and Docker Compose.

```bash
cp .env.example .env
# edit .env — at minimum, set a real JWT_SECRET_KEY
docker compose up -d --build
```

This brings up Postgres, Redis, and Kafka, applies both services' migrations via one-shot `auth-migrate` / `movie-migrate` containers, then starts `auth-api`, `movie_api`, and their respective workers. By default:

- `auth-api` → http://localhost:8000 (interactive docs at `/docs`)
- `movie_api` → http://localhost:8001 (interactive docs at `/docs`)

Set `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD` in `.env` to have `auth-api` bootstrap the first admin account on startup — every admin-management endpoint otherwise requires one to already exist.

Tear down with `docker compose down`, or `docker compose down -v` to also wipe the Postgres volume.

### Run a service locally, without Docker

Each service is independent and only needs its own `requirements.txt`, plus a running Postgres (and Redis/Kafka for `movie_api`):

```bash
cd auth-api   # or movie_api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000   # 8001 for movie_api
```

## Configuration

Every environment variable is documented in [`.env.example`](.env.example), with the default each service falls back to if unset. Highlights:

- `JWT_SECRET_KEY` must be identical across both services — `movie_api` verifies the tokens `auth-api` issues.
- `POSTGRES_URL` / `REDIS_URL` / `KAFKA_BOOTSTRAP_SERVERS` point at the infrastructure each service depends on; Docker Compose wires these to the service names automatically.
- Rate limits, hold TTLs, and cache TTLs are all tunable per environment without a code change.

## Database migrations

Both services use [Alembic](https://alembic.sqlalchemy.org/) — there is no `create_all()` anywhere in the running application. Each service owns its own migration history, its own Postgres schema (`auth_api` / `movie_api`), and (since both currently share one physical database in the default Compose setup) its own `alembic_version`-equivalent tracking table, so the two histories can never collide.

**In Docker**, migrations always run automatically: `auth-migrate` and `movie-migrate` are one-shot services that run `alembic upgrade head` and exit; the API and worker containers won't start until theirs has completed successfully.

**Locally**, from inside a service's own directory:

```bash
alembic upgrade head              # apply all pending migrations
alembic revision --autogenerate -m "describe the change"   # generate a new one from model changes
alembic check                     # fail if the models have drifted from the latest migration
```

CI runs `alembic upgrade head` followed by `alembic check` against a real Postgres for both services on every push, so a model change that isn't matched by a migration fails the build rather than surfacing later as a runtime error.

## API reference

Both services expose interactive OpenAPI docs at `/docs` once running. In short:

**auth-api**
`POST /register` · `POST /register/admin` · `POST /login` · `POST /logout` · `GET /me` · `GET /` (single user lookup) · `GET /users` · `PATCH /users/{id}` · `DELETE /users/{id}` · `GET /health`

**movie_api**
`GET|POST /genres`, `/movies`, `/showrooms` (+ `/{id}` variants) · `POST /showrooms/{id}/seats` · `POST|GET|DELETE /screenings` (+ browse by movie/showroom) · `POST /reservations` · `POST /reservations/{id}/confirm` · `PATCH /reservations/{id}/cancel` · `GET /reservations`, `/reservations/{id}` · `GET /reservations/{id}/payments` · `GET /admin/reservations`, `/admin/screenings/.../capacity`, `/admin/revenue` · `GET /health`

## Testing & quality

```bash
# from a service's own directory, with its venv active
pytest -v                    # auth-api: pytest.ini | movie_api: pytest-movie-api.ini (repo root)
ruff check .
```

Both suites enforce a minimum of 90% coverage (`--cov-fail-under=90`) and currently run well above it. CI (`.github/workflows/ci.yml`) runs, on every push and pull request:

- `ruff check .` across the whole repo
- The full test suite for each service, independently
- A migration-drift check for each service against a real Postgres

## Design diagrams

- [`auth system design.png`](auth%20system%20design.png) — auth-api's architecture
- [`movie system design.png`](movie%20system%20design.png) — movie_api's architecture
- [`reservation lifecycle.png`](reservation%20lifecycle.png) — the seat hold → confirm/cancel/expire state machine
