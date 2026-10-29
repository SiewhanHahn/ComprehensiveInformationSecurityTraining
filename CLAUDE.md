# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current scope

A B/S teaching demonstration for historical precipitation fusion and warning creation, approval, publication, feedback, and audit. The implemented stack is FastAPI + SQLAlchemy/MySQL 8.4 + Redis sessions, with a Vue 3/Vite frontend served by Nginx under Docker Compose. Only **RAINSTORM** is implemented end-to-end; the other seven hazard entries are framework extensions, not quantitatively validated implementations. Risk levels are educational, not official meteorological warning signals.

`AGENTS.md` contains additional repository guidance. `docs/roadmap-v1.md` records delivery stages and version choices; `docs/architecture-v1.md` explains the business design. Code/configuration establish what exists; historical deployment/test reports do not establish that a command succeeded in the current environment.

## Commands

### Docker Compose (from the repository root)

The documented deployment environment is an Ubuntu 26.04 VM. These commands use Bash; repository paths are not VM-specific.

```bash
cp .env.example .env
# Replace all seven placeholders before starting.
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api frontend mysql redis migrate seed
```

`.env` supplies `MYSQL_ROOT_PASSWORD`, `MYSQL_APP_PASSWORD`, `APP_SECRET_KEY`, and the four `DEMO_*_PASSWORD` values. Compose runs migrations, then seeds roles, demo users, and `data/sample/replay_sample.json` before starting the API. The frontend is at `http://127.0.0.1:8080`; API, MySQL, and Redis have no published host ports.

```bash
# Rebuild after source changes; source is copied into images, not bind-mounted.
docker compose build api frontend
docker compose up -d api frontend

# Explicit migration or seed reruns.
docker compose run --rm migrate
docker compose run --rm seed

# Stop while preserving database data.
docker compose down
```

Do not use `docker compose down -v`: it deletes the MySQL volume. Backup/restore details are in `docs/docker-deployment-plan.md`.

### Tests (inside the running API container)

```bash
# Unit suite.
docker compose exec -T api python -m pytest -q -p no:cacheprovider /app/tests/test_units.py

# One test.
docker compose exec -T api python -m pytest -q -p no:cacheprovider /app/tests/test_units.py::test_password_roundtrip

# Full suite, including opt-in integration and RBAC tests (Bash).
set -a; . ./.env; set +a
docker compose exec -T \
  -e RUN_INTEGRATION=1 \
  -e DEMO_ADMIN_PASSWORD -e DEMO_ANALYST_PASSWORD \
  -e DEMO_REVIEWER_PASSWORD -e DEMO_VIEWER_PASSWORD \
  api python -m pytest -q -p no:cacheprovider /app/tests
```

Integration tests require initialized MySQL/Redis and demo accounts, and exercise database-writing business flows; use a development instance. Without `RUN_INTEGRATION=1`, those tests are skipped. There is no project pytest configuration, configured lint command, or frontend test script.

### Local development

For Python on Ubuntu, install `python3-venv` if necessary. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Before running the backend locally, configure `APP_SECRET_KEY`, `DATABASE_URL` (MySQL/PyMySQL), `REDIS_URL`, and `DEMO_*_PASSWORD`, with reachable MySQL/Redis services. The Compose `.env` template alone does not configure local database/Redis URLs, and default Compose does not expose their ports. `backend/app/db.py` creates its SQLAlchemy engine at import time.

```bash
alembic upgrade head
python -m backend.app.seed --sample data/sample/replay_sample.json
python -m uvicorn backend.app.main:app --reload
```

From `frontend/`:

```bash
npm ci
npm run dev
npm run build
npm run preview
```

Vite proxies `/api` and `/health` to `localhost:8000`; run the local API there. The frontend Docker build also uses `npm ci` and `npm run build`. The only package scripts are `dev`, `build`, and `preview`.

### Offline research (from the repository root)

These commands may fetch external data on cache misses and write under `data/`; they are not read-only checks.

```bash
python backend/fusion.py --site 武汉 --lat 30.5928 --lon 114.3055 --start 2024-02-01 --end 2026-09-30 --threshold 25
python backend/pooled.py --out data/results/pooled.json
python backend/summarize.py
```

