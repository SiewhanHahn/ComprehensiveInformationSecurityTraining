# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current scope

A B/S teaching demonstration for historical precipitation fusion and warning creation, approval, publication, feedback, and audit. The implemented stack is FastAPI + SQLAlchemy/MySQL 8.4 + Redis sessions, with a Vue 3/Vite frontend served by Nginx under Docker Compose. Only **RAINSTORM** is implemented end-to-end; the other seven hazard entries are framework extensions, not quantitatively validated implementations. Risk levels are educational, not official meteorological warning signals.

`AGENTS.md` contains additional repository guidance (the Codex-facing twin; this `CLAUDE.md` is canonical for Claude Code — they overlap by design, do not consolidate). `docs/roadmap-v1.md` records delivery stages and version choices; `docs/architecture-v1.md` explains the business design. Also in `docs/`: `requirements-v1.md` (SRS, FR/SEC), `database-design-v1.md` (16-table schema), `traceability-v1.md` (FR→实现→测试矩阵), `test-report-v1.md` (verified evidence), `backend-review-v1.md` (backend review findings + the contracts a frontend refactor must respect), `user-guide-v1.md` (demo script). `docs/docker-deployment-plan.md` §1 is stale (claims no Dockerfile/Compose exist). Code/configuration establish what exists; historical deployment/test reports do not establish that a command succeeded in the current environment.

`report/` (untracked) holds course-report deliverable templates (.docx/.pptx); `info.txt` (tracked) records the course assessment discussion (deliverables: runnable source + report + quantified improvement, no video). Decide whether to gitignore `report/` or commit the templates.

## 当前进度与下一步（Phase A 手交，接手前必读）

目标：B 档之前把 A 档精细打磨完（不要屎山；A 是 B 的地基）。答辩约 2026-12 下旬。**接手第一步：`git status` 核对，别丢未提交改动。**

- 远程 `main` 已合并阶段 2、完成 A 档收口并推送（最新 tag `v0.2.5-phase-a`，其后有 `6956c47` dark command-center 前端重设计、`1065dc2` Dockerfile 阿里云镜像源、`c3bd0bf` CLAUDE.md 刷新）。
- 演示 VM 已于 2026-11-02 更新到 `main` 并验证（暗色 UI、`THRESHOLD_NOT_REACHED`、迁移 `0004`、单元测试通过）；部署步骤见 `docs/docker-deployment-plan.md`，`.env` 只留在 VM。
- **B 档在 `phase-b` 分支进行，分两刀。两刀均已完成并验证**（`docs/test-report-v1.md` §6.13–§6.16）：迁移 `0005`（`warning_subscriptions` / `notifications` / `response_tasks`）、订阅、站内通知、通知中心页、独立 `scheduler` 容器；响应任务自动派发、处置时限、接单/完成、超时升级、任务看板与详情页任务卡。fr02 全量 pytest **75 passed**；两刀各自经过一轮多角度 code review 收口（§6.14、§6.16），另有一轮 `backend/` 全量审查收口（§6.17，清单与前端契约见 `docs/backend-review-v1.md`）。**第二刀没有新迁移**。
- **`backend/` 全量审查（§6.17）的几条现状**：`services/tasks.py` 的 ack/complete 与 escalate 都改成带期望状态的条件 UPDATE；`routers/monitor.py` 的完整性口径与回放对齐（lead/mode/非空/is_complete）；`main.py` 有兜底 500 处理器（`INTERNAL_ERROR`）；per-IP 登录限速**不再被成功登录清零**；`fusion.py` 的最优规则按训练年选择。**给新部署前必读**：`seed.py` 曾因漏导入 `Decimal` 导致任何重建的部署起不来，现已修复并有看门狗测试。
- **剩余**：B 档验收 → 合并 `main` → 打 `v0.3.0-phase-b`；**更新演示 VM 前先问用户**（B 档部署要多起一个 `scheduler` 服务）。fr02 栈如不再用可 `docker compose -p fr02 stop`。课程报告/PPT 尚未动工（模板在 `report/`）。
- **已定决策，不要再问**：登录失败统一 `INVALID_CREDENTIALS`（锁定期间也一样），仅密码正确才 `ACCOUNT_DISABLED`；导入质量问题用新表 `dataset_issues`（迁移 0004）；错误文案以后端 `message` 为准、前端 ERROR_ZH 只兜底；前端引入 Vitest（尚未落地——`package.json` 仅 `dev`/`build`/`preview`，无测试依赖/脚本）；对外 HTTP API 只增不改（`WarningOut` 不变，详情用 `WarningDetailOut` 子类）；定时扫描用独立 `scheduler` 容器而非进程内调度，且不引入 APScheduler/Celery；订阅的「不限」用哨兵值 `'*'`/`''` 而非 NULL；**前端不对未读数做定时轮询**——`/notifications/unread-count` 走 `get_current_user` 会刷新会话空闲 TTL，轮询等于让会话永不过期，只在挂载/切页/标签页回到前台时刷新。

