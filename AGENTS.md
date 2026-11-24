# Repository Guidelines

This course project demonstrates multi-source precipitation fusion and a warning workflow from approval through publication, feedback, and audit. `RAINSTORM` has an end-to-end workflow and a frozen quantitative experiment. `TYPHOON` and `SNOW_DISASTER` replay source-backed historical cases and reuse that warning workflow; five entries are not yet implemented.

## Project Structure & Module Organization

- `backend/app/` contains the FastAPI app, with endpoints in `routers/`, business logic in `services/`, and the worker in `scheduler.py`. Alembic revisions live in `backend/migrations/versions/`; research scripts live directly under `backend/`.
- `frontend/src/` contains the Vue 3 app: routed pages in `views/`, reusable UI in `components/`, and map assets in `assets/`.
- `tests/` holds Python, frontend, and manual checks. `data/sample/` contains offline replay input, `data/results/` holds frozen metrics, and `docs/` documents architecture, API contracts, and deployment.

## Build, Test, and Development Commands

- Copy `.env.example` to `.env` and replace the placeholders. From the root, run `docker compose up --build -d` to build and start the stack, then `docker compose ps` to check it. Open `http://127.0.0.1:8080`.
- Run `docker compose run --rm migrate` to apply pending migrations. For a standalone API, configure MySQL and Redis as described in `CLAUDE.md`, then run `python -m uvicorn backend.app.main:app --reload`.
- In `frontend/`, run `npm ci` to install locked dependencies, `npm run dev` for Vite (proxies API calls to `localhost:8000`), and `npm run build` for production assets.

## Coding Style & Naming Conventions

Use four spaces and `snake_case` in Python. Use two spaces in Vue/JavaScript, `PascalCase.vue` for components, and `camelCase` for JavaScript identifiers. Match surrounding code; no lint or formatter command is configured.

## Testing Guidelines

- Run backend units with `docker compose exec -T api python -m pytest -q -p no:cacheprovider /app/tests/test_units.py`. Name Python tests `test_*.py` and functions `test_*`.
- Mark service-dependent pytest tests `integration`. Enable them with `RUN_INTEGRATION=1` against development MySQL/Redis with seeded demo accounts; see `CLAUDE.md` for the full command. No coverage threshold is configured.
- After installing frontend dependencies, run `node --test tests/test_frontend_review.mjs` from the root for Vue regression checks.

## Commit & Pull Request Guidelines

Use imperative subjects such as `fix(backend): ...`, `docs: ...`, or `test: ...`. In PRs, explain the change, link relevant issues, list checks run, and flag migrations or API changes. Include screenshots for visible UI changes.

## Checkpoint Delivery

Push each accepted sub-item once to `origin/integration/phase-c` with its checkpoint tag if present. Verify the remote refs; do not force-push or merge `main` automatically. Before the final delivery push, notify the project owner to choose the code license.

## Security & Data Hygiene

Keep `.env`, credentials, `node_modules/`, `frontend/dist/`, and `data/cache/` out of Git. Avoid `docker compose down -v`; it deletes the MySQL volume. Preserve the fixed 24-hour forecast lead and treat ERA5 as a proxy label, not station truth. Keep the 2024/2025/2026 train/validation/test split; see `docs/data-and-method.md`.