`docs/data-and-method.md` provides coverage, skill-probe, single-source, and GHCN commands and explains the experimental limitations.

## Architecture and data boundaries

**Offline research:** `backend/ingest.py` fetches Open-Meteo historical forecasts and ERA5 proxy labels into `data/cache/`; `backend/dataset.py` aggregates complete UTC days. Evaluation/fusion scripts compare strategies, and `backend/pooled.py` produces the nine-city frozen comparison. GHCN station validation is a separate path through `backend/ghcn_daily.py` and `backend/observation_eval.py`. Research outputs and the replay sample bridge research and the application; API requests do not run these download/evaluation pipelines.

**Online application:** Vue Router handles page navigation/authentication guards; `frontend/src/api.js` centralizes `/api/v1` requests, credential cookies, CSRF headers, error mapping, and a 60-second GET cache/in-flight deduplication for cities and experiment metrics. Vite proxies requests during development; production Nginx proxies to the API and provides SPA fallback.

`backend/app/main.py` assembles authentication, replay, metrics, warnings, audit, hazards, monitor, and admin user-management routers under `/api/v1`, plus request-ID/CSRF middleware and `/health`, `/health/db`, `/health/redis`. Authentication dependencies in `deps.py` resolve Redis sessions but read active users and roles from MySQL on each request; cached session roles are not authoritative. State-changing requests except login require a CSRF header matching the Redis session token.

Routers signal business errors as `HTTPException(status_code, detail="UPPER_SNAKE_CODE")`. Global handlers in `main.py` turn these and request-validation failures into the documented envelope `{"error": {"code", "message", "request_id"}}` (`422 VALIDATION_ERROR`). `frontend/src/api.js` maps `error.code` to Chinese text through `ERROR_ZH`. When you add a code, update the handler messages, `ERROR_ZH`, and `docs/interface-design-v1.md`. Tests should assert `json()["error"]["code"]`, not `detail`.

MySQL models and Alembic migrations hold authoritative users, datasets, forecast/observation records, fusion runs, warning lifecycle records, feedback, and audit logs. Redis holds sessions, not business facts. `backend/app/seed.py` imports the offline sample and initializes reference data/demo accounts; there is no general-purpose external-data import API.

Reuse `backend/app/services/replay.py::compute_replay` for daily replay and warning calculation. `services/metrics.py` reads frozen `data/results/pooled.json` relative to the working directory, caching by file mtime; Compose mounts `data/results` read-only. Run the backend/tests from the repository root so this path resolves. The monitor is a stored-data snapshot, not a live ingestion stream.

## Cross-cutting constraints

- Preserve the protocol in `docs/data-and-method.md`: fixed **24-hour lead** (`previous_day1`), complete UTC days, and 2024/2025/2026 training/validation/test years. The main comparison is ECMWF IFS against equal-weight ECMWF/GFS/ICON/GEM on identical samples.
- ERA5 is a **proxy label**, not a station measurement. GHCN observations are an independent, coverage-limited cross-check, not a replacement for the nine-city labels.
- Replay selects the latest READY datasets. Fusion requires all four models for the same city, valid time, and lead; missing models yield `PARTIAL` with no fused value, and cannot create a formal warning. Warning creation recomputes results server-side rather than trusting frontend values.
- Warning transitions enforce current state and role, prohibit self-review, and commit business changes with audit records in the same transaction. VIEWER-only users see only published warnings; audit access is admin-only and read-only through business APIs. Public warning identifiers are unguessable, not database sequence IDs.
- User management (`routers/users.py`, ADMIN only) serializes every write by locking the ADMIN `Role` row with `FOR UPDATE`, then re-reading the actor's active status and ADMIN grant before locking the target user. Keep that lock order. It prevents self-disable, self-removal of ADMIN, and removing the last active ADMIN. Requested roles must all exist in `roles`, or the transaction fails. Disabling an account takes effect on the next request; password reset intentionally leaves existing sessions valid. There is no delete or rename endpoint.
- Non-development configuration rejects an empty/default application secret. The development Compose configuration uses non-Secure cookies for loopback HTTP; production requires HTTPS and Secure cookies.