## Commands

### Docker Compose (from the repository root)

The documented deployment environment is an Ubuntu 26.04 VM (compose file is `compose.yaml`). These commands use Bash; repository paths are not VM-specific.

```bash
cp .env.example .env
# Replace all seven placeholders before starting.
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api frontend scheduler mysql redis migrate seed
```

`.env` supplies `MYSQL_ROOT_PASSWORD`, `MYSQL_APP_PASSWORD`, `APP_SECRET_KEY`, and the four `DEMO_*_PASSWORD` values. Compose runs migrations, then seeds roles, demo users, and `data/sample/replay_sample.json` before starting the API. The frontend is at `http://127.0.0.1:8080`; API, MySQL, and Redis have no published host ports. The `scheduler` service runs `python -m backend.app.scheduler` on the same image (notification backfill every `NOTIFICATION_SCAN_INTERVAL_SECONDS`, default 300); it needs only MySQL, not Redis or `data/results`.

```bash
# Rebuild after source changes; source is copied into images, not bind-mounted.
docker compose build api frontend scheduler
docker compose up -d api frontend scheduler

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

Test suite layout: `test_units.py` (no services needed), `test_integration.py`, `test_rbac_matrix.py`, `test_state_machine.py`, `test_user_management.py`, `test_login.py`, `test_ingest.py`, `test_fusion.py` (FR-04 fusion traceability + below-threshold rejection), `test_notifications.py` (subscriptions + publish/withdraw delivery, per-user isolation), `test_scheduler.py` (backfill idempotency + SYSTEM audit via a direct `run_scan` call, no sleeping), `test_tasks.py` (publish → task, permissions, state machine, one-shot escalation); `tests/manual_round{2,3,4}.sh` are manual shell scripts. `tests/conftest.py` provides the shared fixtures `new_client`, `login`, `make_warning`, `created_warnings`, `created_users`, `created_subscriptions`, `subscriber`, `bystander`, plus the helpers `publish_warning` and `notifications_for` (notifications and subscriptions FK to `users` without `ondelete`, so the cleanup helpers must delete them first), and auto-skips `@pytest.mark.integration` tests unless `RUN_INTEGRATION=1`. Full suite after the backend review: **75 passed**.

### Local development

For Python on Ubuntu, install `python3-venv` if necessary. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Before running the backend locally, configure `APP_SECRET_KEY`, `DATABASE_URL` (MySQL/PyMySQL), `REDIS_URL`, and `DEMO_*_PASSWORD`, with reachable MySQL/Redis services. The Compose `.env` template alone does not configure local database/Redis URLs, and default Compose does not expose their ports. `backend/app/db.py` creates its SQLAlchemy engine at import time; without env overrides, `config.py` boots with `app_secret_key = "dev-insecure-secret"`, `DATABASE_URL = mysql+pymysql://weather_app:weather_app_pw@127.0.0.1:3306/weather_warning`, and `REDIS_URL = redis://127.0.0.1:6379/0`.

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

**Online application:** Vue Router handles page navigation/authentication guards; `frontend/src/api.js` centralizes `/api/v1` requests, credential cookies, CSRF headers, error mapping, and a 60-second GET cache/in-flight deduplication — but that cache is **allowlisted** to `/cities` and `/metrics/experiments*`, not all GETs (204 → `null`; backend `message` wins over the module-local `ERROR_ZH` fallback). Vite proxies requests during development; production Nginx proxies to the API and provides SPA fallback.

