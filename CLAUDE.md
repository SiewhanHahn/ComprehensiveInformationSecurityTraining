# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current scope

A B/S teaching demonstration for historical precipitation fusion and warning creation, approval, publication, feedback, and audit. The implemented stack is FastAPI + SQLAlchemy/MySQL 8.4 + Redis sessions, with a Vue 3/Vite frontend served by Nginx under Docker Compose. Only **RAINSTORM** is implemented end-to-end; the other seven hazard entries are framework extensions, not quantitatively validated implementations. Risk levels are educational, not official meteorological warning signals.

`AGENTS.md` contains additional repository guidance. `docs/roadmap-v1.md` records delivery stages and version choices; `docs/architecture-v1.md` explains the business design. Code/configuration establish what exists; historical deployment/test reports do not establish that a command succeeded in the current environment.

## 当前进度与下一步（Phase A 手交，接手前必读）

目标：B 档之前把 A 档精细打磨完（不要屎山；A 是 B 的地基）。答辩约 2026-12 下旬。**接手第一步：`git status` 核对，别丢未提交改动。**

- 远程 `main` 已合并阶段 2 并完成 A 档 code review 收口；`phase-a` 保留历史内容。
- 阶段 2 已在隔离环境 fr02 验证（未触碰演示部署）：迁移 `0004` 由 `0003` 升到 `0004` 成功；全量 pytest **45 passed**（含 `test_fusion.py` 追溯、`test_login.py`/`test_ingest.py`）；前端审核工作台逐行意见、预警详情融合追溯、`ERROR_ZH` 兜底且后端文案优先；`npm run build` 通过；Playwright 复查 `ALL_PW_OK`。
- **剩余**：**部署演示 VM 前先问用户**；B 档从 `main` 切 `phase-b`，迁移顺延 `0005`。fr02 栈如不再用可 `docker compose -p fr02 stop`。
- **已定决策，不要再问**：登录失败统一 `INVALID_CREDENTIALS`（锁定期间也一样），仅密码正确才 `ACCOUNT_DISABLED`；导入质量问题用新表 `dataset_issues`（迁移 0004）；错误文案以后端 `message` 为准、前端 ERROR_ZH 只兜底；前端引入 Vitest；对外 HTTP API 只增不改（`WarningOut` 不变，详情用 `WarningDetailOut` 子类）。

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

Test suite layout: `test_units.py` (no services needed), `test_integration.py`, `test_rbac_matrix.py`, `test_state_machine.py`, `test_user_management.py`, `test_login.py`, `test_ingest.py`; `tests/manual_round{2,3,4}.sh` are manual shell scripts. `tests/conftest.py` provides the shared fixtures `new_client`, `login`, `make_warning`, `created_warnings`, `created_users`, and auto-skips `@pytest.mark.integration` tests unless `RUN_INTEGRATION=1`.

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

Routers signal business errors as `HTTPException(status_code, detail="UPPER_SNAKE_CODE")`. Global handlers in `main.py` turn these and request-validation failures into the documented envelope `{"error": {"code", "message", "request_id"}}` (`422 VALIDATION_ERROR`). `backend/app/errors.py` `MESSAGES` is the authoritative code→中文 message map; `frontend/src/api.js` maps `error.code` through `ERROR_ZH` as a fallback. When you add a code, add it to `errors.py` `MESSAGES`, `ERROR_ZH`, and `docs/interface-design-v1.md`. Tests should assert `json()["error"]["code"]`, not `detail`.

MySQL models and Alembic migrations hold authoritative users, datasets, forecast/observation records, fusion runs, warning lifecycle records, feedback, and audit logs. Redis holds sessions, not business facts. `backend/app/seed.py` imports the offline sample and initializes reference data/demo accounts; there is no general-purpose external-data import API.

`backend/app/models.py` defines **16 tables** (including `dataset_issues`); migrations in `backend/migrations/versions/` run `0001`→`0004` (`0004_dataset_issues` adds the issue table — use it as the pattern for a new migration; the next Phase B migration is `0005`).

