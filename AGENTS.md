# AGENTS.md

This file provides guidance to agents (Codex / Claude Code) working in this repository.

## Current scope

A runnable B/S course project: **multi-source precipitation fusion + warning approval/publish/feedback/audit**, deployed with Docker Compose (FastAPI + Vue 3 + MySQL 8.4 + Redis 8.10.2) on an Ubuntu 26.04 VM.

Implemented:

- Backend: login/RBAC/server-side session (Redis), CSRF, warning state machine, feedback, audit log, replay, frozen metrics, hazard registry, monitor snapshot.
- Frontend: login, dashboard, monitor, replay, metrics, warnings, warning detail (closed-loop stepper), review workbench, hazard matrix, audit.
- Data: nine cities, four forecast models (ECMWF/GFS/ICON/GEM), ERA5 proxy labels, offline sample for replay.
- Tests: unit + integration (opt-in) + manual shell scripts.

Scope boundary: **1 hazard end-to-end (RAINSTORM) + 7 hazard framework entries**. See `docs/requirements-v1.md` §1.4 and `docs/roadmap-v1.md`. Do not describe the seven framework hazards as implemented or quantitatively validated.

## Commands (from the project root on the Ubuntu VM)

```bash
cp .env.example .env        # fill placeholders first
docker compose up --build -d
docker compose ps
# frontend: http://127.0.0.1:8080  (published on loopback only)
```

Rebuild after source changes:

```bash
docker compose build api frontend
docker compose up -d api frontend
```

Migrations (A 收尾已含 `0004`；B 档顺延 `0005`):

```bash
docker compose run --rm migrate
```

Tests inside the API container:

```bash
docker compose exec -T api python -m pytest -q -p no:cacheprovider /app/tests/test_units.py
set -a; . ./.env; set +a
docker compose exec -T \
  -e RUN_INTEGRATION=1 \
  -e DEMO_ADMIN_PASSWORD -e DEMO_ANALYST_PASSWORD \
  -e DEMO_REVIEWER_PASSWORD -e DEMO_VIEWER_PASSWORD \
  api python -m pytest -q -p no:cacheprovider /app/tests
```

Research scripts (may access external data on cache misses and write under `data/`):

```bash
python backend/fusion.py --site 武汉 --lat 30.5928 --lon 114.3055 --start 2024-02-01 --end 2026-09-30 --threshold 25
python backend/pooled.py --out data/results/pooled.json
python backend/summarize.py
```

`docs/data-and-method.md` lists coverage, skill-probe, single-source, and GHCN commands.

Do **not** use `docker compose down -v` (it deletes the MySQL volume).

## Architecture

- `backend/app/main.py` — FastAPI app, routers, request-id middleware, CSRF middleware, health endpoints.
- `backend/app/routers/` — `auth`, `replay`, `metrics`, `warnings`, `audit`, `hazards`, `monitor`, `users` (ADMIN-only user/role management).
- Errors: routers raise `HTTPException(detail="UPPER_SNAKE_CODE")`; global handlers in `main.py` emit `{"error": {"code", "message", "request_id"}}` for all endpoints (422 → `VALIDATION_ERROR`).
- `backend/app/services/` — `replay.compute_replay`, `metrics` (mtime-cached `pooled.json`), `audit`.
- `backend/app/models.py` — 16 tables（含 `dataset_issues`）；`backend/migrations/versions/` — Alembic `0001`~`0004`。
- `backend/app/hazards.py` — eight-hazard registry (`IMPLEMENTED` / `FRAMEWORK`).
- `frontend/src/` — Vue 3 SPA. Shared: `ui/labels.js`, `ui/useCountUp.js`, `components/{StatusBadge,EmptyState,PaginationBar,TableSkeleton,ClosedLoopStepper}.vue`.
- `frontend/src/views/` — Dashboard, Monitor, Replay, Metrics, Warnings, WarningDetail, Review, Hazards, Audit, Users, Login, NotFound.
- `frontend/src/api.js` — fetch wrapper with CSRF, Chinese error mapping, 60s GET cache for `/cities` and `/metrics/experiments*`, in-flight dedupe.

## Experimental constraints (must preserve)

- Fixed 24-hour lead; forecasts use `previous_day1`.
- ERA5 is a **proxy label**, not a station measurement.
- Years 2024/2025/2026 = train/validation/test; test evaluated once.
- Main comparison: ECMWF IFS baseline vs equal-weight ECMWF/GFS/ICON/GEM ensemble on identical samples.
- GHCN station observations are an independent, coverage-limited cross-check, not a replacement label.

## Security and repository hygiene

- Never commit `.env`, real passwords, SSH keys, `node_modules/`, `frontend/dist/`, or `data/cache/`.
- Demo passwords come from `.env` (`DEMO_*_PASSWORD`), never hard-coded.
- Audit logs are append-only through business APIs.
- Versioning: `main` holds verified versions; development happens on `phase-a` / `phase-b` / `phase-c`; see `docs/roadmap-v1.md` for tags and how to choose a version.