**Frontend state and layout:** `frontend/src/auth.js` is the single shared `reactive` singleton (`user`/`csrf`/`ready` + `set`/`clear`/`hasRole`); `frontend/src/notifications.js` is a second, smaller one (`notificationState.unread` + `refreshUnread`/`resetUnread`) that keeps the topbar bell and the notification centre showing the same number. There is no Pinia/Vuex. The router (`router.js`) lazy-loads views and its global guard does a one-time `/auth/me` bootstrap then enforces login + role gates. Source map: `views/` (14 pages: Dashboard, Monitor, Replay, Metrics, Warnings, WarningDetail, Review, Tasks, Hazards, Notifications, Audit, Users, Login, NotFound), `components/` (ChartPanel, ClosedLoopStepper, StatusBadge, EmptyState, PaginationBar, TableSkeleton), `charts/` (`theme.js` + `options.js` ECharts option builders), `lib/` (`echarts.js` tree-shaken registration, `chinaMap.js`), `ui/` (`labels.js`, `useCountUp.js`), `data/cityCoords.js`, `assets/china.json`. The current visual system is the dark "command-center" redesign (`style.css` dark tokens + ECharts dashboards: China effect-scatter map, radar, model bar) from commit `6956c47`.

`backend/app/main.py` assembles authentication, replay, metrics, warnings, notifications/subscriptions, response tasks, audit, hazards, monitor, and admin user-management routers under `/api/v1`, plus request-ID/CSRF middleware (and CORS when `cors_origin_list` is non-empty) and `/health`, `/health/db`, `/health/redis`. Authentication dependencies in `deps.py` resolve Redis sessions but read active users and roles from MySQL on each request; cached session roles are not authoritative. State-changing requests except login require a CSRF header matching the Redis session token.

Routers signal business errors as `HTTPException(status_code, detail="UPPER_SNAKE_CODE")`. Global handlers in `main.py` turn these and request-validation failures into the documented envelope `{"error": {"code", "message", "request_id"}}` (`422 VALIDATION_ERROR`). `backend/app/errors.py` `MESSAGES` is the authoritative code→中文 message map; `frontend/src/api.js` maps `error.code` through `ERROR_ZH` as a fallback. When you add a code, add it to `errors.py` `MESSAGES`, `ERROR_ZH`, and `docs/interface-design-v1.md`. Tests should assert `json()["error"]["code"]`, not `detail`.

MySQL models and Alembic migrations hold authoritative users, datasets, forecast/observation records, fusion runs, warning lifecycle records, feedback, subscriptions, notifications, and audit logs. Redis holds sessions, not business facts. `backend/app/seed.py` imports the offline sample and initializes reference data/demo accounts; there is no general-purpose external-data import API.

`backend/app/models.py` defines **19 tables**; migrations in `backend/migrations/versions/` run `0001_initial`→`0005_subscriptions_notifications` (`0004` adds `dataset_issues`, `0005` adds `warning_subscriptions` + `notifications` + `response_tasks` — use either as the pattern for a new migration; the next migration is `0006`). `response_tasks` is created but unused until Phase B slice 2.

**Business core — `backend/app/services/`** (routers stay thin: params, auth deps, serialization):
- `warnings.py` — warning state machine. `Transition` dataclass plus `SUBMIT`/`APPROVE`/`REJECT`/`PUBLISH`/`WITHDRAW` encode allowed source states, target, timestamps and audit action; `is_viewer_only` drives visibility. `create_warning` recomputes via `compute_replay` (raising `409 THRESHOLD_NOT_REACHED` when the recomputed risk level is `None`, i.e. below the selected threshold) and persists `FusionRun` + `FusionInput` + `WarningResult`; `to_out` / `to_detail_out` serialize. Write functions only `flush()` — the router `commit()`s, so business rows and the audit row share one transaction. `publish_warning` / `withdraw_warning` also call `notifications.notify_warning` so subscribers are notified inside that same transaction.
- `subscriptions.py` — matches a warning's (hazard_type, city_code) against each user's subscription; `ALL_HAZARDS = "*"` / `ALL_CITIES = ""` sentinels mean "any". Duplicate scope → `409 SUBSCRIPTION_EXISTS`.
- `notifications.py` — builds and stores in-app notifications. `notify_users` is the generic insert (dedupe by `dedupe_key`); `notify_warning` resolves subscribers and calls it. Also owns the notification-centre queries (`list_notifications`, `unread_count`, `mark_read`, `mark_all_read`) and `backfill_published` for the scan.
- `tasks.py` — response tasks. `create_for_published` runs inside the publish transaction (assignee = warning creator, reassigned to the publisher when the creator is inactive; due = now + `RESPONSE_TASK_DUE_MINUTES`); `ack_task`/`complete_task` enforce the `PENDING → ACKED → COMPLETED` machine and "assignee or ADMIN"; `list_tasks` lets any business role read a warning's tasks when the `warning` filter is present, but keeps the board list (no filter) to ADMIN + own. `escalate_overdue` is the scan's second pass and never changes `status` — overdue is `escalated_at`/`escalation_level` only — and it writes through a **conditional single-row UPDATE** (status/due_at/escalated_at in the WHERE, decided by `rowcount`) so a completion committed after the scan read cannot be overwritten.
- `audit.py` — `add_audit` / `AuditContext` (bound to request_id + client IP). Append-only, same transaction as the business write.
- `ingest.py` — offline-sample import validation (unknown city/model, bad date, duplicate, out-of-order, invalid value). Each problem is written to `dataset_issues` and skipped; the dataset's `quality_status` becomes `PARTIAL`; idempotent by dataset version.
- `replay.py::compute_replay` — shared daily replay and warning calculation. `metrics.py` reads frozen `data/results/pooled.json` relative to the working directory, caching by file mtime; Compose mounts `data/results` read-only. Run `tests/` from the repository root so this path resolves. The monitor is a stored-data snapshot, not a live ingestion stream.