**Business core — `backend/app/services/`** (routers stay thin: params, auth deps, serialization):
- `warnings.py` — warning state machine. `Transition` dataclass plus `SUBMIT`/`APPROVE`/`REJECT`/`PUBLISH`/`WITHDRAW` encode allowed source states, target, timestamps and audit action; `is_viewer_only` drives visibility. `create_warning` recomputes via `compute_replay` and persists `FusionRun` + `FusionInput` + `WarningResult`; `to_out` / `to_detail_out` serialize. Write functions only `flush()` — the router `commit()`s, so business rows and the audit row share one transaction.
- `audit.py` — `add_audit` / `AuditContext` (bound to request_id + client IP). Append-only, same transaction as the business write.
- `ingest.py` — offline-sample import validation (unknown city/model, bad date, duplicate, out-of-order, invalid value). Each problem is written to `dataset_issues` and skipped; the dataset's `quality_status` becomes `PARTIAL`; idempotent by dataset version.
- `replay.py::compute_replay` — shared daily replay and warning calculation. `metrics.py` reads frozen `data/results/pooled.json` relative to the working directory, caching by file mtime; Compose mounts `data/results` read-only. Run backend/tests from the repository root so this path resolves. The monitor is a stored-data snapshot, not a live ingestion stream.
- `clock.py` — single `utcnow()` (naive UTC, matches `DATETIME(6)`); `security.py` — Argon2 hashing, unguessable 26-char `public_id`, CSRF/session tokens.

**Fusion traceability (FR-04):** `GET /warnings/{public_id}` returns `WarningDetailOut`, a **subclass** of `WarningOut` (additive only), adding `models` (four model inputs), `baseline_mm`, `proxy_label_mm`, `dataset_version`. `WarningOut` stays unchanged for list/create.

**Auth hardening (FR-01):** `config.py` carries both session **idle TTL** and **absolute TTL**; Redis enforces a **per-IP login-failure limit** (`login:fail:<ip>` → `429 LOGIN_RATE_LIMITED`) alongside per-account lockout. Login always returns uniform `INVALID_CREDENTIALS` (even while locked); `ACCOUNT_DISABLED` only after a correct password. These are locked decisions (see the handoff section) — do not re-litigate.

Research helper scripts: `backend/make_sample.py` regenerates `data/sample/replay_sample.json`; `backend/coverage_report.py` summarizes data coverage.

## Cross-cutting constraints

- Preserve the protocol in `docs/data-and-method.md`: fixed **24-hour lead** (`previous_day1`), complete UTC days, and 2024/2025/2026 training/validation/test years. The main comparison is ECMWF IFS against equal-weight ECMWF/GFS/ICON/GEM on identical samples.
- ERA5 is a **proxy label**, not a station measurement. GHCN observations are an independent, coverage-limited cross-check, not a replacement for the nine-city labels.
- Replay selects the latest non-`FAILED` dataset (`PARTIAL` datasets are still usable; missing models yield `PARTIAL`). Fusion requires all four models for the same city, valid time, and lead; missing models yield `PARTIAL` with no fused value, and cannot create a formal warning. Warning creation recomputes results server-side rather than trusting frontend values.
- Warning transitions enforce current state and role, prohibit self-review, and commit business changes with audit records in the same transaction. VIEWER-only users see only published warnings; audit access is admin-only and read-only through business APIs. Public warning identifiers are unguessable, not database sequence IDs.
- User management (`routers/users.py`, ADMIN only) serializes every write by locking the ADMIN `Role` row with `FOR UPDATE`, then re-reading the actor's active status and ADMIN grant before locking the target user. Keep that lock order. It prevents self-disable, self-removal of ADMIN, and removing the last active ADMIN. Requested roles must all exist in `roles`, or the transaction fails. Disabling an account takes effect on the next request; password reset intentionally leaves existing sessions valid. There is no delete or rename endpoint.
- Non-development configuration rejects an empty/default application secret. The development Compose configuration uses non-Secure cookies for loopback HTTP; production requires HTTPS and Secure cookies.