App-level helper modules sit directly under `backend/app/` (not `services/`): `clock.py` (single `utcnow()`, naive UTC matching `DATETIME(6)`), `security.py` (Argon2 hashing, unguessable 26-char `public_id`, CSRF/session tokens), `scheduler.py` (`run_scan(db, *, now, hours)` pure function running two passes (notification backfill + overdue-task escalation) plus a SIGTERM-aware `main()` loop; runs in its own compose service, not in the API process), plus `cities.py` (`ALL_CITIES`), `hazards.py` (`ALL_HAZARDS`), `errors.py`, `config.py`, `db.py`, `deps.py`, `session.py`, `schemas.py`.

**Fusion traceability (FR-04):** `GET /warnings/{public_id}` returns `WarningDetailOut`, a **subclass** of `WarningOut` (additive only), adding `models` (four model inputs), `baseline_mm`, `proxy_label_mm`, `dataset_version`. `WarningOut` stays unchanged for list/create.

**Auth hardening (FR-01):** `config.py` carries both session **idle TTL** and **absolute TTL**; Redis enforces a **per-IP login-failure limit** (`login:fail:<ip>` → `429 LOGIN_RATE_LIMITED`) alongside per-account lockout. Login always returns uniform `INVALID_CREDENTIALS` (even while locked); `ACCOUNT_DISABLED` only after a correct password. These are locked decisions (see the handoff section) — do not re-litigate.

Research helper scripts: `backend/make_sample.py` regenerates `data/sample/replay_sample.json`; `backend/coverage_report.py` summarizes data coverage.

## Cross-cutting constraints

- Preserve the protocol in `docs/data-and-method.md`: fixed **24-hour lead** (`previous_day1`; centralized as `LEAD_HOURS = 24` in `backend/app/cities.py`), complete UTC days, and 2024/2025/2026 training/validation/test years. The main comparison is ECMWF IFS against equal-weight ECMWF/GFS/ICON/GEM on identical samples.
- ERA5 is a **proxy label**, not a station measurement. GHCN observations are an independent, coverage-limited cross-check, not a replacement for the nine-city labels.
- Replay selects the latest non-`FAILED` dataset (`PARTIAL` datasets are still usable; missing models yield `PARTIAL`). Fusion requires all four models for the same city, valid time, and lead; missing models yield `PARTIAL` with no fused value, and cannot create a formal warning. Even with all four models (`COMPLETE`), a fused value below the selected threshold yields a `None` risk level and creation is rejected with `409 THRESHOLD_NOT_REACHED`. Warning creation recomputes results server-side rather than trusting frontend values.
- Warning transitions enforce current state and role, prohibit self-review, and commit business changes with audit records in the same transaction. VIEWER-only users see only published warnings; audit access is admin-only and read-only through business APIs. Public warning identifiers are unguessable, not database sequence IDs.
- User management (`routers/users.py`, ADMIN only) serializes every write by locking the ADMIN `Role` row with `FOR UPDATE`, then re-reading the actor's active status and ADMIN grant before locking the target user. Keep that lock order. It prevents self-disable, self-removal of ADMIN, and removing the last active ADMIN. Requested roles must all exist in `roles`, or the transaction fails. Disabling an account takes effect on the next request; password reset intentionally leaves existing sessions valid. There is no delete or rename endpoint.
- Non-development configuration rejects an empty/default application secret. The development Compose configuration uses non-Secure cookies for loopback HTTP; production requires HTTPS and Secure cookies.
